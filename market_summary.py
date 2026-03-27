"""
market_summary.py
获取 A 股三市（沪/深/京）收盘概况：
  - 主要指数（上证/深证/创业板/科创50/北证50）最新点位、涨跌幅、成交额
  - 各市场上涨/下跌/平盘家数
  - 全市场合计成交额
  - 近 30 个交易日全市场成交额历史序列（用于折线图）
返回结构化 dict，供 report_generator 生成 HTML 点评区域使用
"""

import requests
from datetime import datetime


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.eastmoney.com/",
}

# 指数配置：(secid, 简称)
_INDEX_SECIDS = [
    ("1.000001",  "上证指数"),
    ("0.399001",  "深证成指"),
    ("0.399006",  "创业板指"),
    ("1.000688",  "科创50"),
    ("0.899050",  "北证50"),
]

# 历史K线 secid（沪/深/北，用于求和全市场成交额）
_HIST_SECIDS = ["1.000001", "0.399001", "0.899050"]


def _fmt_amount(yuan: float) -> str:
    """将元转为 xxxx亿 / xx.x万亿"""
    yi = yuan / 1e8
    if yi >= 10000:
        return f"{yi/10000:.2f}万亿"
    return f"{yi:.0f}亿"


def _fetch_hist_klines(secid: str, days: int = 35) -> dict:
    """
    拉取单个指数的日K线，返回 {date: amount_yuan} 字典
    K线字段：日期,开,收,高,低,成交量,成交额,...
    """
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?cb=&secid={secid}&ut=bd1d9ddb04089700cf9c27f6f7426281"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=1&end=20500101&lmt={days}"
        f"&_={int(datetime.now().timestamp()*1000)}"
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        klines = resp.json().get("data", {}).get("klines", [])
        result = {}
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 7:
                date   = parts[0]          # "2026-03-26"
                amount = float(parts[6])   # 成交额（元）
                result[date] = amount
        return result
    except Exception:
        return {}


def fetch_amount_history(days: int = 30) -> list:
    """
    返回最近 days 个交易日的全市场成交额列表（沪+深+北），
    格式：[{"date": "2026-03-26", "amount_yi": 8213.5}, ...]
    按日期升序排列。
    """
    # 多拉几条保证够 days 条（节假日等原因）
    fetch_n = days + 8

    # 并行拉取三市历史数据
    maps = [_fetch_hist_klines(sid, fetch_n) for sid in _HIST_SECIDS]

    # 取三者日期交集（只有三市都有数据的交易日才汇总）
    all_dates = set(maps[0].keys())
    for m in maps[1:]:
        all_dates |= m.keys()   # 用并集，缺的补0

    sorted_dates = sorted(all_dates)[-days:]   # 取最近 days 条

    result = []
    for date in sorted_dates:
        total = sum(m.get(date, 0.0) for m in maps)
        result.append({
            "date":      date,
            "amount_yi": round(total / 1e8, 1),
        })
    return result


