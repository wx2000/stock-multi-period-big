"""
HTML 报告生成模块
将本次生成的所有股票K线图以二列网格形式输出为一个自包含 HTML 文件
"""

import os
import base64
from datetime import datetime
import pandas as pd


def _calc_ma260_deviation(stock_data: dict):
    """
    从 stock_data["periods"]["日线"] 计算 MA260 偏差值
    返回 (偏差值float, 颜色str) 或 (None, None)
    """
    try:
        df = stock_data.get("periods", {}).get("日线", pd.DataFrame())
        if df.empty or len(df) < 20:
            return None, None
        ma260 = df["close"].rolling(window=260, min_periods=20).mean().iloc[-1]
        last_close = df["close"].iloc[-1]
        if not ma260 or ma260 == 0:
            return None, None
        deviation = last_close / ma260 - 1
        color = "#e03030" if deviation >= 0 else "#0aa855"
        return deviation, color
    except Exception:
        return None, None


def _img_to_base64(path: str) -> str:
    """将图片文件转为 base64 内嵌字符串，HTML 无需外部依赖"""
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{data}"


def _parse_label(filename: str) -> str:
    """
    从文件名解析标签，格式：
      601600-中国铝业_20260325_194525.png  →  601600 · 中国铝业
      TSLA_20260325_194538.png             →  TSLA
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    # 去掉时间戳部分（最后两段 _YYYYMMDD_HHMMSS）
    parts = base.split("_")
    code_name = "_".join(parts[:-2]) if len(parts) >= 3 else parts[0]
    # 替换 - 为 · 美化显示
    return code_name.replace("-", " · ")


def _chg_cls(v):
    """根据涨跌值返回 CSS 类名"""
    if v is None:
        return "flat-c"
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return "flat-c"


def _chg_str(v, fmt="+.2f"):
    """格式化涨跌值，带符号"""
    if v is None:
        return "-"
    return f"{v:{fmt}}"


def _build_market_html(market_data: dict) -> str:
    """根据 market_summary 数据构建收盘点评 HTML 块"""
    if not market_data or market_data.get("error"):
        err = (market_data or {}).get("error", "未获取到数据")
        return f'<div class="market-panel"><div class="panel-title">🏛 今日市场概况</div><p style="color:#aaa;font-size:13px">数据获取失败：{err}</p></div>'

    md = market_data
    pt = md.get("time", "")

    # ── 指数行（去掉涨跌家数列）──
    rows = ""
    for idx in md.get("indices", []):
        name      = idx["name"]
        close     = idx["close"]
        pct       = idx.get("chg_pct")
        pt_val    = idx.get("chg_pt")
        amount    = idx.get("amount", "-")
        cls       = _chg_cls(pct)
        pct_str   = f"{pct:+.2f}%" if pct is not None else "-"
        pt_str    = f"{pt_val:+.2f}" if pt_val is not None else "-"
        close_str = f"{close:,.2f}" if close is not None else "-"
        rows += f"""
      <tr>
        <td>{name}</td>
        <td class="{cls}">{close_str}</td>
        <td class="{cls}">{pct_str}</td>
        <td class="{cls}">{pt_str}</td>
        <td>{amount}</td>
      </tr>"""

    # ── 三市成交额 ──
    sh_a  = md.get("sh_amount", "-")
    sz_a  = md.get("sz_amount", "-")
    bj_a  = md.get("bj_amount", "-")
    tot_a = md.get("market_total_amount", "-")

    # ── 近30日成交额折线图数据（JSON注入Canvas脚本）──
    history = md.get("amount_history", [])
    import json as _json
    chart_dates  = _json.dumps([h["date"][-5:]  for h in history])   # "MM-DD"
    chart_values = _json.dumps([h["amount_yi"]   for h in history])   # 亿

    return f"""
