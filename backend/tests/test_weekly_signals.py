"""
주봉(1w) 신호 4종 (weekly_signals.compute_weekly_signals) - 반전 캔들 / 장악형 / 매물소진 / EMA20·50·200 터치.

- 기준값은 주봉 전용 상수(일봉 상수와 분리), 모양 기준값은 WEEKLY_SHAPE_PARAMS 사본
- 직전 캔들 시가 == 종가(몸통 0)면 양봉도 음봉도 아니라 무신호
- display_start 이전 주는 신호를 내지 않는다(직전 주 정보로는 그 이전 데이터를 쓴다)
- 실데이터(2022~2026-10-19까지 마감 주봉)의 신호 건수가 확정한 표와 같다
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

import candle_patterns  # noqa: E402
import weekly_data  # noqa: E402
import weekly_signals as ws  # noqa: E402

NAN = float("nan")


def make_weeks(rows, emas=None, start="2025-01-06"):
    """rows: (open, high, low, close[, volume]) - 월요일 시작 주봉 DataFrame. emas: {20: [..], 50: [..], 200: [..]} (없으면 NaN)."""
    n = len(rows)
    df = pd.DataFrame({
        "open_time": pd.date_range(start, periods=n, freq="7D", tz="UTC"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows], "low": [r[2] for r in rows],
        "close": [r[3] for r in rows], "volume": [r[4] if len(r) > 4 else 1000.0 for r in rows],
    })
    for p in (20, 50, 200):
        df[f"EMA{p}"] = (emas or {}).get(p, [NAN] * n)
    return df


def texts(rows, emas=None, **kw):
    sigs = ws.compute_weekly_signals(make_weeks(rows, emas), **kw)
    return {i: [(s.text, s.direction) for s in v] for i, v in sigs.items() if v}


FLAT = (100, 100, 100, 100)            # 시가 == 종가, 범위 0: 모양 아님, 어떤 직전 캔들 조건에도 안 걸림
DOJI = (100, 105, 95, 100)             # 시가 == 종가, 두 꼬리 같음 -> 도지 (몸통 0)


def bull(pct, base=100.0):
    """몸통 pct% 양봉 (모양 아님: 꼬리 없음)."""
    return (base, base * (1 + pct / 100), base, base * (1 + pct / 100))


def bear(pct, base=100.0):
    return (base, base, base * (1 - pct / 100), base * (1 - pct / 100))


# --- 상수 ---

def test_weekly_constants_are_separate_from_the_daily_ones():
    assert ws.W_REVERSAL_PREV_BODY_MIN_PCT == 3.0
    assert ws.W_ENGULF_PREV_BODY_MIN_PCT == 4.0
    assert ws.W_EXHAUSTION_PREV_MIN_PCT == 10.0
    assert (ws.W_EMA_TOUCH_MAX_PCT, ws.W_EMA_BREAKOUT_MIN_PCT) == (0.65, 2.0)
    assert ws.W_EMA_PERIODS == (20, 50, 200)
    # 모양 기준값은 일봉 상수 사본(값은 같게 시작) - 하지만 별개 객체
    assert ws.WEEKLY_SHAPE_PARAMS == candle_patterns.default_shape_params()


# --- 1. 반전 캔들 ---

def test_reversal_short_after_bullish_and_long_after_bearish_candle():
    assert texts([bull(5), DOJI]) == {1: [("주봉 도지 반전 - 숏 후보", "short")]}
    assert texts([bear(5), DOJI]) == {1: [("주봉 도지 반전 - 롱 후보", "long")]}


def test_reversal_previous_body_threshold_is_inclusive():
    assert texts([bull(3.0), DOJI]) != {}
    assert texts([bull(2.99), DOJI]) == {}
    assert texts([bear(3.0), DOJI]) != {}
    assert texts([bear(2.99), DOJI]) == {}


def test_reversal_needs_a_real_direction_for_the_previous_candle():
    assert texts([FLAT, DOJI]) == {}                          # 직전 시가 == 종가: 양봉도 음봉도 아님
    assert texts([(100, 103, 97, 100), DOJI]) == {}           # 꼬리만 있고 몸통 0


def test_reversal_covers_hammer_and_inverted_hammer():
    hammer = (100, 100.5, 80, 99)      # 위꼬리 짧고 아래꼬리 긴 망치형
    inverted = (100, 120, 99.5, 101)   # 아래꼬리 짧고 위꼬리 긴 역망치형
    assert texts([bull(5), hammer]) == {1: [("주봉 망치형 반전 - 숏 후보", "short")]}
    assert texts([bear(5), inverted]) == {1: [("주봉 역망치형 반전 - 롱 후보", "long")]}


def test_shape_uses_the_weekly_params_not_the_daily_constants(monkeypatch):
    monkeypatch.setattr(candle_patterns, "BODY_MAX_PCT", 0.0)           # 일봉 상수를 망가뜨려도 주봉 모양은 그대로
    monkeypatch.setattr(candle_patterns, "BODY_EXT_MAX_PCT", 0.0)
    assert texts([bull(5), DOJI]) != {}
    from dataclasses import replace
    monkeypatch.setattr(ws, "WEEKLY_SHAPE_PARAMS", replace(ws.WEEKLY_SHAPE_PARAMS, body_max=-1.0, body_ext_max=-1.0))
    assert texts([bull(5), DOJI]) == {}                                  # 주봉 사본을 바꾸면 주봉만 바뀐다


# --- 2. 장악형 ---

def test_bearish_engulfing_short_and_bullish_engulfing_long():
    assert texts([(100, 105, 100, 105), (105, 106, 99, 99.5)]) == {1: [("주봉 장악형 하락 - 숏 신호", "short")]}
    assert texts([(100, 100, 95, 95), (95, 101, 94, 100.5)]) == {1: [("주봉 장악형 상승 - 롱 신호", "long")]}


def engulf(rows):
    """장악형 신호만 (모양 캔들의 반전 신호와 겹쳐 보이지 않게 거른다)."""
    return {i: [t for t in v if "장악형" in t[0]] for i, v in texts(rows).items() if any("장악형" in t[0] for t in v)}


def test_engulfing_conditions_and_thresholds():
    prev_bull = (100, 104, 100, 104)                         # 몸통 4.0%
    assert engulf([prev_bull, (104, 105, 99, 99.69)]) != {}  # 종가 <= 직전 시가 100 x 0.997 = 99.7
    assert engulf([prev_bull, (104, 105, 99, 99.8)]) == {}   # 시가를 0.3% 이상 뚫지 못함
    assert engulf([prev_bull, (103.8, 105, 99, 99.5)]) == {}  # 시가가 직전 종가 x 0.999 아래에서 열림
    assert engulf([(100, 103.99, 100, 103.99), (104, 105, 99, 99.5)]) == {}   # 직전 몸통 3.99% < 4%
    assert engulf([prev_bull, (104, 106, 99, 105)]) == {}    # 이번 주가 양봉이면 하락 장악형이 아님


# --- 3. 매물소진 ---

def test_exhaustion_buy_after_big_bearish_and_sell_after_big_bullish():
    assert texts([(100, 100, 90, 90, 1000), (90, 95, 88, 92, 600)]) == {1: [("주봉 매물소진 - 매수 신호", "long")]}
    assert texts([(100, 110, 100, 110, 1000), (110, 112, 106, 108, 600)]) == {1: [("주봉 매물소진 - 매도 신호", "short")]}


def test_exhaustion_thresholds():
    prev = (100, 100, 90, 90, 1000)                          # 직전 변화율 10%
    assert texts([(100, 100, 90.1, 90.1, 1000), (90.1, 95, 88, 92, 600)]) == {}      # 직전 9.9% < 10%
    assert texts([prev, (90, 96, 88, 94.6, 600)]) == {}                              # 이번 5.1% > 직전의 절반(5%)
    assert texts([prev, (90, 95, 88, 94.4, 600)]) != {}                              # 4.4% <= 5%
    assert texts([prev, (90, 95, 88, 92, 499)]) == {}                                # 거래량이 직전의 50% 미만
    assert texts([prev, (90, 95, 88, 92, 500)]) != {}                                # 정확히 50%는 통과
    # 이번 주가 음봉이어도 방향은 직전 캔들 기준이라 매수
    assert texts([prev, (90, 91, 88, 89, 600)]) == {1: [("주봉 매물소진 - 매수 신호", "long")]}


# --- 4. EMA 터치 ---

def ema_week(open_, close, ema=100.0, prev_close=100.0, high=106.0, low=94.0):
    rows = [(prev_close, prev_close, prev_close, prev_close), (open_, high, low, close)]
    return texts(rows, emas={20: [NAN, ema]})


def test_ema_touch_direction_follows_the_open_and_breakout_follows_the_close():
    assert ema_week(101, 100.5) == {1: [("주봉 EMA20 지지", "long")]}                 # 근접(0.5%), 시가 위
    assert ema_week(99, 100.5) == {1: [("주봉 EMA20 저항 (거부)", "short")]}          # 근접, 시가 아래 - 종가가 위여도 시가 기준
    assert ema_week(99, 103) == {1: [("주봉 EMA20 상향 돌파", "long")]}               # 돌파(3%), 종가 위
    assert ema_week(103, 97) == {1: [("주봉 EMA20 하향 이탈", "short")]}              # 돌파, 종가 아래 - 시가가 위여도 종가 기준


def test_ema_gray_zone_and_boundaries():
    assert ema_week(99, 101) == {1: [("주봉 EMA20 근접했으나 회색지대라 신호 제외", "reference")]}   # 이격 1% (0.65~2%)
    assert ema_week(101, 100.6) == {1: [("주봉 EMA20 지지", "long")]}                 # 0.6% <= 0.65%
    assert ema_week(101, 100.7)[1][0][1] == "reference"                              # 0.7% > 0.65% 회색
    assert ema_week(101, 102.0)[1][0][1] == "reference"                              # 정확히 2.0%는 돌파 아님(초과만)
    assert ema_week(101, 102.01) == {1: [("주봉 EMA20 상향 돌파", "long")]}


def test_ema_open_equal_uses_previous_close_and_needs_a_touch():
    assert ema_week(100, 100.5, prev_close=101) == {1: [("주봉 EMA20 지지", "long")]}   # 시가 == EMA: 직전 종가가 위
    assert ema_week(100, 100.5, prev_close=99) == {1: [("주봉 EMA20 저항 (거부)", "short")]}
    assert ema_week(100, 100.5, prev_close=100) == {}                                  # 직전 종가도 같으면 무신호
    assert ema_week(110, 112, ema=100.0, low=108.0, high=115.0) == {}                              # 캔들이 EMA에 안 닿음(저가 > EMA)
    assert texts([FLAT, (101, 106, 94, 100.5)]) == {}                                  # EMA가 NaN이면 무시


def test_each_ema_period_signals_independently():
    rows = [FLAT, (99, 106, 94, 103)]
    out = texts(rows, emas={20: [NAN, 100.0], 50: [NAN, 101.0], 200: [NAN, 90.0]})
    assert out == {1: [("주봉 EMA20 상향 돌파", "long"), ("주봉 EMA50 근접했으나 회색지대라 신호 제외", "reference")]}


# --- display_start / 미래 참조 ---

def test_display_start_suppresses_earlier_weeks_but_uses_them_as_the_previous_candle():
    rows = [bull(5), DOJI, bull(5), DOJI]                    # idx1, idx3에서 반전 숏
    assert set(texts(rows)) == {1, 3}
    start = make_weeks(rows)["open_time"].iloc[2]            # idx2부터 표시
    assert set(texts(rows, display_start=start)) == {3}
    start3 = make_weeks(rows)["open_time"].iloc[3]
    assert set(texts(rows, display_start=start3)) == {3}     # 직전(idx2)은 표시 이전이 아니어도 직전 정보로만 쓰인다
    assert texts([bull(5), DOJI], display_start="2030-01-01") == {}


def test_signals_do_not_change_when_later_weeks_are_removed():
    rows = [bull(5), DOJI, bear(6), (95, 101, 94, 100.5), (100, 100, 90, 90), (90, 95, 88, 92)]
    full = texts(rows)
    for k in range(2, len(rows)):
        prefix = texts(rows[:k])
        assert prefix == {i: v for i, v in full.items() if i < k}


# --- 실데이터: 확정한 표와 같은 건수 ---

@pytest.fixture(scope="module")
def real_weekly():
    df = weekly_data.ensure_fresh_weekly_data()
    df = df[df["open_time"] <= pd.Timestamp("2026-10-19", tz="UTC")].reset_index(drop=True)   # 확정 시점까지 마감된 주만(이후 주가 늘어도 고정)
    for p in (20, 50, 200):
        df[f"EMA{p}"] = df["close"].ewm(span=p, adjust=False, min_periods=p).mean()
    return df


def _classify(text):
    if "반전 - 숏" in text:
        return "반전 숏"
    if "반전 - 롱" in text:
        return "반전 롱"
    if "장악형 하락" in text:
        return "장악형 숏"
    if "장악형 상승" in text:
        return "장악형 롱"
    if "매물소진" in text:
        return "매물소진"
    if "회색지대" in text:
        return "EMA 회색"
    if "지지" in text or "저항" in text:
        return "EMA 근접"
    return "EMA 돌파"


def test_real_data_counts_match_the_agreed_table(real_weekly):
    from collections import Counter
    sigs = ws.compute_weekly_signals(real_weekly, display_start=weekly_data.WEEKLY_DISPLAY_START)
    counts = Counter(_classify(s.text) for v in sigs.values() for s in v)
    assert counts["반전 숏"] == 25 and counts["반전 롱"] == 15
    assert counts["장악형 숏"] == 5 and counts["장악형 롱"] == 6
    assert counts["매물소진"] == 20
    assert counts["EMA 근접"] == 7 and counts["EMA 돌파"] == 75
    assert counts["EMA 회색"] == 22
    first = real_weekly.index[real_weekly["open_time"] >= pd.Timestamp(weekly_data.WEEKLY_DISPLAY_START, tz="UTC")][0]
    assert all(not v for i, v in sigs.items() if i < first)                # 2022-01-03 이전 주는 신호 없음
    assert all(s.near_zone is None and s.next_bar is None for v in sigs.values() for s in v)
    assert all(s.text.startswith("주봉 ") for v in sigs.values() for s in v)


def test_real_data_ema200_is_valid_from_the_display_start(real_weekly):
    first = real_weekly[real_weekly["open_time"] >= pd.Timestamp(weekly_data.WEEKLY_DISPLAY_START, tz="UTC")]
    assert first["EMA200"].notna().all() and len(first) == 251


def test_real_data_no_lookahead(real_weekly):
    full = ws.compute_weekly_signals(real_weekly, display_start=weekly_data.WEEKLY_DISPLAY_START)
    key = lambda m, hi: {i: [(s.text, s.direction) for s in v] for i, v in m.items() if i < hi and v}  # noqa: E731
    for k in (300, 380, 440):
        prefix = ws.compute_weekly_signals(real_weekly.iloc[:k], display_start=weekly_data.WEEKLY_DISPLAY_START)
        assert key(prefix, k) == key(full, k)