def fetch_sector_data(top_n: int = 5) -> dict:
    """
    获取板块涨跌 + 主力资金流向排行
    返回:
    {
      "concept_up":   [{"name":..,"chg_pct":..,"amount":..,"zljlr":..}, ...],  # 涨幅TOP5概念
      "concept_down": [...],   # 跌幅TOP5概念
      "industry_up":  [...],   # 涨幅TOP5行业
      "industry_down":[...],   # 跌幅TOP5行业
      "fund_in":      [...],   # 主力净流入TOP5板块（排除指数型板块）
      "fund_out":     [...],   # 主力净流出TOP5板块
      "sh_zljlr":     "-468亿", # 沪市主力净流入
      "sz_zljlr":     "-455亿", # 深市主力净流入
      "total_zljlr":  "-923亿", # 全市场主力净流入
    }
    """
    res = {
        "concept_up": [], "concept_down": [],
        "industry_up": [], "industry_down": [],
        "fund_in": [], "fund_out": [],
        "sh_zljlr": "-", "sz_zljlr": "-", "total_zljlr": "-",
    }

    # 过滤掉融资融券/MSCI/沪股通等指数型板块关键词
    _SKIP_KEYWORDS = ("融资融券", "MSCI", "沪股通", "深股通", "富时", "标准普尔",
                      "道琼斯", "昨日", "连板", "涨停", "打板",
                      "HS300", "深成500", "机构重仓", "社保重仓", "央国企",
                      "深股通", "沪深300", "上证50", "中证")

    def _is_valid(name):
        return not any(k in name for k in _SKIP_KEYWORDS)

    def _fetch_clist(t, fid, po, pz):
        """东方财富板块列表接口"""
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn=1&pz={pz}&po={po}&np=1"
            f"&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2"
            f"&fid={fid}&fs=m:90+t:{t}"
            f"&fields=f2,f3,f4,f12,f14,f20,f62"
            f"&_={int(datetime.now().timestamp()*1000)}"
        )
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10)
            r.raise_for_status()
            return r.json().get("data", {}).get("diff", []) or []
        except Exception:
            return []

    def _parse(items, n):
        out = []
        for d in items:
            name = d.get("f14", "")
            if not _is_valid(name):
                continue
            chg = d.get("f3")
            amt = d.get("f20") or 0
            zl  = d.get("f62") or 0
            out.append({
                "name":    name,
                "chg_pct": chg,
                "amount":  _fmt_amount(amt) if amt else "-",
                "zljlr":   zl,
                "zljlr_str": _fmt_amount(abs(zl)) if zl else "-",
            })
            if len(out) >= n:
                break
        return out

    # ── 概念板块涨跌（t=3）── po=1降序=涨幅榜，po=0升序=跌幅榜
    res["concept_up"]   = _parse(_fetch_clist(3, "f3", 1, top_n + 15), top_n)
    res["concept_down"] = _parse(_fetch_clist(3, "f3", 0, top_n + 15), top_n)

    # ── 行业板块涨跌（t=2）──
    res["industry_up"]   = _parse(_fetch_clist(2, "f3", 1, top_n + 5), top_n)
    res["industry_down"] = _parse(_fetch_clist(2, "f3", 0, top_n + 5), top_n)

    # ── 主力净流入/流出概念板块（按 f62 排序）── po=1降序=流入最多，po=0升序=流出最多
    fund_all = _fetch_clist(3, "f62", 1, top_n + 20)  # 净流入降序（最多在前）
    res["fund_in"]  = _parse(fund_all, top_n)

    fund_out_all = _fetch_clist(3, "f62", 0, top_n + 20)  # 净流入升序（负值最大=流出最多）
    res["fund_out"] = _parse(fund_out_all, top_n)

    # ── 三大指数主力净流入 ──
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/ulist.np/get"
            "?fltt=2&invt=2&fields=f2,f3,f12,f14,f62,f184"
            "&secids=1.000001,0.399001,0.399006"
            "&ut=bd1d9ddb04089700cf9c27f6f7426281"
        )
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        diff = r.json().get("data", {}).get("diff", [])
        sh_zl = sz_zl = 0.0
        for d in diff:
            code = d.get("f12", "")
            zl   = d.get("f62") or 0
            if code == "000001":
                sh_zl = zl
            elif code == "399001":
                sz_zl = zl
        total_zl = sh_zl + sz_zl
        res["sh_zljlr"]    = _fmt_amount(sh_zl)
        res["sz_zljlr"]    = _fmt_amount(sz_zl)
        res["total_zljlr"] = _fmt_amount(total_zl)
        res["sh_zljlr_raw"]    = sh_zl
        res["sz_zljlr_raw"]    = sz_zl
        res["total_zljlr_raw"] = total_zl
    except Exception:
        pass

    return res