<div class="market-panel">
  <div class="panel-title">
    🏛 今日市场概况
    <span class="pt-time">数据时间：{pt}</span>
  </div>

  <div class="market-body">
    <!-- 左：指数表格 + 成交额 -->
    <div class="market-left">
      <table class="idx-table">
        <thead>
          <tr>
            <th>指数</th>
            <th>收盘点位</th>
            <th>涨跌幅</th>
            <th>涨跌点</th>
            <th>成交额</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>

      <div class="amount-row">
        <div class="amt-item">
          <span class="amt-label">全市场成交额</span>
          <span class="amt-val amt-total">{tot_a}</span>
        </div>
        <div class="amt-item">
          <span class="amt-label">沪市</span>
          <span class="amt-val">{sh_a}</span>
        </div>
        <div class="amt-item">
          <span class="amt-label">深市</span>
          <span class="amt-val">{sz_a}</span>
        </div>
        <div class="amt-item">
          <span class="amt-label">北交所</span>
          <span class="amt-val">{bj_a}</span>
        </div>
      </div>
    </div>

    <!-- 右：30日成交额折线图 -->
    <div class="market-right">
      <div class="chart-title">近30日全市场成交额（亿元）</div>
      <canvas id="amountChart"></canvas>
    </div>
  </div>
</div>

