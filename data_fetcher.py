"""
数据获取模块
支持 A股（沪深）、港股、美股
数据源：东方财富 API（主）、新浪财经 API（备）

增强特性：
- Session 连接复用
- 请求重试（指数退避）
- 本地 JSON 缓存
- 改进日志（INFO/WARN/ERROR）
- 离线模式支持
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import re
import json
import os
import random
from functools import wraps

# ── 请求头（模拟浏览器）────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.eastmoney.com/",
}

# ── 缓存配置 ────────────────────────────────────────────
CACHE_DIR = ".cache/kline"
CACHE_VALIDITY_HOURS = 24

# ── Session 全局复用 ────────────────────────────────────────────
_session = None

def _get_session():
    """获取或创建 requests.Session（连接池复用）"""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
        # 配置超时：连接 5s，读取 15s
        _session.timeout = (5, 15)
    return _session


# ══════════════════════════════════════════════════════════════════
#  重试装饰器与缓存函数
# ══════════════════════════════════════════════════════════════════

def _retry_on_failure(max_retries=3, backoff_base=2):
    """
    重试装饰器：自动重试网络请求
    可重试错误：超时、连接错误、5xx
    不可重试：4xx、解析错误
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.Timeout, requests.ConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = backoff_base ** attempt
                        print(f"    [WARN] 网络错误，{wait_time}s 后重试 ({attempt+1}/{max_retries}): {type(e).__name__}")
                        time.sleep(wait_time)
                    else:
                        print(f"    [ERROR] 网络请求失败（已重试 {max_retries} 次），即将使用缓存")
                except requests.HTTPError as e:
                    if e.response.status_code >= 500:
                        # 5xx 可重试
                        last_exception = e
                        if attempt < max_retries - 1:
                            wait_time = backoff_base ** attempt
                            print(f"    [WARN] 服务器错误 (HTTP {e.response.status_code})，{wait_time}s 后重试 ({attempt+1}/{max_retries})")
                            time.sleep(wait_time)
                        else:
                            print(f"    [ERROR] 服务器持续返回错误，即将使用缓存")
                    else:
                        # 4xx 不可重试
                        print(f"    [ERROR] 请求参数错误 (HTTP {e.response.status_code})，不重试")
                        raise
                except (ValueError, json.JSONDecodeError) as e:
                    # 解析错误不可重试
                    print(f"    [ERROR] 响应数据解析失败，不重试: {e}")
                    raise
                except Exception as e:
                    # 其他异常：记录但不重试
                    print(f"    [ERROR] 未知错误，不重试: {e}")
                    raise
            
            # 所有重试都失败
            raise last_exception or requests.RequestException("所有重试均失败")
        return wrapper
    return decorator


def _init_cache_dir():
    """初始化缓存目录"""
    os.makedirs(CACHE_DIR, exist_ok=True)


def _get_cache_path(em_code: str, period: str) -> str:
    """获取缓存文件路径"""
    code_dir = os.path.join(CACHE_DIR, em_code.replace(".", "_"))
    return os.path.join(code_dir, f"{period}.json")


def _save_cache(em_code: str, period: str, df: pd.DataFrame):
    """将 DataFrame 保存到本地缓存"""
    if df.empty:
        return
    
    try:
        _init_cache_dir()
        code_dir = os.path.join(CACHE_DIR, em_code.replace(".", "_"))
        os.makedirs(code_dir, exist_ok=True)
        
        cache_file = _get_cache_path(em_code, period)
        
        # DataFrame → JSON 格式
        cache_data = {
            "updated_at": datetime.now().isoformat(),
            "data": [
                [idx.isoformat(), row["open"], row["close"], row["high"], row["low"], 
                 row["volume"], row["amount"], row.get("chg_pct", 0)]
                for idx, row in df.iterrows()
            ]
        }
        
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
    
    except Exception as e:
        print(f"    [WARN] 缓存保存失败: {e}")


def _load_cache(em_code: str, period: str) -> pd.DataFrame:
    """从本地缓存读取 DataFrame"""
    try:
        cache_file = _get_cache_path(em_code, period)
        if not os.path.exists(cache_file):
            return pd.DataFrame()
        
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        
        # 检查缓存有效期
        updated_at = datetime.fromisoformat(cache_data["updated_at"])
        age_hours = (datetime.now() - updated_at).total_seconds() / 3600
        
        if age_hours > CACHE_VALIDITY_HOURS:
            print(f"    [WARN] 缓存已过期（{age_hours:.1f}h 前更新），跳过使用")
            return pd.DataFrame()
        
        # JSON → DataFrame
        rows = []
        for item in cache_data["data"]:
            rows.append({
                "date":    item[0],
                "open":    item[1],
                "close":   item[2],
                "high":    item[3],
                "low":     item[4],
                "volume":  item[5],
                "amount":  item[6],
                "chg_pct": item[7],
            })
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        
        print(f"    [INFO] 使用缓存数据（更新于 {updated_at.strftime('%Y-%m-%d %H:%M:%S')}）")
        return df
    
    except Exception as e:
        print(f"    [WARN] 缓存读取失败: {e}")
        return pd.DataFrame()


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


