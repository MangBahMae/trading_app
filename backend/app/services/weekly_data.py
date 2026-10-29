"""
주봉(1w) 데이터 수집과 캐시 - 일봉 data_fetcher.py는 건드리지 않고 그 안의 fetch 함수만 가져다 쓴다.

- Binance 1w 캔들: 월요일 00:00 UTC에 열려 일요일 23:59:59.999 UTC에 마감한다.
- 캐시 구조는 일봉과 같다: data/merged/BTCUSDT_1w_dashboard.parquet, 캐시가 없으면 전체를 페이지네이션으로 받고
  있으면 마지막 캔들 이후분만 증분으로 이어붙인다. 아직 마감되지 않은 주(진행 중)는 어떤 경로에서도 포함하지 않는다.
- EMA200(200주 = 약 4년)이 2022년부터 유효하도록 캐시는 Binance가 가진 첫 주봉(2017-08)부터 받는다.
  화면/신호는 WEEKLY_DISPLAY_START(2022-01-03, 2022-01-01 이후 첫 월요일)부터만 쓴다.
"""
import pandas as pd

from config import MERGED_DIR, SYMBOL
from data_fetcher import fetch_full_history, fetch_klines

WEEKLY_INTERVAL = "1w"
WEEKLY_CACHE_START = "2017-08-01"       # EMA 워밍업용으로 캐시에 넣는 시작일 (Binance 첫 주봉은 2017-08-14)
WEEKLY_DISPLAY_START = "2022-01-03"     # 화면/신호의 시작 주(월요일) - 일봉 HISTORY_START(2022-01-01) 이후 첫 주봉
WEEKLY_CACHE_PATH = MERGED_DIR / f"{SYMBOL}_{WEEKLY_INTERVAL}_dashboard.parquet"
WEEK = pd.Timedelta(days=7)


def latest_closed_week_open(now_utc: pd.Timestamp) -> pd.Timestamp:
    """지금 기준으로 마지막으로 마감된 주봉의 open_time(월요일 00:00 UTC) = 이번 주 월요일 - 7일."""
    this_monday = now_utc.floor("D") - pd.Timedelta(days=now_utc.weekday())
    return this_monday - WEEK


def ensure_fresh_weekly_data(force: bool = False) -> pd.DataFrame:
    """주봉 캐시를 최신으로 맞춰 반환(캐시 시작일부터 마지막으로 마감된 주까지). 일봉 ensure_fresh_data와 같은 구조."""
    cache_existed = WEEKLY_CACHE_PATH.exists()
    if cache_existed:
        df = pd.read_parquet(WEEKLY_CACHE_PATH)
    else:
        df = fetch_full_history(SYMBOL, WEEKLY_INTERVAL, WEEKLY_CACHE_START)

    now_utc = pd.Timestamp.now(tz="UTC")
    needs_incremental_fetch = force or df["open_time"].max() < latest_closed_week_open(now_utc)

    if needs_incremental_fetch:
        start_ms = int((df["open_time"].max() + pd.Timedelta(milliseconds=1)).timestamp() * 1000)
        new_rows = fetch_klines(SYMBOL, WEEKLY_INTERVAL, start_time_ms=start_ms)
        if not new_rows.empty:
            df = pd.concat([df, new_rows], ignore_index=True)
            df = df.drop_duplicates(subset="open_time", keep="last").sort_values("open_time").reset_index(drop=True)

    # 룩어헤드 금지: 아직 마감되지 않은(진행 중인) 주봉은 모든 경로에서 걸러낸다.
    df = df[df["close_time"] <= pd.Timestamp.now(tz="UTC")].reset_index(drop=True)

    if not cache_existed or needs_incremental_fetch:
        WEEKLY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(WEEKLY_CACHE_PATH, index=False)
    return df


if __name__ == "__main__":
    out = ensure_fresh_weekly_data(force=True)
    print(f"{SYMBOL} {WEEKLY_INTERVAL}: {len(out)}개 캔들, {out['open_time'].min()} ~ {out['open_time'].max()}")
