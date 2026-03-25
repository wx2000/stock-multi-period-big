"""
数据获取模块
支持 A股（沪深）、港股、美股
数据源：东方财富 API（主）、新浪财经 API（备）
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import re

# ── 请求头（模拟浏览器）────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.eastmoney.com/",
}


# ══════════════════════════════════════════════════════════════════
#  股票代码识别与标准化
# ══════════════════════════════════════════════════════════════════

def detect_market(code: str) -> str:
    """
    自动识别股票市场
    返回: 'A_SH' | 'A_SZ' | 'HK' | 'US'
    """
    code = code.strip().upper()

    # 美股：纯字母 1-5 位
    if re.fullmatch(r"[A-Z]{1,5}", code):
        return "US"

    # 港股：5位纯数字（以 0 开头）或 4-5 位数字
    if re.fullmatch(r"0\d{4}", code) or re.fullmatch(r"\d{4,5}", code):
        # 港股一般 5 位且首位为 0，但也有例外；根据范围判断
        num = int(code.lstrip("0") or "0")
        if len(code) == 5 and code[0] == "0":
            return "HK"
        # A股深交所：0/3 开头 6 位
        if re.fullmatch(r"[03]\d{5}", code):
            return "A_SZ"
        # A股上交所：6/5/688 开头
        if re.fullmatch(r"[16]\d{5}", code):
            return "A_SH"
        # 科创板
        if re.fullmatch(r"688\d{3}", code):
            return "A_SH"

    # 6 位数字
    if re.fullmatch(r"\d{6}", code):
        if code.startswith(("6", "5")):
            return "A_SH"
        if code.startswith(("0", "3")):
            return "A_SZ"
        if code.startswith("688"):
            return "A_SH"

    # 默认当 A 股上交所
    return "A_SH"


def normalize_code(code: str) -> dict:
    """
    将用户输入的股票代码标准化
    返回 dict: {raw, market, em_code, sina_code, display}
    """
    code = code.strip().upper()
    market = detect_market(code)

    if market == "A_SH":
        em_code = f"1.{code}"          # 东方财富：1 = 上交所
        sina_code = f"sh{code.lower()}"
        display = f"{code}.SH"
    elif market == "A_SZ":
        em_code = f"0.{code}"          # 东方财富：0 = 深交所
        sina_code = f"sz{code.lower()}"
        display = f"{code}.SZ"
    elif market == "HK":
        em_code = f"116.{code}"        # 东方财富：116 = 港股
        # 补齐 5 位
        padded = code.zfill(5)
        sina_code = f"hk{padded.lower()}"
        display = f"{padded}.HK"
        code = padded
    else:  # US
        em_code = f"105.{code}"        # 东方财富：105 = 纳斯达克（常见），107=NYSE
        sina_code = f"gb_{code.lower()}"
        display = f"{code}.US"

    return {
        "raw": code,
        "market": market,
        "em_code": em_code,
        "sina_code": sina_code,
        "display": display,
    }


# ══════════════════════════════════════════════════════════════════
#  东方财富 K 线 API
# ══════════════════════════════════════════════════════════════════

# klt 周期映射
EM_KLT = {
    "1min":  1,
    "5min":  5,
    "15min": 15,
    "30min": 30,
    "60min": 60,
    "day":   101,
    "week":  102,
    "month": 103,
    "quarter": 104,  # 部分接口支持
    "year":  106,
}

# 复权：0=不复权 1=前复权 2=后复权
FUQUAN = 1


def _fetch_em_kline(em_code: str, klt: int, limit: int = 200) -> pd.DataFrame:
    """
    从东方财富获取 K 线数据
    返回 DataFrame: [date, open, close, high, low, volume, amount, chg_pct]
    """
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid":     em_code,
        "fields1":   "f1,f2,f3,f4,f5,f6",
        "fields2":   "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt":       klt,
        "fqt":       FUQUAN,
        "lmt":       limit,
        "end":       "20500101",
        "beg":       "19900101",
        "_":         int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        klines = data.get("data", {}) or {}
        items = klines.get("klines", [])
        if not items:
            return pd.DataFrame()

        rows = []
        for item in items:
            parts = item.split(",")
            # f51=日期, f52=开, f53=收, f54=高, f55=低, f56=成交量, f57=成交额, f58=振幅, f59=涨跌幅, f60=涨跌额, f61=换手率
            rows.append({
                "date":    parts[0],
                "open":    float(parts[1]),
                "close":   float(parts[2]),
                "high":    float(parts[3]),
                "low":     float(parts[4]),
                "volume":  float(parts[5]),
                "amount":  float(parts[6]),
                "chg_pct": float(parts[8]),
            })

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        return df

    except Exception as e:
        print(f"  [东方财富] 获取失败 em_code={em_code} klt={klt}: {e}")
        return pd.DataFrame()


def _fetch_em_minute(em_code: str) -> pd.DataFrame:
    """
    获取分时数据（当日）
    返回 DataFrame: [date, price, volume, amount, avg_price]
    """
    url = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
    params = {
        "secid":   em_code,
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "iscr":    0,
        "ndays":   1,
        "_":       int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        trends = (data.get("data") or {}).get("trends", [])
        if not trends:
            return pd.DataFrame()

        rows = []
        for item in trends:
            parts = item.split(",")
            rows.append({
                "date":      pd.to_datetime(parts[0]),
                "price":     float(parts[1]),
                "volume":    float(parts[2]),
                "amount":    float(parts[3]),
                "avg_price": float(parts[5]),
            })

        df = pd.DataFrame(rows)
        df.set_index("date", inplace=True)
        # 补充 OHLC（用于蜡烛图兼容，分时图用 price）
        df["open"]  = df["price"]
        df["high"]  = df["price"]
        df["low"]   = df["price"]
        df["close"] = df["price"]
        return df

    except Exception as e:
        print(f"  [东方财富分时] 获取失败 em_code={em_code}: {e}")
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════
#  季线：由月线聚合
# ══════════════════════════════════════════════════════════════════

def _aggregate_quarter(df_month: pd.DataFrame) -> pd.DataFrame:
    """将月线数据聚合为季线（兼容 pandas 0.24+）"""
    if df_month.empty:
        return pd.DataFrame()
    df = df_month.copy()
    # 按季度分组（兼容旧版 pandas）
    df["quarter"] = df.index.to_period("Q")

    # 旧版 pandas groupby 不支持命名聚合，用旧写法
    agg = df.groupby("quarter").agg({
        "open":   "first",
        "close":  "last",
        "high":   "max",
        "low":    "min",
        "volume": "sum",
        "amount": "sum",
    })
    agg.index = agg.index.to_timestamp()
    # 涨跌幅
    agg["chg_pct"] = agg["close"].pct_change() * 100
    agg["chg_pct"].fillna(0, inplace=True)
    return agg


# ══════════════════════════════════════════════════════════════════
#  对外主接口
# ══════════════════════════════════════════════════════════════════

PERIOD_MAP = {
    "分时":   ("minute", None),
    "日线":   ("kline", EM_KLT["day"]),
    "周线":   ("kline", EM_KLT["week"]),
    "月线":   ("kline", EM_KLT["month"]),
    "季线":   ("quarter", None),
    "年线":   ("kline", EM_KLT["year"]),
}

# 每个周期默认拉取的 bar 数量
PERIOD_LIMIT = {
    "分时": 240,
    "日线": 250,
    "周线": 200,
    "月线": 120,
    "季线": 60,   # 由月线聚合
    "年线": 30,
}


def fetch_stock_data(code: str) -> dict:
    """
    获取一只股票所有周期的数据
    返回:
        {
          "info": {display, market, name},
          "periods": {
              "分时": DataFrame,
              "日线": DataFrame,
              ...
          }
        }
    """
    info = normalize_code(code)
    em_code = info["em_code"]
    print(f"\n[数据] 获取 {info['display']} ({info['market']}) ...")

    result = {"info": info, "periods": {}}

    for period, (ptype, klt) in PERIOD_MAP.items():
        limit = PERIOD_LIMIT[period]
        print(f"  → {period} ...", end=" ", flush=True)

        if ptype == "minute":
            df = _fetch_em_minute(em_code)
        elif ptype == "quarter":
            # 先取月线再聚合
            df_month = _fetch_em_kline(em_code, EM_KLT["month"], limit=limit * 3)
            df = _aggregate_quarter(df_month)
        else:
            df = _fetch_em_kline(em_code, klt, limit=limit)

        if df.empty:
            print(f"无数据")
        else:
            print(f"OK ({len(df)} 条)")

        result["periods"][period] = df

        time.sleep(0.2)  # 礼貌性延迟，避免被封

    # 尝试获取股票名称（新浪接口）
    result["info"]["name"] = _fetch_name(info)
    return result


def _fetch_name(info: dict) -> str:
    """通过新浪接口获取股票名称"""
    try:
        url = f"https://hq.sinajs.cn/list={info['sina_code']}"
        resp = requests.get(url, headers={**HEADERS, "Referer": "https://finance.sina.com.cn/"}, timeout=5)
        resp.encoding = "gbk"
        text = resp.text
        # 格式: var hq_str_sh600036="招商银行,...";
        match = re.search(r'"([^"]+)"', text)
        if match:
            parts = match.group(1).split(",")
            if parts and parts[0]:
                return parts[0]
    except Exception:
        pass
    return info["display"]


# ══════════════════════════════════════════════════════════════════
#  测试
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 快速测试
    for test_code in ["000001", "00700", "AAPL"]:
        data = fetch_stock_data(test_code)
        print(f"\n{data['info']['display']} - {data['info']['name']}")
        for period, df in data["periods"].items():
            print(f"  {period}: {len(df)} 条")