@_retry_on_failure(max_retries=3, backoff_base=2)
def _fetch_em_kline_api(em_code: str, klt: int, limit: int = 200) -> pd.DataFrame:
    """
    [内部] 从东方财富获取 K 线数据（带重试）
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
    
    session = _get_session()
    resp = session.get(url, params=params, timeout=(5, 15))
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


def _fetch_em_kline(em_code: str, klt: int, limit: int = 200, offline: bool = False) -> pd.DataFrame:
    """
    从东方财富获取 K 线数据（支持缓存和离线模式）
    """
    # 周期名称映射
    period_name = {101: "day", 102: "week", 103: "month", 104: "quarter", 106: "year", 1: "1min"}
    period = period_name.get(klt, f"klt{klt}")
    
    # 离线模式：只读缓存
    if offline:
        df = _load_cache(em_code, period)
        if df.empty:
            print(f"    [ERROR] 离线模式下无缓存数据可用")
        return df
    
    # 在线模式：尝试 API，失败则使用缓存
    try:
        df = _fetch_em_kline_api(em_code, klt, limit)
        if not df.empty:
            _save_cache(em_code, period, df)
        return df
    except Exception as e:
        print(f"    [ERROR] API 请求失败: {type(e).__name__}")
        print(f"    [INFO] 尝试从缓存恢复...")
        df = _load_cache(em_code, period)
        if df.empty:
            print(f"    [ERROR] 无可用缓存，请检查网络连接或重试")
        return df


@_retry_on_failure(max_retries=3, backoff_base=2)
def _fetch_em_minute_api(em_code: str) -> pd.DataFrame:
    """
    [内部] 获取分时数据（当日，带重试）
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
    
    session = _get_session()
    resp = session.get(url, params=params, timeout=(5, 15))
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


def _fetch_em_minute(em_code: str, offline: bool = False) -> pd.DataFrame:
    """
    获取分时数据（当日，支持缓存和离线模式）
    """
    period = "minute"
    
    # 离线模式：只读缓存
    if offline:
        df = _load_cache(em_code, period)
        if df.empty:
            print(f"    [ERROR] 离线模式下无缓存数据可用")
        return df
    
    # 在线模式：尝试 API，失败则使用缓存
    try:
        df = _fetch_em_minute_api(em_code)
        if not df.empty:
            _save_cache(em_code, period, df)
        return df
    except Exception as e:
        print(f"    [ERROR] API 请求失败: {type(e).__name__}")
        print(f"    [INFO] 尝试从缓存恢复...")
        df = _load_cache(em_code, period)
        if df.empty:
            print(f"    [ERROR] 无可用缓存，请检查网络连接或重试")
        return df


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


def fetch_stock_data(code: str, offline: bool = False) -> dict:
    """
    获取一只股票所有周期的数据
    参数:
        code: 股票代码
        offline: 离线模式（仅使用本地缓存）
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
    mode_str = "（离线模式）" if offline else ""
    print(f"\n[数据] 获取 {info['display']} ({info['market']}) {mode_str}...")

    result = {"info": info, "periods": {}}

    for period, (ptype, klt) in PERIOD_MAP.items():
        limit = PERIOD_LIMIT[period]
        print(f"  → {period} ...", end=" ", flush=True)

        if ptype == "minute":
            df = _fetch_em_minute(em_code, offline=offline)
        elif ptype == "quarter":
            # 先取月线再聚合
            df_month = _fetch_em_kline(em_code, EM_KLT["month"], limit=limit * 3, offline=offline)
            df = _aggregate_quarter(df_month)
        else:
            df = _fetch_em_kline(em_code, klt, limit=limit, offline=offline)

        if df.empty:
            print(f"无数据")
        else:
            print(f"OK ({len(df)} 条)")

        result["periods"][period] = df

        # 随机延迟（避免规律被检测）
        delay = random.uniform(0.3, 0.5)
        time.sleep(delay)

    # 尝试获取股票名称（新浪接口，离线模式下跳过）
    if not offline:
        result["info"]["name"] = _fetch_name(info)
    else:
        result["info"]["name"] = info["display"]
    
    return result


@_retry_on_failure(max_retries=2, backoff_base=2)
def _fetch_name_api(info: dict) -> str:
    """[内部] 通过新浪接口获取股票名称（带重试）"""
    url = f"https://hq.sinajs.cn/list={info['sina_code']}"
    session = _get_session()
    resp = session.get(url, headers={**HEADERS, "Referer": "https://finance.sina.com.cn/"}, timeout=(5, 10))
    resp.encoding = "gbk"
    text = resp.text
    # 格式: var hq_str_sh600036="招商银行,...";
    match = re.search(r'"([^"]+)"', text)
    if match:
        parts = match.group(1).split(",")
        if parts and parts[0]:
            return parts[0]
    return None


def _fetch_name(info: dict) -> str:
    """获取股票名称（支持重试）"""
    try:
        name = _fetch_name_api(info)
        if name:
            return name
    except Exception as e:
        print(f"    [WARN] 获取股票名称失败: {type(e).__name__}")
    
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
