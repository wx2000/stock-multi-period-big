"""
主入口脚本 · v1.1
支持命令行参数、文件输入、交互模式
支持生成后自动发送到企业微信/飞书
支持 --send_only 直接复用已有图片发送，不重新拉数据
"""

import argparse
import os
import re
import sys

from data_fetcher import fetch_stock_data
from chart_generator import generate_charts_batch, OUTPUT_DIR


# ── 默认股票列表（可编辑 stocks.txt 替换）──────────────────────
DEFAULT_STOCKS = [
    "000001",  # 平安银行  A股
    "600036",  # 招商银行  A股
    "00700",   # 腾讯控股  港股
    "AAPL",    # 苹果      美股
]


def load_stocks_from_file(path: str) -> list:
    """从文件读取股票列表，每行一个代码，# 开头为注释"""
    if not os.path.exists(path):
        print(f"[警告] 文件不存在: {path}")
        return []
    stocks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 去掉行内注释（# 及之后的内容）
            line = line.split("#")[0].strip()
            if not line:
                continue
            # 支持逗号或空格分隔
            for code in line.replace(",", " ").split():
                if code:
                    stocks.append(code)
    return stocks


def interactive_mode() -> list:
    """交互式输入股票代码"""
    print("\n=== 多周期K线图生成工具（交互模式）===")
    print("请输入股票代码，多个代码用空格或逗号分隔")
    print("支持：A股（如 000001）、港股（如 00700）、美股（如 AAPL）")
    print("直接回车使用默认列表")
    raw = input("\n股票代码: ").strip()
    if not raw:
        print(f"[信息] 使用默认股票列表: {DEFAULT_STOCKS}")
        return DEFAULT_STOCKS
    return [c.strip() for c in raw.replace(",", " ").split() if c.strip()]


def _load_config(config_path: str) -> dict:
    """加载配置文件，返回 dict；文件不存在则返回空 dict"""
    if not os.path.exists(config_path):
        return {}
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        print("[警告] 未安装 PyYAML，无法读取 config.yaml，请运行: pip install pyyaml")
        return {}
    except Exception as e:
        print(f"[警告] 读取配置文件失败: {e}")
        return {}


def _build_notifiers(args, config: dict) -> list:
    """根据命令行参数和配置文件，构建通知器列表"""
    try:
        from notifier import make_notifier, WeCom, Feishu
    except ImportError as e:
        print(f"[警告] 无法加载发送模块: {e}")
        return []

    if args.wecom:
        config.setdefault("wecom", {})
        config["wecom"]["enabled"] = True
        config["wecom"]["webhook_url"] = args.wecom
    if args.feishu:
        config.setdefault("feishu", {})
        config["feishu"]["enabled"] = True
        config["feishu"]["webhook_url"] = args.feishu

    return make_notifier(config)


def _collect_latest_pngs(output_dir: str) -> list:
    """
    从 output_dir 中找出最新一批 PNG。
    策略：取修改时间最新的 PNG，然后圈出与它修改时间相差 ≤ 120 秒的所有 PNG（同批）。
    """
    if not os.path.isdir(output_dir):
        return []

    pngs = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.lower().endswith(".png")
    ]
    if not pngs:
        return []

    # 按修改时间倒序
    pngs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    latest_mtime = os.path.getmtime(pngs[0])

    batch = [p for p in pngs if latest_mtime - os.path.getmtime(p) <= 120]
    batch.sort()
    return batch


def _make_stub_data(img_path: str) -> dict:
    """
    从文件名解析出 code/name，构造轻量 stock_data stub
    仅用于 send_only 模式（无真实行情数据）
    """
    base = os.path.splitext(os.path.basename(img_path))[0]
    parts = base.split("_")
    code_name = "_".join(parts[:-2]) if len(parts) >= 3 else parts[0]

    if "-" in code_name:
        code, name = code_name.split("-", 1)
    else:
        code, name = code_name, code_name

    if re.match(r"^\d{6}$", code):
        market = "A_SH" if code.startswith(("6", "9")) else "A_SZ"
    elif re.match(r"^\d{5}$", code):
        market = "HK"
    else:
        market = "US"

    return {
        "info": {
            "raw":     code,
            "display": code,
            "name":    name,
            "market":  market,
            "price":   None,
            "chg_pct": None,
        },
        "periods": {},
    }