def fetch_market_summary() -> dict:
    """
    返回:
    {
      "date":       "2026-03-26",
      "time":       "15:03",
      "indices": [...],
      "market_total_amount": "8213亿",
      "sh_amount": "3516亿",
      "sz_amount": "4641亿",
      "bj_amount": "56亿",
      "sh_up": 817,  "sh_down": 1435,
      "sz_up": 972,  "sz_down": 1844,
      "bj_up": 229,  "bj_down": 68,
      "total_up": 2018, "total_down": 3347,
      "amount_history": [{"date": "2026-02-10", "amount_yi": 9821.3}, ...],  # 近30日
      "sector": { ... },   # 板块涨跌 + 主力资金
      "error": None
    }
    """
    result = {
        "date":  datetime.now().strftime("%Y-%m-%d"),
        "time":  datetime.now().strftime("%H:%M"),
        "indices": [],
        "market_total_amount": "-",
        "sh_amount": "-", "sz_amount": "-", "bj_amount": "-",
        "sh_up": 0, "sh_down": 0, "sz_up": 0, "sz_down": 0,
        "bj_up": 0, "bj_down": 0,
        "total_up": 0, "total_down": 0,
        "amount_history": [],
        "sector": {},
        "error": None,
    }

    try:
        # ── 1. 实时指数快照 ──────────────────────────────────
        secids = ",".join(s for s, _ in _INDEX_SECIDS)
        url = (
            "https://push2.eastmoney.com/api/qt/ulist.np/get"
            f"?fltt=2&invt=2"
            f"&fields=f2,f3,f4,f6,f12,f14,f104,f105,f106"
            f"&secids={secids}"
            f"&ut=bd1d9ddb04089700cf9c27f6f7426281"
            f"&_={int(datetime.now().timestamp()*1000)}"
        )
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        raw_list = resp.json().get("data", {}).get("diff", [])
        code_map = {d["f12"]: d for d in raw_list}

        sh_amount = sz_amount = bj_amount = 0.0
        total_up = total_down = 0

        for secid, name in _INDEX_SECIDS:
            code = secid.split(".")[1]
            d = code_map.get(code)
            if not d:
                continue

            amount_yuan = d.get("f6") or 0
            up   = d.get("f104") or 0
            down = d.get("f105") or 0
            flat = d.get("f106") or 0

            entry = {
                "name":    name,
                "close":   d.get("f2"),
                "chg_pct": d.get("f3"),
                "chg_pt":  d.get("f4"),
                "amount":  _fmt_amount(amount_yuan) if amount_yuan else "-",
                "up":   up,
                "down": down,
                "flat": flat,
            }
            result["indices"].append(entry)

            if code == "000001":
                sh_amount = amount_yuan
                result["sh_up"]   = up
                result["sh_down"] = down
            elif code == "399001":
                sz_amount = amount_yuan
                result["sz_up"]   = up
                result["sz_down"] = down
            elif code == "899050":
                bj_amount = amount_yuan
                result["bj_up"]   = up
                result["bj_down"] = down

            if code in ("000001", "399001"):
                total_up   += up
                total_down += down

        total_up   += result["bj_up"]
        total_down += result["bj_down"]

        total_amount = sh_amount + sz_amount + bj_amount
        result["sh_amount"]           = _fmt_amount(sh_amount) if sh_amount else "-"
        result["sz_amount"]           = _fmt_amount(sz_amount) if sz_amount else "-"
        result["bj_amount"]           = _fmt_amount(bj_amount) if bj_amount else "-"
        result["market_total_amount"] = _fmt_amount(total_amount) if total_amount else "-"
        result["total_up"]            = total_up
        result["total_down"]          = total_down

        # ── 2. 近30日历史成交额 ──────────────────────────────
        result["amount_history"] = fetch_amount_history(30)

        # ── 3. 板块涨跌 + 主力资金流向 ──────────────────────
        result["sector"] = fetch_sector_data(top_n=5)

    except Exception as e:
        result["error"] = str(e)

    return result


if __name__ == "__main__":
    import json
    data = fetch_market_summary()
    print(f"近30日成交额历史：{len(data['amount_history'])} 条")
    for item in data["amount_history"][-5:]:
        print(f"  {item['date']}  {item['amount_yi']:.0f}亿")
    print(json.dumps({k: v for k, v in data.items() if k != "amount_history"},
                     ensure_ascii=False, indent=2))