<script>
(function() {{
  var dates  = {chart_dates};
  var values = {chart_values};
  if (!dates.length) return;

  var canvas = document.getElementById('amountChart');
  if (!canvas) return;

  // 自适应 canvas 尺寸
  function resize() {{
    canvas.width  = canvas.parentElement.clientWidth  || 500;
    canvas.height = canvas.parentElement.clientHeight || 160;
    drawChart();
  }}

  function drawChart() {{
    var W = canvas.width, H = canvas.height;
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, W, H);

    var PAD_L = 54, PAD_R = 18, PAD_T = 18, PAD_B = 38;
    var cW = W - PAD_L - PAD_R;
    var cH = H - PAD_T - PAD_B;

    var minV = Math.min.apply(null, values);
    var maxV = Math.max.apply(null, values);
    var span = maxV - minV || 1;
    // 上下留出 10% 余量
    var lo = minV - span * 0.10;
    var hi = maxV + span * 0.10;
    var vSpan = hi - lo;

    var n = values.length;
    function xOf(i) {{ return PAD_L + (i / (n - 1)) * cW; }}
    function yOf(v) {{ return PAD_T + (1 - (v - lo) / vSpan) * cH; }}

    // ── 背景网格 ──
    ctx.strokeStyle = '#e8eaed';
    ctx.lineWidth   = 1;
    var gridLines = 4;
    for (var g = 0; g <= gridLines; g++) {{
      var gy = PAD_T + (g / gridLines) * cH;
      ctx.beginPath(); ctx.moveTo(PAD_L, gy); ctx.lineTo(PAD_L + cW, gy); ctx.stroke();
      var label = ((hi - (g / gridLines) * vSpan) / 10000).toFixed(2) + '万亿';
      if ((hi - (g / gridLines) * vSpan) < 10000) {{
        label = Math.round(hi - (g / gridLines) * vSpan) + '亿';
      }}
      ctx.fillStyle = '#aaa';
      ctx.font = '10px Microsoft YaHei, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(label, PAD_L - 4, gy + 3.5);
    }}

    // ── 渐变填充 ──
    var grad = ctx.createLinearGradient(0, PAD_T, 0, PAD_T + cH);
    grad.addColorStop(0, 'rgba(26,111,196,0.25)');
    grad.addColorStop(1, 'rgba(26,111,196,0.02)');
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(values[0]));
    for (var i = 1; i < n; i++) ctx.lineTo(xOf(i), yOf(values[i]));
    ctx.lineTo(xOf(n-1), PAD_T + cH);
    ctx.lineTo(xOf(0),   PAD_T + cH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // ── 折线 ──
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(values[0]));
    for (var i = 1; i < n; i++) ctx.lineTo(xOf(i), yOf(values[i]));
    ctx.strokeStyle = '#1a6fc4';
    ctx.lineWidth   = 2;
    ctx.lineJoin    = 'round';
    ctx.stroke();

    // ── 最后一点高亮 ──
    var lx = xOf(n-1), ly = yOf(values[n-1]);
    ctx.beginPath();
    ctx.arc(lx, ly, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#1a6fc4';
    ctx.fill();
    // 最新值标注
    var lastLabel = values[n-1] >= 10000
      ? (values[n-1]/10000).toFixed(2) + '万亿'
      : Math.round(values[n-1]) + '亿';
    ctx.fillStyle = '#1a6fc4';
    ctx.font = 'bold 11px Microsoft YaHei, sans-serif';
    ctx.textAlign = lx > W - 80 ? 'right' : 'left';
    ctx.fillText(lastLabel, lx + (lx > W - 80 ? -8 : 8), ly - 6);

    // ── X轴日期标签（每5个取一个）──
    ctx.fillStyle = '#aaa';
    ctx.font = '10px Microsoft YaHei, sans-serif';
    ctx.textAlign = 'center';
    var step = Math.ceil(n / 6);
    for (var i = 0; i < n; i++) {{
      if (i % step === 0 || i === n - 1) {{
        ctx.fillText(dates[i], xOf(i), H - PAD_B + 14);
      }}
    }}

    // ── X轴基线 ──
    ctx.beginPath();
    ctx.moveTo(PAD_L, PAD_T + cH);
    ctx.lineTo(PAD_L + cW, PAD_T + cH);
    ctx.strokeStyle = '#ddd';
    ctx.lineWidth   = 1;
    ctx.stroke();
  }}

  // 初次绘制 + 窗口 resize 重绘
  setTimeout(resize, 0);
  window.addEventListener('resize', resize);
}})();
</script>"""


def _build_sector_html(sector: dict) -> str:
    """根据 fetch_sector_data() 返回的数据构建板块&资金面板 HTML"""
    if not sector:
        return ""

    def _rows(items, is_up_section):
        html = ""
        for it in items:
            pct = it.get("chg_pct")
            cls = _chg_cls(pct)
            pct_str = f"{pct:+.2f}%" if pct is not None else "-"
            html += f'<div class="sector-item"><span class="sector-name">{it["name"]}</span><span class="sector-pct {cls}">{pct_str}</span></div>'
        return html

    def _fund_rows(items, is_inflow):
        html = ""
        for it in items:
            zl  = it.get("zljlr", 0) or 0
            zls = it.get("zljlr_str", "-")
            cls = "up" if zl > 0 else "down"
            sign = "+" if zl > 0 else "-"
            pct = it.get("chg_pct")
            pct_str = f"{pct:+.2f}%" if pct is not None else ""
            html += (
                f'<div class="fund-item">'
                f'<span class="fund-name">{it["name"]}<span style="color:#aaa;font-size:11px;margin-left:4px">{pct_str}</span></span>'
                f'<span class="fund-amount {cls}">{sign}{zls}</span>'
                f'</div>'
            )
        return html

    # 主力净流入汇总
    sh_zl  = sector.get("sh_zljlr", "-")
    sz_zl  = sector.get("sz_zljlr", "-")
    tot_zl = sector.get("total_zljlr", "-")
    sh_raw  = sector.get("sh_zljlr_raw", 0) or 0
    sz_raw  = sector.get("sz_zljlr_raw", 0) or 0
    tot_raw = sector.get("total_zljlr_raw", 0) or 0
    sh_cls  = _chg_cls(sh_raw)
    sz_cls  = _chg_cls(sz_raw)
    tot_cls = _chg_cls(tot_raw)
    sh_sign  = "+" if sh_raw  > 0 else ""
    sz_sign  = "+" if sz_raw  > 0 else ""
    tot_sign = "+" if tot_raw > 0 else ""

    return f"""
