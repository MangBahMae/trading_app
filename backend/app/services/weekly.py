"""
주봉(1W) 대시보드 응답 조립 - /api/dashboard/weekly가 쓴다. 일봉 dashboard.py는 건드리지 않는다.

- 데이터: weekly_data.ensure_fresh_weekly_data() (2017-08부터 받은 마감 주봉). EMA9/20/50/200은 그 전체 이력으로 계산해서
  EMA200이 2022년 초부터 유효하고, 응답의 캔들/신호는 WEEKLY_DISPLAY_START(2022-01-03) 이후 주만 담는다.
- 신호: weekly_signals.compute_weekly_signals (반전 캔들 / 장악형 / 매물소진 / EMA 터치). 날짜 키는 주봉이 시작하는 월요일.
- 선/존: 일봉(1d)에서 그린 것을 그대로 내려주기만 한다(표시용). 주봉 신호 판정에는 쓰지 않는다.
- RSI는 차트 표시용으로 일봉과 같은 Wilder 14기간을 주봉 종가에 적용한다(신호에는 쓰이지 않음).
- 일봉과 같은 응답 모양(DashboardResponse)이라 프런트가 같은 타입을 쓴다. 다이버전스 마커는 항상 빈 목록.
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lines_store  # noqa: E402
import manual_lines  # noqa: E402
import rsi  # noqa: E402
import weekly_data  # noqa: E402
import weekly_signals  # noqa: E402
from config import INTERVAL, SYMBOL  # noqa: E402

EMA_PERIODS = (9, 20, 50, 200)
_CACHE_TTL_SECONDS = 3600
_cache: dict = {"data": None, "computed_at": 0.0}


def _nan_to_none(value):
    if isinstance(value, float) and value != value:
        return None
    return value


def _compute_base(force_refresh: bool = False):
    """(표시 구간 df, 날짜별 신호 dict). 1시간 캐시(일봉과 같은 TTL) - 선/존은 매 요청 새로 읽는다."""
    now = time.time()
    if not force_refresh and _cache["data"] is not None and now - _cache["computed_at"] < _CACHE_TTL_SECONDS:
        return _cache["data"]

    df = weekly_data.ensure_fresh_weekly_data(force=False).reset_index(drop=True)
    for period in EMA_PERIODS:   # 전체 이력(워밍업 포함)으로 계산 - 각 EMA는 자기 기간이 쌓이기 전엔 NaN
        df[f"EMA{period}"] = df["close"].ewm(span=period, adjust=False, min_periods=period).mean()
    df["rsi"] = rsi.compute_rsi_signals(df)["rsi"]

    signals = weekly_signals.compute_weekly_signals(df, display_start=weekly_data.WEEKLY_DISPLAY_START)
    start = pd.Timestamp(weekly_data.WEEKLY_DISPLAY_START, tz="UTC")
    shown = df[df["open_time"] >= start].reset_index(drop=True)
    offset = len(df) - len(shown)
    result = (shown, {i - offset: sigs for i, sigs in signals.items() if i >= offset})
    _cache["data"] = result
    _cache["computed_at"] = now
    return result


def get_weekly_dashboard_data(force_refresh: bool = False) -> dict:
    df, signals = _compute_base(force_refresh)

    lines = lines_store.list_lines(SYMBOL, INTERVAL)   # 일봉에서 그린 선/존 - 표시 전용
    for line in lines:
        line["label"] = manual_lines.line_label(line)

    signals_by_date = {}
    for i in range(len(df)):
        if signals.get(i):
            date = df["open_time"].iloc[i].strftime("%Y-%m-%d")
            signals_by_date[date] = [
                {
                    "text": s.text, "direction": s.direction, "source": s.source, "tier": s.tier,
                    "evidence": list(s.evidence), "ref_id": s.ref_id, "ref_created_at": s.ref_created_at,
                    "near_zone": s.near_zone, "next_bar": s.next_bar,
                }
                for s in signals[i]
            ]

    candle_cols = ["open", "high", "low", "close", "volume"] + [f"EMA{p}" for p in EMA_PERIODS] + ["rsi"]
    candles = []
    for row in df.itertuples():
        entry = {"date": row.open_time.strftime("%Y-%m-%d")}
        for col in candle_cols:
            entry[col.lower()] = _nan_to_none(getattr(row, col))
        candles.append(entry)

    return {
        "candles": candles,
        "date_range": {
            "min": df["open_time"].iloc[0].strftime("%Y-%m-%d"),
            "max": df["open_time"].iloc[-1].strftime("%Y-%m-%d"),
        },
        "signals": signals_by_date,
        "divergence_markers": [],
        "manual_lines": lines,
    }
