"""
망치형/역망치형/도지 모양 판정 (candle_patterns.compute_candle_shape) - 2026-10 새 정의.

- 망치형: 몸통 <= 35%, 위꼬리 <= 10%, 아래꼬리 >= 몸통 x 2   (모든 비율은 범위 = 고가 - 저가 대비)
- 역망치형: 몸통 <= 35%, 아래꼬리 <= 10%, 위꼬리 >= 몸통 x 2
- 도지: 위 둘이 아니면서 몸통 <= 15%, 15~25%는 거래량 >= 직전 20일 평균 x 1.5. 대칭도 조건 없음.
- 망치형/역망치형에는 거래량 조건이 없다. 범위 0 캔들은 모양 없음.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

import candle_patterns  # noqa: E402
import pipeline  # noqa: E402

LOW, HIGH = 0.0, 100.0     # 범위 100 -> 비율 = 가격 차이(%)


def shape_of(top, bottom, bullish=True, volume=1.0, prior_volume=1.0, n_prior=25):
    """앞에 거래량 prior_volume짜리 평범한 캔들 n_prior개를 깔고, 마지막 캔들(몸통 bottom~top, 범위 0~100)의 모양."""
    o, c = (bottom, top) if bullish else (top, bottom)
    rows = [(50.0, 51.0, 49.0, 50.0, prior_volume)] * n_prior + [(o, HIGH, LOW, c, volume)]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    df["open_time"] = pd.date_range("2025-01-01", periods=len(df), freq="D", tz="UTC")
    return candle_patterns.compute_candle_shape(df)["shape"].iloc[-1]


def test_threshold_constants():
    assert candle_patterns.HAMMER_BODY_MAX_PCT == 0.35
    assert candle_patterns.HAMMER_OPPOSITE_WICK_MAX_PCT == 0.10
    assert candle_patterns.HAMMER_WICK_BODY_MULT == 2
    assert candle_patterns.BODY_MAX_PCT == 0.15 and candle_patterns.BODY_EXT_MAX_PCT == 0.25


# --- 망치형 ---

def test_hammer_basic_and_bearish_body_too():
    assert shape_of(top=90, bottom=70) == "hammer"                         # 몸통 20, 위꼬리 10(경계), 아래꼬리 70
    assert shape_of(top=90, bottom=70, bullish=False) == "hammer"          # 몸통 색은 안 본다


def test_hammer_upper_wick_limit_is_ten_percent_inclusive():
    assert shape_of(top=90, bottom=70) == "hammer"                         # 위꼬리 10.0%
    assert shape_of(top=89.9, bottom=69.9) is None                         # 위꼬리 10.1%, 몸통 20%(> 15%)이고 거래량 조건 미달


def test_hammer_lower_wick_must_be_at_least_twice_the_body():
    assert shape_of(top=90, bottom=60) == "hammer"                         # 몸통 30, 아래꼬리 60 = 2배(경계)
    assert shape_of(top=90, bottom=59.9) is None                           # 몸통 30.1 > 25%, 아래꼬리 59.9 < 60.2


def test_hammer_does_not_need_the_volume_condition_even_in_the_15_to_25_percent_body_zone():
    assert shape_of(top=92, bottom=72, volume=0.1) == "hammer"             # 몸통 20%인데 거래량이 아주 낮아도 망치형
    assert shape_of(top=92, bottom=72, volume=5.0) == "hammer"


def test_thirty_five_percent_body_bound_is_implied_by_the_two_times_rule():
    # 위꼬리가 0이어도 아래꼬리(= 100 - 몸통) >= 2 x 몸통이려면 몸통 <= 33.3%라서, 35% 상한은 사실상 넉넉한 안전판이다
    assert shape_of(top=100, bottom=66.67) == "hammer"                     # 몸통 33.33%, 아래꼬리 66.67 >= 66.66
    assert shape_of(top=100, bottom=66) is None                            # 몸통 34%: 아래꼬리 66 < 68 (그리고 > 25%라 도지도 아님)


# --- 역망치형 (대칭) ---

def test_inverted_hammer_mirror():
    assert shape_of(top=30, bottom=10) == "inverted_hammer"                 # 몸통 20, 아래꼬리 10(경계), 위꼬리 70
    assert shape_of(top=30, bottom=10, bullish=False) == "inverted_hammer"
    assert shape_of(top=30.1, bottom=10.1) is None                         # 아래꼬리 10.1%
    assert shape_of(top=40, bottom=10) == "inverted_hammer"                # 몸통 30, 위꼬리 60 = 2배(경계)
    assert shape_of(top=40.1, bottom=10) is None


def test_inverted_hammer_has_no_volume_condition():
    assert shape_of(top=28, bottom=8, volume=0.1) == "inverted_hammer"


# --- 도지 ---

def test_doji_is_everything_small_body_that_is_not_a_hammer_or_inverted_hammer():
    assert shape_of(top=50, bottom=50) == "doji"                           # 몸통 0, 두 꼬리 50/50
    assert shape_of(top=60, bottom=50) == "doji"                           # 몸통 10%, 꼬리 40/50
    # 예전에는 망치형이던 모양(위꼬리 15%, 몸통 5%): 위꼬리 > 10%라 망치형이 못 되고 도지가 된다(대칭도 조건 없음)
    assert shape_of(top=85, bottom=80) == "doji"


def test_doji_body_up_to_fifteen_percent_without_volume_and_up_to_twenty_five_with_it():
    assert shape_of(top=65, bottom=50) == "doji"                           # 몸통 15% (거래량 무관)
    assert shape_of(top=70, bottom=50, volume=1.0) is None                 # 몸통 20%, 거래량 배수 1.0 < 1.5
    assert shape_of(top=70, bottom=50, volume=1.5) == "doji"               # 몸통 20%, 배수 1.5 (경계)
    assert shape_of(top=75, bottom=50, volume=3.0) == "doji"               # 몸통 25%
    assert shape_of(top=75.1, bottom=50, volume=3.0) is None               # 몸통 25.1% > 25%


def test_zero_range_candle_has_no_shape():
    df = pd.DataFrame([(50.0, 50.0, 50.0, 50.0, 1.0)] * 3, columns=["open", "high", "low", "close", "volume"])
    df["open_time"] = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
    assert candle_patterns.compute_candle_shape(df)["shape"].tolist() == [None, None, None]


def test_wide_body_is_never_a_pattern():
    assert shape_of(top=95, bottom=5) is None


# --- 실데이터: 독립 구현과 일치 ---

def test_real_data_matches_an_independent_implementation():
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    sh = candle_patterns.compute_candle_shape(df)
    rng = (df["high"] - df["low"]).to_numpy()
    body = (df["close"] - df["open"]).abs().to_numpy()
    top = df[["open", "close"]].max(axis=1).to_numpy()
    bottom = df[["open", "close"]].min(axis=1).to_numpy()
    upper = df["high"].to_numpy() - top
    lower = bottom - df["low"].to_numpy()
    avg = df["volume"].shift(1).rolling(20).mean().to_numpy()
    vol = df["volume"].to_numpy()
    expected = []
    for i in range(len(df)):
        if rng[i] == 0:
            expected.append(None)
            continue
        b, u, lo = body[i] / rng[i], upper[i] / rng[i], lower[i] / rng[i]
        if b <= 0.35 and u <= 0.10 and lo >= 2 * b:
            expected.append("hammer")
        elif b <= 0.35 and lo <= 0.10 and u >= 2 * b:
            expected.append("inverted_hammer")
        elif b <= 0.15 or (b <= 0.25 and avg[i] == avg[i] and vol[i] / avg[i] >= 1.5):
            expected.append("doji" if max(u, lo) > 0 else None)
        else:
            expected.append(None)
    assert sh["shape"].tolist() == expected
    counts = pd.Series(expected).value_counts()
    assert counts["doji"] > counts["hammer"] > 0 and counts["inverted_hammer"] > 0


# --- 기준값 인자 (주봉처럼 다른 기준을 쓰는 쪽용) ---

def _frame(top, bottom, volume=1.0, prior_volume=1.0, n_prior=25):
    rows = [(50.0, 51.0, 49.0, 50.0, prior_volume)] * n_prior + [(bottom, HIGH, LOW, top, volume)]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    df["open_time"] = pd.date_range("2025-01-01", periods=len(df), freq="D", tz="UTC")
    return df


def test_default_params_equal_the_module_constants_and_give_the_same_result():
    p = candle_patterns.default_shape_params()
    assert (p.body_max, p.body_ext_max, p.hammer_body_max, p.hammer_opposite_wick_max, p.hammer_wick_body_mult,
            p.volume_lookback, p.volume_ratio_min) == (0.15, 0.25, 0.35, 0.10, 2, 20, 1.5)
    df = _frame(top=90, bottom=70)
    assert candle_patterns.compute_candle_shape(df)["shape"].tolist() ==         candle_patterns.compute_candle_shape(df, p)["shape"].tolist()


def test_default_params_follow_the_module_constants_at_call_time(monkeypatch):
    df = _frame(top=90, bottom=70)                                   # 망치형(몸통 20%, 위꼬리 10%)
    assert candle_patterns.compute_candle_shape(df)["shape"].iloc[-1] == "hammer"
    monkeypatch.setattr(candle_patterns, "HAMMER_OPPOSITE_WICK_MAX_PCT", 0.05)
    assert candle_patterns.compute_candle_shape(df)["shape"].iloc[-1] is None


def test_explicit_params_override_the_defaults_without_touching_them():
    from dataclasses import replace
    df = _frame(top=90, bottom=70)
    strict = replace(candle_patterns.default_shape_params(), hammer_opposite_wick_max=0.05)
    assert candle_patterns.compute_candle_shape(df, strict)["shape"].iloc[-1] is None
    assert candle_patterns.compute_candle_shape(df)["shape"].iloc[-1] == "hammer"      # 기본은 그대로
    short_lookback = replace(candle_patterns.default_shape_params(), volume_lookback=5)
    wide = _frame(top=70, bottom=50, volume=2.0, n_prior=6)                            # 몸통 20%: 거래량 룩백이 짧을 때만 평균이 생긴다
    assert candle_patterns.compute_candle_shape(wide)["shape"].iloc[-1] is None        # 기본 20봉: 평균 NaN -> 탈락
    assert candle_patterns.compute_candle_shape(wide, short_lookback)["shape"].iloc[-1] == "doji"
