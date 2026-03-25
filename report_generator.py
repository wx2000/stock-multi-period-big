"""
HTML 报告生成模块
将本次生成的所有股票K线图以二列网格形式输出为一个自包含 HTML 文件
"""

import os
import base64
from datetime import datetime


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


def generate_html_report(
    saved_paths: list,
    stock_data_list: list,
    output_dir: str,
) -> str:
    """
    生成 HTML 报告
    saved_paths:      generate_charts_batch 返回的图片路径列表
    stock_data_list:  对应的 stock_data 列表（取最新价/涨跌幅）
    output_dir:       输出目录
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

        # 尝试从 stock_data 取行情摘要
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
            <span class="label">{label}</span>
            <span class="meta">{summary}</span>
          </div>
          <img src="{img_src}" alt="{label}" loading="lazy"
               onclick="openLightbox(this.src, '{label}')" />
        </div>"""
        cards_html.append(card)

    cards_joined = "\n".join(cards_html)
    count = len(saved_paths)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>多周期K线图报告 · {date_str}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: #0a0a0a;
    color: #cccccc;
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
    color: #ffffff;
    font-weight: 700;
    letter-spacing: 2px;
  }}
  .header .sub {{
    font-size: 13px;
    color: #555;
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
    background: #111111;
    border: 1px solid #222;
    border-radius: 8px;
    overflow: hidden;
    transition: border-color .2s, box-shadow .2s;
  }}
  .card:hover {{
    border-color: #3a6ea8;
    box-shadow: 0 0 12px rgba(58,110,168,.35);
  }}

  .card-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    background: #161616;
    border-bottom: 1px solid #1e1e1e;
  }}
  .label {{
    font-size: 14px;
    font-weight: 600;
    color: #e0e0e0;
    letter-spacing: 0.5px;
  }}
  .meta {{ font-size: 13px; }}
  .price {{ color: #e0e0e0; margin-right: 4px; }}
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
    color: #444;
    cursor: pointer;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 3px 9px;
  }}
  #lb-zoom-reset:hover {{ color: #aaa; border-color: #555; }}

  /* ── 页脚 ── */
  .footer {{
    text-align: center;
    margin-top: 36px;
    font-size: 12px;
    color: #333;
  }}

  @media (max-width: 900px) {{
    .grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>📈 多周期 K 线图报告</h1>
  <div class="sub">生成时间：{date_str} &nbsp;|&nbsp; 共 {count} 只股票</div>
</div>

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
  <div class="lb-hint">滚轮缩放 &nbsp;·&nbsp; 拖拽平移 &nbsp;·&nbsp; 双击还原 &nbsp;·&nbsp; Esc 关闭</div>
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
