"""
주봉 데이터 수집/캐시 (weekly_data) - 네트워크 없이 fetch 함수를 가짜로 바꿔서 확인한다.

- 캐시가 없으면 WEEKLY_CACHE_START부터 전체를 받아 저장, 있으면 마지막 캔들 이후만 증분으로 이어붙인다
- 아직 마감되지 않은 주(진행 중)는 어떤 경로에서도 결과/캐시에 들어가지 않는다
- 이미 최신이면 요청이 없다
- 마지막으로 마감된 주의 open_time 계산(월요일 00:00 UTC, 일요일 23:59:59.999 UTC 마감)
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

import weekly_data  # noqa: E402

WEEK = pd.Timedelta(days=7)


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def week_rows(opens):
    """open_time 목록 -> data_fetcher.KEEP_COLS 모양 DataFrame (마감 시각 = open + 7일 - 1ms)."""
    return pd.DataFrame({
        "open_time": opens, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0,
        "close_time": [o + WEEK - pd.Timedelta(milliseconds=1) for o in opens],
    })


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(weekly_data, "WEEKLY_CACHE_PATH", tmp_path / "BTCUSDT_1w_dashboard.parquet")
    calls = {"full": [], "incr": []}
    now = pd.Timestamp.now(tz="UTC")
    last_closed = weekly_data.latest_closed_week_open(now)
    in_progress = last_closed + WEEK                      # 아직 안 끝난 주

    def full(symbol, interval, start_date):
        calls["full"].append((symbol, interval, start_date))
        return week_rows([last_closed - 3 * WEEK, last_closed - 2 * WEEK, last_closed - WEEK, last_closed, in_progress])

    def incr(symbol, interval, start_time_ms=None, limit=1000):
        calls["incr"].append((symbol, interval, start_time_ms))
        return week_rows([last_closed, in_progress])      # 겹치는 마지막 주 + 진행 중인 주를 같이 돌려준다

    monkeypatch.setattr(weekly_data, "fetch_full_history", full)
    monkeypatch.setattr(weekly_data, "fetch_klines", incr)
    return calls, last_closed, in_progress


def test_latest_closed_week_open_is_the_monday_a_week_before_this_monday():
    assert weekly_data.latest_closed_week_open(ts("2026-10-29 04:38")) == ts("2026-10-19")    # 목요일: 10/26 주는 진행 중
    assert weekly_data.latest_closed_week_open(ts("2026-10-26 00:00")) == ts("2026-10-19")    # 월요일 00:00: 10/19 주가 막 마감
    assert weekly_data.latest_closed_week_open(ts("2026-10-25 23:59:59")) == ts("2026-10-12")  # 일요일 마감 1초 전: 아직 10/19 주 진행 중
    assert weekly_data.latest_closed_week_open(ts("2026-11-01 12:00")) == ts("2026-10-19")


def test_constants():
    assert weekly_data.WEEKLY_INTERVAL == "1w"
    assert weekly_data.WEEKLY_CACHE_START == "2017-08-01"
    assert weekly_data.WEEKLY_DISPLAY_START == "2022-01-03"
    assert ts(weekly_data.WEEKLY_DISPLAY_START).day_name() == "Monday"


def test_first_load_fetches_everything_from_the_cache_start_and_drops_the_in_progress_week(fake):
    calls, last_closed, in_progress = fake
    df = weekly_data.ensure_fresh_weekly_data()
    assert calls["full"] == [("BTCUSDT", "1w", "2017-08-01")] and calls["incr"] == []
    assert df["open_time"].iloc[-1] == last_closed and in_progress not in set(df["open_time"])
    assert weekly_data.WEEKLY_CACHE_PATH.exists()
    assert pd.read_parquet(weekly_data.WEEKLY_CACHE_PATH)["open_time"].iloc[-1] == last_closed   # 캐시에도 진행 중 주는 없다


def test_up_to_date_cache_makes_no_request(fake):
    calls, last_closed, _ = fake
    weekly_data.ensure_fresh_weekly_data()
    calls["full"].clear()
    df = weekly_data.ensure_fresh_weekly_data()
    assert calls["full"] == [] and calls["incr"] == []
    assert df["open_time"].iloc[-1] == last_closed


def test_stale_cache_is_extended_incrementally_from_the_last_candle(fake):
    calls, last_closed, in_progress = fake
    stale = week_rows([last_closed - 3 * WEEK, last_closed - 2 * WEEK])
    stale.to_parquet(weekly_data.WEEKLY_CACHE_PATH, index=False)
    df = weekly_data.ensure_fresh_weekly_data()
    assert calls["full"] == [] and len(calls["incr"]) == 1
    start_ms = calls["incr"][0][2]
    assert start_ms == int((stale["open_time"].max() + pd.Timedelta(milliseconds=1)).timestamp() * 1000)
    assert df["open_time"].iloc[-1] == last_closed and not df["open_time"].duplicated().any()
    assert in_progress not in set(df["open_time"])
    assert list(df["open_time"]) == sorted(df["open_time"])


def test_force_refetches_even_when_up_to_date(fake):
    calls, _, _ = fake
    weekly_data.ensure_fresh_weekly_data()
    weekly_data.ensure_fresh_weekly_data(force=True)
    assert len(calls["incr"]) == 1