<div class="sector-panel">
  <div class="panel-title">📊 板块动向 &amp; 主力资金</div>

  <!-- 主力净流入汇总 -->
  <div class="fund-summary">
    <div class="fs-item">
      <span class="fs-label">全市场主力净流入</span>
      <span class="fs-val {tot_cls}">{tot_sign}{tot_zl}</span>
    </div>
    <div class="fs-item">
      <span class="fs-label">沪市</span>
      <span class="fs-val {sh_cls}">{sh_sign}{sh_zl}</span>
    </div>
    <div class="fs-item">
      <span class="fs-label">深市</span>
      <span class="fs-val {sz_cls}">{sz_sign}{sz_zl}</span>
    </div>
  </div>

  <!-- 板块涨跌四栏 -->
  <div class="sector-grid">
    <div>
      <div class="sector-col-title">🔴 概念板块 涨幅TOP5</div>
      {_rows(sector.get("concept_up", []), True)}
    </div>
    <div>
      <div class="sector-col-title">🟢 概念板块 跌幅TOP5</div>
      {_rows(sector.get("concept_down", []), False)}
    </div>
    <div>
      <div class="sector-col-title">🔴 行业板块 涨幅TOP5</div>
      {_rows(sector.get("industry_up", []), True)}
    </div>
    <div>
      <div class="sector-col-title">🟢 行业板块 跌幅TOP5</div>
      {_rows(sector.get("industry_down", []), False)}
    </div>
  </div>

  <!-- 主力资金流向 -->
  <div class="fund-row">
    <div>
      <div class="fund-col-title">🔴 主力净流入概念板块 TOP5</div>
      {_fund_rows(sector.get("fund_in", []), True)}
    </div>
    <div>
      <div class="fund-col-title">🟢 主力净流出概念板块 TOP5</div>
      {_fund_rows(sector.get("fund_out", []), False)}
    </div>
  </div>
