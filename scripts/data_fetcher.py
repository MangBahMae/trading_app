"""
Binance 공개 REST API에서 캔들을 가져와 로컬 캐시를 관리한다.

- 인증 불필요 (klines는 공개 시세 데이터)
- 캐시가 없으면 config.HISTORY_START부터 지금까지 전체를 페이지네이션으로 받아오고,
  있으면 마지막 캔들 이후분만 증분으로 받아와서 이어붙인다
  (data/merged/{SYMBOL}_{INTERVAL}_dashboard.parquet 에 캐시)
- 하루 한 번, 새 봉이 마감된 뒤 갱신되는 정도면 충분 (요청 스펙)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from config import SYMBOL, INTERVAL, HISTORY_START, DASHBOARD_CACHE_PATH

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
]
# 신호 계산에 실제로 쓰이는 컬럼만 유지 (Binance API의 나머지 필드는 타입이
# 소스마다 달라서(zip=int, API=str) 합칠 때 충돌하므로 애초에 버림)
KEEP_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
NUMERIC_COLS = ["open", "high", "low", "close", "volume"]


def fetch_klines(symbol: str, interval: str, start_time_ms: int | None = None, limit: int = 1000) -> pd.DataFrame:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time_ms is not None:
        params["startTime"] = start_time_ms

    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
    resp.raise_for_status()
    rows = resp.json()

    if not rows:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["open_time"] = pd.to_datetime(df["open_time"].astype(np.int64), unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"].astype(np.int64), unit="ms", utc=True)
    for col in NUMERIC_COLS:
        df[col] = df[col].astype(float)
    return df[KEEP_COLS]


def fetch_full_history(symbol: str, interval: str, start_date: str) -> pd.DataFrame:
    """Binance API를 여러 번 나눠 호출(페이지네이션)해서 start_date부터 지금까지
    전체 이력을 받아온다. 캐시가 없을 때(최초 적재) 사용 - zip 아카이브에
    의존하지 않으므로 zip이 커버하지 않는 과거 구간(예: 2022~2024)도 받을 수 있다."""
    start_ms = int(pd.Timestamp(start_date, tz="UTC").timestamp() * 1000)
    frames = []
    while True:
        batch = fetch_klines(symbol, interval, start_time_ms=start_ms, limit=1000)
        if batch.empty:
            break
        frames.append(batch)
        if len(batch) < 1000:
            break
        start_ms = int(batch["close_time"].iloc[-1].timestamp() * 1000) + 1

    if not frames:
        return pd.DataFrame(columns=KEEP_COLS)
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)


def ensure_fresh_data(force: bool = False) -> pd.DataFrame:
    """
    캐시가 있으면 그걸 기준으로 증분 갱신, 없으면 HISTORY_START부터 전체를
    Binance API로 받아와서 새로 캐시를 만든다.
    """
    if DASHBOARD_CACHE_PATH.exists():
        df = pd.read_parquet(DASHBOARD_CACHE_PATH)
    else:
        df = fetch_full_history(SYMBOL, INTERVAL, HISTORY_START)

    last_open_time = df["open_time"].max()
    now_utc = pd.Timestamp.now(tz="UTC")
    # 일봉 기준: 마지막으로 "마감된" 캔들의 open_time은 오늘 UTC 자정보다 하루 전이어야 함
    latest_closed_open = now_utc.floor("D") - pd.Timedelta(days=1)

    if not force and last_open_time >= latest_closed_open:
        return df  # 이미 최신

    start_ms = int((last_open_time + pd.Timedelta(milliseconds=1)).timestamp() * 1000)
    new_rows = fetch_klines(SYMBOL, INTERVAL, start_time_ms=start_ms)

    if not new_rows.empty:
        df = pd.concat([df, new_rows], ignore_index=True)
        df = df.drop_duplicates(subset="open_time", keep="last").sort_values("open_time").reset_index(drop=True)

    # 룩어헤드 금지 원칙: 아직 마감되지 않은(진행 중인) 캔들은 절대 포함하지 않는다.
    # Binance API는 오늘 자정부터 지금까지의 미완성 캔들도 함께 돌려주므로 걸러낸다.
    df = df[df["close_time"] <= pd.Timestamp.now(tz="UTC")].reset_index(drop=True)

    DASHBOARD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DASHBOARD_CACHE_PATH, index=False)
    return df


if __name__ == "__main__":
    df = ensure_fresh_data(force=True)
    print(f"{SYMBOL} {INTERVAL}: {len(df)}개 캔들, {df['open_time'].min()} ~ {df['open_time'].max()}")