def _do_send(notifiers, saved_paths, all_data, html_path):
    """统一发送逻辑：仅发送 GitHub Pages 链接通知"""
    if not html_path:
        return

    pages_url = "https://stock-multi-period-big.pages.dev/"
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = (
        f"📈 多周期K线图报告已更新\n"
        f"生成时间：{now}\n"
        f"共 {len(saved_paths)} 只股票\n"
        f"点击查看：{pages_url}"
    )

    print("\n" + "=" * 50)
    print("正在发送通知...")
    for notifier_name, notifier in notifiers:
        print(f"\n[{notifier_name}] 发送中...")
        try:
            notifier.send_text(msg)
            print(f"[{notifier_name}] OK 通知发送成功")
        except Exception as e:
            print(f"[{notifier_name}] FAIL 发送失败: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="多周期K线图生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                                # 使用默认列表
  python main.py --stocks 000001 600036 AAPL    # 指定代码
  python main.py --file stocks.txt              # 从文件读取
  python main.py --interactive                  # 交互输入
  python main.py --output D:/charts             # 指定输出目录

  # 生成后发送到企业微信（直接传 URL）
  python main.py --stocks 000001 --wecom "https://qyapi.weixin.qq.com/..."

  # 从 config.yaml 读取通知配置（推荐）
  python main.py --stocks 000001 --notify

  # 复用已有图片直接发送（不重新拉数据）
  python main.py --send_only --notify
  python main.py --send_only output/601600-中国铝业_xxx.png --notify
        """,
    )
    parser.add_argument("--stocks",      nargs="+", help="股票代码列表")
    parser.add_argument("--file",        type=str,  help="股票代码文件路径")
    parser.add_argument("--interactive", action="store_true", help="交互模式")
    parser.add_argument("--output",      type=str,  default=OUTPUT_DIR, help="图片输出目录")
    parser.add_argument("--config",      type=str,
                        default=os.path.join(os.path.dirname(__file__), "config.yaml"),
                        help="配置文件路径（默认: config.yaml）")

    notify_group = parser.add_argument_group("通知发送（可选）")
    notify_group.add_argument("--notify",    action="store_true",
                               help="启用发送（从 config.yaml 读取通知配置）")
    notify_group.add_argument("--wecom",     type=str, metavar="WEBHOOK_URL",
                               help="企业微信 Webhook URL")
    notify_group.add_argument("--feishu",    type=str, metavar="WEBHOOK_URL",
                               help="飞书 Webhook URL")
    notify_group.add_argument("--send_only", dest="send_only", nargs="*", metavar="PNG",
                               help="跳过数据获取，直接发送已有图片。"
                                    "不带参数=自动取最新一批；带参数=指定 PNG 路径列表")

    pages_group = parser.add_argument_group("GitHub Pages（可选）")
    pages_group.add_argument("--no-push", dest="no_push", action="store_true",
                              help="跳过 git push，不更新 GitHub Pages（离线使用时加此参数）")

    args = parser.parse_args()

    # ── 加载通知配置 ──────────────────────────────────────────
    config    = _load_config(args.config)
    notifiers = []
    # 默认始终尝试加载通知配置（config.yaml 里 enabled: true 即生效）
    # 命令行 --wecom / --feishu 可额外覆盖或补充
    notifiers = _build_notifiers(args, config)
    if notifiers:
        print(f"[通知] 已启用渠道: {[n for n, _ in notifiers]}")
    elif args.notify or args.wecom or args.feishu:
        print("[通知] 未找到有效的通知配置")

    # ══════════════════════════════════════════════════════════
    #  --send_only 模式：跳过数据获取，直接发送
    # ══════════════════════════════════════════════════════════
    if args.send_only is not None:
        if args.send_only:
            saved_paths = [
                p for p in args.send_only
                if p.lower().endswith(".png") and os.path.exists(p)
            ]
            if not saved_paths:
                print("[错误] 指定的 PNG 文件不存在或路径有误")
                sys.exit(1)
        else:
            saved_paths = _collect_latest_pngs(args.output)
            if not saved_paths:
                print(f"[错误] {args.output} 目录下没有找到 PNG 文件")
                sys.exit(1)
            print(f"[send_only] 自动选取最新一批 {len(saved_paths)} 张图:")
            for p in saved_paths:
                print(f"  → {p}")

        all_data = [_make_stub_data(p) for p in saved_paths]

        # 尝试找同批次 HTML
        html_path = None
        ts_part = "_".join(
            os.path.splitext(os.path.basename(saved_paths[0]))[0].split("_")[-2:]
        )
        html_candidate = os.path.join(args.output, f"report_{ts_part}.html")
        if os.path.exists(html_candidate):
            html_path = html_candidate
            print(f"[send_only] 对应 HTML 报告: {html_path}")

        if not notifiers:
            print("[send_only] 未配置通知渠道，退出")
            sys.exit(0)

        _do_send(notifiers, saved_paths, all_data, html_path)
        return

    # ══════════════════════════════════════════════════════════
    #  正常模式：拉数据 → 生成图表 → 发送
    # ══════════════════════════════════════════════════════════

    if args.interactive:
        codes = interactive_mode()
    elif args.file:
        codes = load_stocks_from_file(args.file)
        if not codes:
            print("[错误] 文件中没有有效的股票代码")
            sys.exit(1)
    elif args.stocks:
        codes = args.stocks
    else:
        default_file = os.path.join(os.path.dirname(__file__), "stocks.txt")
        if os.path.exists(default_file):
            codes = load_stocks_from_file(default_file)
            print(f"[信息] 从 stocks.txt 读取 {len(codes)} 只股票")
        else:
            codes = DEFAULT_STOCKS
            print(f"[信息] 使用内置默认列表: {codes}")

    if not codes:
        print("[错误] 股票代码列表为空")
        sys.exit(1)

    print(f"\n共 {len(codes)} 只股票: {codes}")
    print(f"输出目录: {args.output}")
    print("=" * 50)

    all_data = []
    for code in codes:
        try:
            data = fetch_stock_data(code)
            all_data.append(data)
        except Exception as e:
            print(f"[错误] 获取 {code} 数据失败: {e}")

    if not all_data:
        print("[错误] 所有股票数据获取失败")
        sys.exit(1)

    print("\n正在生成图表...")
    saved_paths = generate_charts_batch(all_data, output_dir=args.output)

    print("\n" + "=" * 50)
    print(f"[完成] 共生成 {len(saved_paths)} 张图表")
    for p in saved_paths:
        print(f"  → {p}")

    # ── 自动生成 HTML 报告 ─────────────────────────────────────
    html_path = None
    if saved_paths:
        try:
            from report_generator import generate_html_report
            from market_summary import fetch_market_summary
            print("\n[大盘] 正在获取市场概况数据...")
            market_data = fetch_market_summary()
            if market_data.get("error"):
                print(f"[大盘] 获取失败（不影响报告生成）: {market_data['error']}")
            else:
                print(f"[大盘] 获取成功：全市场成交额 {market_data['market_total_amount']}，"
                      f"上涨 {market_data['total_up']} 家，下跌 {market_data['total_down']} 家")
            html_path = generate_html_report(saved_paths, all_data, args.output, market_data)
            print(f"\n[报告] HTML 报告: {html_path}")
        except Exception as e:
            print(f"[警告] HTML 报告生成失败: {e}")

    # ── 推送到 GitHub Pages ───────────────────────────────────
    if html_path and not args.no_push:
        print("\n" + "=" * 50)
        print("正在推送到 GitHub Pages...")
        try:
            from git_push import push_html_to_github
            push_html_to_github(html_path)
        except Exception as e:
            print(f"[警告] GitHub Pages 推送失败: {e}")
            print("       如不需要推送，可加 --no-push 参数跳过")

    # ── 发送通知 ──────────────────────────────────────────────
    if notifiers and saved_paths:
        _do_send(notifiers, saved_paths, all_data, html_path)


if __name__ == "__main__":
    main()