</div>"""


def generate_html_report(
    saved_paths: list,
    stock_data_list: list,
    output_dir: str,
    market_data: dict = None,
) -> str:
    """
    生成 HTML 报告
    saved_paths:      generate_charts_batch 返回的图片路径列表
    stock_data_list:  对应的 stock_data 列表（取最新价/涨跌幅）
    output_dir:       输出目录
    market_data:      market_summary.fetch_market_summary() 返回的大盘数据（可选）
    返回: HTML 文件路径
    """
    now = datetime.now()
    ts_str   = now.strftime("%Y%m%d_%H%M%S")
    # 避免 strftime 中文字符触发 Windows locale 编码问题，手动拼接
    date_str = (
        f"{now.year}\u5e74{now.month:02d}\u6708{now.day:02d}\u65e5"
        f" {now.hour:02d}:{now.minute:02d}"
    )

    # ── 构建每张卡片 ─────────────────────────────────────────
    cards_html = []
    for i, path in enumerate(saved_paths):
        label = _parse_label(path)

        # ── MA260 偏差值 ──────────────────────────────────────
        dev_part = ""
        if i < len(stock_data_list):
            deviation, dev_color = _calc_ma260_deviation(stock_data_list[i])
            if deviation is not None:
                dev_sign = "+" if deviation >= 0 else ""
                dev_part = (
                    f' <span style="color:{dev_color};font-weight:700;">'
                    f'{dev_sign}{deviation * 100:.1f}%</span>'
                )

        # 尝试从 stock_data 取行情摘要（当日价格+涨跌幅）
        summary = ""
        if i < len(stock_data_list):
            info = stock_data_list[i].get("info", {})
            price    = info.get("price")
            chg_pct  = info.get("chg_pct")
            if price is not None:
                price_str = f"{price:.2f}"
                if chg_pct is not None:
                    sign  = "+" if chg_pct >= 0 else ""
                    color = "#ff4444" if chg_pct >= 0 else "#00cc66"
                    summary = (
                        f'<span class="price">{price_str}</span>'
                        f'<span class="chg" style="color:{color}">'
                        f'  {sign}{chg_pct:.2f}%</span>'
                    )
                else:
                    summary = f'<span class="price">{price_str}</span>'

        img_src = _img_to_base64(path)
        card = f"""
        <div class="card">
          <div class="card-header">
            <span class="label">{label}{dev_part}</span>
            <span class="meta">{summary}</span>
          </div>
          <img src="{img_src}" alt="{label}" loading="lazy"
               onclick="openLightbox(this.src, '{label}')" />
        </div>"""
        cards_html.append(card)

    cards_joined = "\n".join(cards_html)
    count = len(saved_paths)

    # ── 构建大盘点评区域 HTML ────────────────────────────────
    market_html = _build_market_html(market_data)

    # ── 构建板块&资金面板 HTML ───────────────────────────────
    sector_html = _build_sector_html((market_data or {}).get("sector", {}))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>多周期K线图报告 · {date_str}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: #ffffff;
    color: #333333;
    font-family: "Microsoft YaHei", "PingFang SC", "SimHei", sans-serif;
    padding: 24px 20px 40px;
  }}

  /* ── 顶部标题 ── */
  .header {{
    text-align: center;
    margin-bottom: 28px;
  }}
  .header h1 {{
    font-size: 22px;
    color: #111111;
    font-weight: 700;
    letter-spacing: 2px;
  }}
  .header .sub {{
    font-size: 13px;
    color: #888;
    margin-top: 6px;
  }}

  /* ── 二列网格 ── */
  .grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 18px;
    max-width: 1600px;
    margin: 0 auto;
  }}

  /* ── 卡片 ── */
  .card {{
    background: #f8f8f8;
    border: 1px solid #ddd;
    border-radius: 8px;
    overflow: hidden;
    transition: border-color .2s, box-shadow .2s;
  }}
  .card:hover {{
    border-color: #3a6ea8;
    box-shadow: 0 0 12px rgba(58,110,168,.2);
  }}

  .card-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    background: #eeeeee;
    border-bottom: 1px solid #ddd;
  }}
  .label {{
    font-size: 14px;
    font-weight: 600;
    color: #222222;
    letter-spacing: 0.5px;
  }}
  .ma260-dev {{
    font-size: 13px;
    font-weight: 700;
    margin-left: 10px;
    letter-spacing: 0.5px;
  }}
  .meta {{ font-size: 13px; }}
  .price {{ color: #333333; margin-right: 4px; }}
  .chg   {{ font-weight: 600; }}

  .card img {{
    width: 100%;
    display: block;
    cursor: zoom-in;
  }}

  /* ── 灯箱 ── */
  #lightbox {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.92);
    z-index: 9999;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    overflow: hidden;
  }}
  #lightbox.active {{ display: flex; }}
  #lb-img-wrap {{
    position: relative;
    overflow: hidden;
    width: 95vw;
    height: 88vh;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: grab;
  }}
  #lb-img-wrap.dragging {{ cursor: grabbing; }}
  #lb-img {{
    max-width: none;
    max-height: none;
    border-radius: 6px;
    box-shadow: 0 0 40px rgba(0,0,0,.8);
    transform-origin: center center;
    user-select: none;
    pointer-events: none;
    transition: none;
  }}
  #lightbox .lb-label {{
    margin-top: 8px;
    font-size: 13px;
    color: #888;
    flex-shrink: 0;
  }}
  #lightbox .lb-hint {{
    font-size: 11px;
    color: #444;
    margin-top: 3px;
    flex-shrink: 0;
  }}
  #lightbox .lb-close {{
    position: absolute;
    top: 14px; right: 20px;
    font-size: 26px;
    color: #555;
    cursor: pointer;
    line-height: 1;
    z-index: 10;
  }}
  #lightbox .lb-close:hover {{ color: #ccc; }}
  #lb-zoom-reset {{
    position: absolute;
    bottom: 14px; right: 20px;
    font-size: 12px;
    color: #aaa;
    cursor: pointer;
    background: #222;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 3px 9px;
  }}
  #lb-zoom-reset:hover {{ color: #fff; border-color: #888; }}

  /* ── 页脚 ── */
  .footer {{
    text-align: center;
    margin-top: 36px;
    font-size: 12px;
    color: #aaa;
  }}

  /* ── 收盘点评区域 ── */
  .market-panel {{
    max-width: 1600px;
    margin: 0 auto 28px;
    background: #f5f7fa;
    border: 1px solid #e0e4ea;
    border-radius: 10px;
    padding: 18px 24px;
  }}
  .market-panel .panel-title {{
    font-size: 15px;
    font-weight: 700;
    color: #222;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid #e0e4ea;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .market-panel .panel-title .pt-time {{
    font-size: 12px;
    font-weight: 400;
    color: #999;
    margin-left: auto;
  }}
  /* 左右分栏 */
  .market-body {{
    display: flex;
    gap: 28px;
    align-items: flex-start;
  }}
  .market-left {{
    flex: 1 1 0;
    min-width: 0;
  }}
  .market-right {{
    flex: 1 1 0;
    min-width: 0;
  }}
  .chart-title {{
    font-size: 12px;
    color: #888;
    margin-bottom: 6px;
  }}
  #amountChart {{
    width: 100%;
    height: 200px;
    display: block;
  }}
  /* 指数表格 */
  .idx-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin-bottom: 12px;
  }}
  .idx-table th {{
    text-align: center;
    color: #888;
    font-weight: 500;
    padding: 4px 8px;
    border-bottom: 1px solid #e8e8e8;
  }}
  .idx-table th:first-child {{ text-align: left; }}
  .idx-table td {{
    text-align: center;
    padding: 6px 8px;
    border-bottom: 1px solid #f0f0f0;
    white-space: nowrap;
  }}
  .idx-table td:first-child {{ text-align: left; font-weight: 600; color: #333; }}
  .idx-table tr:last-child td {{ border-bottom: none; }}
  .up   {{ color: #e03030; font-weight: 600; }}
  .down {{ color: #0aa855; font-weight: 600; }}
  .flat-c {{ color: #888; }}
  /* 成交额汇总行 */
  .amount-row {{
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
    font-size: 13px;
    color: #555;
  }}
  .amount-row .amt-item {{
    display: flex;
    align-items: center;
    gap: 5px;
  }}
  .amount-row .amt-label {{ color: #999; }}
  .amount-row .amt-val   {{ font-weight: 600; color: #333; font-size: 14px; }}
  .amount-row .amt-total {{ color: #1a6fc4; font-weight: 700; font-size: 15px; }}

  /* ── 板块与资金面板 ── */
  .sector-panel {{
    max-width: 1600px;
    margin: 0 auto 28px;
    background: #f5f7fa;
    border: 1px solid #e0e4ea;
    border-radius: 10px;
    padding: 18px 24px;
  }}
  .sector-panel .panel-title {{
    font-size: 15px;
    font-weight: 700;
    color: #222;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid #e0e4ea;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  /* 四列网格：概念涨/跌 + 行业涨/跌 */
  .sector-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 16px;
  }}
  .sector-col-title {{
    font-size: 12px;
    color: #888;
    margin-bottom: 8px;
    font-weight: 500;
    padding-bottom: 4px;
    border-bottom: 1px solid #eee;
  }}
  .sector-item {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 13px;
    border-bottom: 1px solid #f5f5f5;
  }}
  .sector-item:last-child {{ border-bottom: none; }}
  .sector-name {{ color: #333; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .sector-pct  {{ font-weight: 600; min-width: 52px; text-align: right; }}
  /* 资金流向区域 */
  .fund-row {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    padding-top: 12px;
    border-top: 1px solid #eee;
  }}
  .fund-col-title {{
    font-size: 12px;
    color: #888;
    margin-bottom: 8px;
    font-weight: 500;
    padding-bottom: 4px;
    border-bottom: 1px solid #eee;
  }}
  .fund-item {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 13px;
    border-bottom: 1px solid #f5f5f5;
  }}
  .fund-item:last-child {{ border-bottom: none; }}
  .fund-name   {{ color: #333; flex: 1; }}
  .fund-amount {{ font-weight: 600; min-width: 60px; text-align: right; }}
  /* 主力资金净流入汇总条 */
  .fund-summary {{
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
    margin-bottom: 12px;
    padding: 8px 12px;
    background: #eef2f8;
    border-radius: 6px;
    font-size: 13px;
  }}
  .fund-summary .fs-item {{ display: flex; align-items: center; gap: 6px; }}
  .fund-summary .fs-label {{ color: #888; }}
  .fund-summary .fs-val   {{ font-weight: 700; font-size: 14px; }}

  @media (max-width: 900px) {{
    .grid {{ grid-template-columns: 1fr; }}
    .market-body {{ flex-direction: column; }}
    .market-left {{ min-width: 0; width: 100%; }}
    #amountChart {{ height: 160px; }}
    .sector-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .fund-row    {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>📈 后期关注股票每日报告</h1>
  <div class="sub">生成时间：{date_str} &nbsp;|&nbsp; 共 {count} 只股票</div>
</div>

{market_html}

{sector_html}

<div class="grid">
{cards_joined}
</div>

<div class="footer">数据来源：东方财富 · 新浪财经 &nbsp;|&nbsp; 仅供参考，不构成投资建议</div>

<!-- 灯箱 -->
<div id="lightbox">
  <span class="lb-close" onclick="closeLightbox()">✕</span>
  <div id="lb-img-wrap">
    <img id="lb-img" src="" alt="" draggable="false" />
  </div>
  <div class="lb-label" id="lb-label"></div>
  <div class="lb-hint">双指缩放/滚轮缩放 &nbsp;·&nbsp; 拖拽平移 &nbsp;·&nbsp; 双击还原 &nbsp;·&nbsp; Esc 关闭</div>
  <span id="lb-zoom-reset" onclick="resetTransform()">还原</span>
</div>

<script>
(function() {{
  var lb      = document.getElementById('lightbox');
  var wrap    = document.getElementById('lb-img-wrap');
  var img     = document.getElementById('lb-img');
  var lbLabel = document.getElementById('lb-label');

  var scale = 1, tx = 0, ty = 0;
  var dragging = false, startX = 0, startY = 0, startTx = 0, startTy = 0;
  var MIN_SCALE = 0.5, MAX_SCALE = 10;

  function applyTransform() {{
    img.style.transform = 'translate(' + tx + 'px, ' + ty + 'px) scale(' + scale + ')';
  }}

  window.resetTransform = function() {{
    scale = 1; tx = 0; ty = 0;
    applyTransform();
  }};

  window.openLightbox = function(src, label) {{
    img.src = src;
    lbLabel.textContent = label;
    lb.classList.add('active');
    resetTransform();
    event.stopPropagation();
  }};

  window.closeLightbox = function() {{
    lb.classList.remove('active');
    img.src = '';
    resetTransform();
  }};

  // 滚轮缩放（以鼠标位置为缩放中心）
  wrap.addEventListener('wheel', function(e) {{
    e.preventDefault();
    var rect  = img.getBoundingClientRect();
    var mx    = e.clientX - (rect.left + rect.width  / 2);
    var my    = e.clientY - (rect.top  + rect.height / 2);
    var delta = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    var newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * delta));
    var ratio    = newScale / scale;
    tx = tx * ratio + mx * (1 - ratio);
    ty = ty * ratio + my * (1 - ratio);
    scale = newScale;
    applyTransform();
  }}, {{ passive: false }});

  // 拖拽平移
  wrap.addEventListener('mousedown', function(e) {{
    if (e.button !== 0) return;
    dragging = true;
    startX = e.clientX; startY = e.clientY;
    startTx = tx; startTy = ty;
    wrap.classList.add('dragging');
    e.preventDefault();
  }});
  window.addEventListener('mousemove', function(e) {{
    if (!dragging) return;
    tx = startTx + (e.clientX - startX);
    ty = startTy + (e.clientY - startY);
    applyTransform();
  }});
  window.addEventListener('mouseup', function() {{
    dragging = false;
    wrap.classList.remove('dragging');
  }});

  // 双击还原
  wrap.addEventListener('dblclick', function(e) {{
    e.stopPropagation();
    resetTransform();
  }});

  // ── 触摸事件（手机/平板）──────────────────────────────
  var touchStartDist = 0;   // 双指初始距离
  var touchStartScale = 1;  // 双指开始时的 scale
  var touchStartMidX = 0, touchStartMidY = 0; // 双指中点（屏幕坐标）
  var touchStartTx = 0, touchStartTy = 0;     // 双指开始时的位移
  var singleStartX = 0, singleStartY = 0;     // 单指起始
  var singleStartTx = 0, singleStartTy = 0;
  var isSingleTouch = false;

  function getTouchDist(t) {{
    var dx = t[0].clientX - t[1].clientX;
    var dy = t[0].clientY - t[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }}
  function getTouchMid(t) {{
    return {{
      x: (t[0].clientX + t[1].clientX) / 2,
      y: (t[0].clientY + t[1].clientY) / 2
    }};
  }}

  wrap.addEventListener('touchstart', function(e) {{
    e.preventDefault();
    var touches = e.touches;
    if (touches.length === 1) {{
      isSingleTouch = true;
      singleStartX  = touches[0].clientX;
      singleStartY  = touches[0].clientY;
      singleStartTx = tx;
      singleStartTy = ty;
    }} else if (touches.length === 2) {{
      isSingleTouch  = false;
      touchStartDist  = getTouchDist(touches);
      touchStartScale = scale;
      var mid         = getTouchMid(touches);
      touchStartMidX  = mid.x;
      touchStartMidY  = mid.y;
      touchStartTx    = tx;
      touchStartTy    = ty;
    }}
  }}, {{ passive: false }});

  wrap.addEventListener('touchmove', function(e) {{
    e.preventDefault();
    var touches = e.touches;
    if (touches.length === 1 && isSingleTouch) {{
      // 单指拖拽
      tx = singleStartTx + (touches[0].clientX - singleStartX);
      ty = singleStartTy + (touches[0].clientY - singleStartY);
      applyTransform();
    }} else if (touches.length === 2) {{
      // 双指缩放（以两指中点为缩放中心）
      var dist     = getTouchDist(touches);
      var newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, touchStartScale * dist / touchStartDist));
      var ratio    = newScale / touchStartScale;
      var rect     = img.getBoundingClientRect();
      var cx       = touchStartMidX - (rect.left + rect.width  / 2);
      var cy       = touchStartMidY - (rect.top  + rect.height / 2);
      tx = touchStartTx * ratio + cx * (1 - ratio);
      ty = touchStartTy * ratio + cy * (1 - ratio);
      scale = newScale;
      applyTransform();
    }}
  }}, {{ passive: false }});

  wrap.addEventListener('touchend', function(e) {{
    // 双指结束，剩1指时重置单指起点，避免跳动
    if (e.touches.length === 1) {{
      isSingleTouch  = true;
      singleStartX   = e.touches[0].clientX;
      singleStartY   = e.touches[0].clientY;
      singleStartTx  = tx;
      singleStartTy  = ty;
    }}
  }}, {{ passive: false }});

  // 点击背景关闭（非图片区域）
  lb.addEventListener('click', function(e) {{
    if (e.target === lb) closeLightbox();
  }});

  document.addEventListener('keydown', function(e) {{
    if (!lb.classList.contains('active')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === '0') resetTransform();
  }});
}})();
</script>
</body>
</html>"""

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"report_{ts_str}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [报告] 已保存: {out_path}")
    return out_path
