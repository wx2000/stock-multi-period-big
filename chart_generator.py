"""
图表生成模块
黑色背景，2行×3列，6个周期子图
每个子图内部分三区：K线+均线 / 成交量 / MACD
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 无头模式，不需要显示器
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec
from matplotlib.patches import FancyArrowPatch
import matplotlib.ticker as ticker
import matplotlib.font_manager as fm
from datetime import datetime

# ── 中文字体配置 ──────────────────────────────────────────────────
def _setup_chinese_font():
    """自动查找并配置中文字体"""
    # Windows 常见中文字体候选
    candidates = [
        "SimHei",       # 黑体（Windows 内置）
        "Microsoft YaHei",  # 微软雅黑
        "SimSun",       # 宋体
        "FangSong",     # 仿宋
        "KaiTi",        # 楷体
        "Arial Unicode MS",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return name

    # 尝试直接查找字体文件
    font_dirs = [
        r"C:\Windows\Fonts",
        r"C:\Windows\fonts",
    ]
    font_files = {
        "simhei.ttf": "SimHei",
        "msyh.ttc":   "Microsoft YaHei",
        "simsun.ttc": "SimSun",
    }
    for d in font_dirs:
        for fname, name in font_files.items():
            fpath = os.path.join(d, fname)
            if os.path.exists(fpath):
                fe = fm.FontEntry(fname=fpath, name=name)
                fm.fontManager.ttflist.append(fe)
                plt.rcParams["font.family"] = name
                plt.rcParams["axes.unicode_minus"] = False
                return name

    # 兜底：使用 sans-serif 并关闭 unicode minus
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False
    return "default"

_FONT_NAME = _setup_chinese_font()

# ── 颜色配置（中国市场：红涨绿跌）──────────────────────────────
C_BG        = "#0d0d0d"   # 主背景
C_PANEL     = "#111111"   # 子图背景
C_BORDER    = "#333333"   # 边框
C_TEXT      = "#cccccc"   # 普通文字
C_TITLE     = "#ffffff"   # 标题
C_UP        = "#ff3333"   # 涨（红）
C_DOWN      = "#00cc66"   # 跌（绿）
C_VOL_UP    = "#cc2222"   # 量柱涨
C_VOL_DOWN  = "#007744"   # 量柱跌
C_MACD_POS  = "#ff4444"   # MACD 柱正
C_MACD_NEG  = "#00bb55"   # MACD 柱负
C_MACD_LINE = "#ffaa00"   # MACD 线
C_SIGNAL    = "#00aaff"   # Signal 线
C_GRID      = "#1e1e1e"   # 网格线

# 均线颜色
MA_COLORS = {
    5:   "#ffdd44",
    10:  "#ff8800",
    20:  "#ff44ff",
    30:  "#44ddff",
    60:  "#ffffff",
    120: "#aaaaaa",
    250: "#666666",
}

# 每个周期显示的均线
PERIOD_MAS = {
    "分时": [],          # 分时不画均线（只画均价线）
    "日线": [5, 10, 20, 60, 120, 250],
    "周线": [5, 10, 20, 60],
    "月线": [5, 10, 20, 60],
    "季线": [4, 8, 12],
    "年线": [3, 5, 10],
}

PERIODS_ORDER = ["分时", "日线", "周线", "月线", "季线", "年线"]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


# ══════════════════════════════════════════════════════════════════
#  技术指标计算
# ══════════════════════════════════════════════════════════════════

def calc_ma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def calc_macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = (macd_line - signal_line) * 2
    return macd_line, signal_line, histogram


def format_volume(vol: float) -> str:
    if vol >= 1e8:
        return f"{vol/1e8:.1f}亿"
    if vol >= 1e4:
        return f"{vol/1e4:.1f}万"
    return f"{vol:.0f}"


def format_price(val: float) -> str:
    if abs(val) >= 1e4:
        return f"{val:.0f}"
    if abs(val) >= 100:
        return f"{val:.1f}"
    return f"{val:.2f}"


# ══════════════════════════════════════════════════════════════════
#  单个周期子图绘制
# ══════════════════════════════════════════════════════════════════

def _plot_period(fig, outer_gs_cell, df: pd.DataFrame, period: str, is_minute: bool = False):
    """
    在给定的 GridSpec 格子内绘制一个周期的三区图
    outer_gs_cell: SubplotSpec
    """
    # 内部分三行：K线(3份) / 成交量(1份) / MACD(1.2份)
    inner_gs = GridSpecFromSubplotSpec(
        3, 1,
        subplot_spec=outer_gs_cell,
        hspace=0,
        height_ratios=[3, 1, 1.2],
    )
    ax_k   = fig.add_subplot(inner_gs[0])
    ax_vol = fig.add_subplot(inner_gs[1], sharex=ax_k)
    ax_mac = fig.add_subplot(inner_gs[2], sharex=ax_k)

    for ax in [ax_k, ax_vol, ax_mac]:
        ax.set_facecolor(C_PANEL)
        ax.tick_params(colors=C_TEXT, labelsize=6, length=2)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        for spine in ax.spines.values():
            spine.set_edgecolor(C_BORDER)
        ax.grid(True, color=C_GRID, linewidth=0.4, linestyle="-", alpha=0.8)

    # ── 数据准备 ──────────────────────────────────────────────
    if df.empty:
        ax_k.text(0.5, 0.5, "暂无数据", transform=ax_k.transAxes,
                  color=C_TEXT, ha="center", va="center", fontsize=10)
        ax_k.set_title(period, color=C_TITLE, fontsize=9, loc="right", pad=2)
        plt.setp(ax_k.get_xticklabels(), visible=False)
        plt.setp(ax_vol.get_xticklabels(), visible=False)
        return

    # 只取最近 N 条（避免太密）
    MAX_BARS = {"分时": 240, "日线": 120, "周线": 100, "月线": 60, "季线": 40, "年线": 20}
    n = MAX_BARS.get(period, 120)
    df = df.tail(n).copy()

    x = np.arange(len(df))
    closes = df["close"].values

    # ── K线 / 分时折线 ────────────────────────────────────────
    if is_minute:
        # 分时图：折线 + 均价线
        ax_k.plot(x, df["price"].values, color=C_UP, linewidth=0.8, label="价格")
        if "avg_price" in df.columns:
            ax_k.plot(x, df["avg_price"].values, color=C_SIGNAL,
                      linewidth=0.6, linestyle="--", label="均价", alpha=0.8)
        ax_k.fill_between(x, df["price"].values,
                          df["price"].values.min(),
                          alpha=0.12, color=C_UP)
    else:
        opens  = df["open"].values
        highs  = df["high"].values
        lows   = df["low"].values

        # 蜡烛图
        bar_w = 0.6
        for i in range(len(df)):
            o, c, h, l = opens[i], closes[i], highs[i], lows[i]
            color = C_UP if c >= o else C_DOWN
            # 影线
            ax_k.plot([x[i], x[i]], [l, h], color=color, linewidth=0.7)
            # 实体
            rect_y  = min(o, c)
            rect_h  = max(abs(c - o), (h - l) * 0.005)  # 最小高度
            rect    = plt.Rectangle((x[i] - bar_w/2, rect_y), bar_w, rect_h,
                                    color=color, linewidth=0)
            ax_k.add_patch(rect)

        # 均线
        ma_list = PERIOD_MAS.get(period, [5, 10, 20])
        for ma_n in ma_list:
            if len(df) >= ma_n:
                ma_vals = calc_ma(df["close"], ma_n).values
                color = MA_COLORS.get(ma_n, "#888888")
                ax_k.plot(x, ma_vals, color=color, linewidth=0.6,
                          label=f"MA{ma_n}", alpha=0.9)

    # ── 成交量 ────────────────────────────────────────────────
    vol_col = "volume" if "volume" in df.columns else "price"
    vols = df[vol_col].values if vol_col == "volume" else np.zeros(len(df))

    if not is_minute:
        opens_v = df["open"].values
        vol_colors = [C_VOL_UP if c >= o else C_VOL_DOWN
                      for c, o in zip(closes, opens_v)]
    else:
        vol_colors = [C_VOL_UP] * len(df)

    ax_vol.bar(x, vols, color=vol_colors, width=0.6, linewidth=0)

    # ── MACD ──────────────────────────────────────────────────
    if len(closes) >= 26:
        close_s = pd.Series(closes)
        macd_line, signal_line, histogram = calc_macd(close_s)

        bar_colors = [C_MACD_POS if v >= 0 else C_MACD_NEG for v in histogram]
        ax_mac.bar(x, histogram.values, color=bar_colors, width=0.6, linewidth=0, alpha=0.8)
        ax_mac.plot(x, macd_line.values,  color=C_MACD_LINE, linewidth=0.7, label="MACD")
        ax_mac.plot(x, signal_line.values, color=C_SIGNAL,   linewidth=0.7, label="Signal")
        ax_mac.axhline(0, color=C_BORDER, linewidth=0.5)
    else:
        ax_mac.text(0.5, 0.5, "数据不足", transform=ax_mac.transAxes,
                    color=C_TEXT, ha="center", va="center", fontsize=7)

    # ── X 轴刻度 ─────────────────────────────────────────────
    _set_xticks(ax_mac, df.index, period, x)
    plt.setp(ax_k.get_xticklabels(), visible=False)
    plt.setp(ax_vol.get_xticklabels(), visible=False)

    # ── Y 轴格式 ──────────────────────────────────────────────
    for ax in [ax_k, ax_vol, ax_mac]:
        ax.yaxis.set_major_formatter(
            ticker.FuncFormatter(lambda val, _: format_price(val))
        )
        ax.tick_params(axis="y", labelsize=6)

    ax_vol.yaxis.set_major_formatter(
        ticker.FuncFormatter(lambda val, _: format_volume(val))
    )
    ax_vol.tick_params(axis="y", labelsize=5)

    # ── 周期标题（右上角）──────────────────────────────────────
    ax_k.text(0.99, 0.97, period, transform=ax_k.transAxes,
              color="#aaddff", fontsize=8, ha="right", va="top",
              fontweight="bold")

    # ── 均线图例（左上）──────────────────────────────────────
    if not is_minute and len(PERIOD_MAS.get(period, [])) > 0:
        handles, labels = ax_k.get_legend_handles_labels()
        if handles:
            leg = ax_k.legend(handles[:6], labels[:6], loc="upper left",
                              fontsize=5, framealpha=0, handlelength=1.5,
                              ncol=3, columnspacing=0.5, labelspacing=0.1,
                              borderpad=0.2)
            for text in leg.get_texts():
                text.set_color(C_TEXT)

    # x 轴范围
    if len(x) > 0:
        ax_k.set_xlim(-0.5, len(x) - 0.5)


def _set_xticks(ax, index, period: str, x):
    """设置 X 轴时间刻度"""
    n = len(index)
    if n == 0:
        return

    if period == "分时":
        # 显示时:分
        step = max(1, n // 6)
        ticks = list(range(0, n, step))
        labels = [index[i].strftime("%H:%M") for i in ticks]
    elif period == "日线":
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        labels = [index[i].strftime("%y/%m") for i in ticks]
    elif period in ("周线", "月线"):
        step = max(1, n // 6)
        ticks = list(range(0, n, step))
        labels = [index[i].strftime("%y/%m") for i in ticks]
    else:
        step = max(1, n // 5)
        ticks = list(range(0, n, step))
        labels = [index[i].strftime("%Y") for i in ticks]

    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=5, color=C_TEXT, rotation=0)


# ══════════════════════════════════════════════════════════════════
#  整体图表
# ══════════════════════════════════════════════════════════════════

def generate_chart(stock_data: dict, output_dir: str = None) -> str:
    """
    生成整张多周期 K 线图并保存
    stock_data: fetch_stock_data() 的返回值
    返回: 保存路径
    """
    info    = stock_data["info"]
    periods = stock_data["periods"]
    display = info["display"]
    name    = info.get("name", display)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 画布 ──────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 12), dpi=120, facecolor=C_BG)
    fig.patch.set_facecolor(C_BG)

    # 外层 GridSpec：2行×3列 + 顶部标题行
    outer = GridSpec(
        2, 3,
        hspace=0.25,
        wspace=0.12,
        left=0.02, right=0.98,
        top=0.93, bottom=0.03,
    )

    # ── 顶部标题 ──────────────────────────────────────────────
    fig.text(
        0.5, 0.97,
        f"{name}  {display}",
        ha="center", va="top",
        color=C_TITLE, fontsize=16, fontweight="bold",
    )
    fig.text(
        0.98, 0.97,
        now_str,
        ha="right", va="top",
        color="#888888", fontsize=9,
    )

    # ── 绘制 6 个周期 ─────────────────────────────────────────
    positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    for idx, period in enumerate(PERIODS_ORDER):
        row, col = positions[idx]
        df = periods.get(period, pd.DataFrame())
        is_minute = (period == "分时")
        _plot_period(fig, outer[row, col], df, period, is_minute=is_minute)

    # ── 保存 ──────────────────────────────────────────────────
    save_dir = output_dir or OUTPUT_DIR
    os.makedirs(save_dir, exist_ok=True)

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    code = info["raw"]
    name_part = info.get("name", "")
    # 去掉文件名中的非法字符，避免路径问题
    safe_name = name_part.replace("/", "").replace("\\", "").replace(":", "").replace("*", "").replace("?", "").replace('"', "").replace("<", "").replace(">", "").replace("|", "").strip()
    if safe_name:
        filename = f"{code}-{safe_name}_{ts}.png"
    else:
        filename = f"{code}_{ts}.png"
    filepath = os.path.join(save_dir, filename)

    plt.savefig(filepath, dpi=120, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)

    print(f"  [图表] 已保存: {filepath}")
    return filepath


# ══════════════════════════════════════════════════════════════════
#  批量生成
# ══════════════════════════════════════════════════════════════════

def generate_charts_batch(stock_data_list: list, output_dir: str = None) -> list:
    """批量生成，返回所有文件路径"""
    paths = []
    for stock_data in stock_data_list:
        try:
            path = generate_chart(stock_data, output_dir)
            paths.append(path)
        except Exception as e:
            display = stock_data.get("info", {}).get("display", "?")
            print(f"  [图表] 生成失败 {display}: {e}")
    return paths
