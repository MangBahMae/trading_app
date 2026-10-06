"""
기능1 개편 2a단계: 근접/터치 신호의 방향 기준이 "시가가 자리(EMA/선)의 어느 쪽에
있었는가"로 통일된 것을 합성 캔들로 검증한다.

- sr_touch.compute_sr_touch: 이격률 0.1% 이내 touch_reject의 방향 (EMA50)
- manual_lines.compute_manual_line_signals: 수평선/추세선 근접의 방향과 문구

pipeline 회귀 테스트(test_regression_pipeline.py)는 수동선/캔들패턴을 안 돌리므로
수동선 쪽은 이 파일이 유일한 검증이다.
"""
import sys
from pathlib import Path

import pandas as pd

SERVICES_DIR = Path(__file__).resolve().parents[1] / "app" / "services"
sys.path.insert(0, str(SERVICES_DIR))

import manual_lines  # noqa: E402
import sr_touch  # noqa: E402

SUPPORT = "지지 시험 (매수 후보)"
RESISTANCE = "저항 시험 (매도 후보)"


def _df(rows):
    """rows: (open, high, low, close) 목록. 날짜는 2025-01-01부터 하루씩."""
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=len(rows), freq="D", tz="UTC"),
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
    })


def _touch_signal(rows, ema, idx=-1):
    df = _df(rows)
    df["EMA50"] = ema
    df["EMA200"] = float("nan")
    sig = sr_touch.compute_sr_touch(df)["EMA50_signal"].iloc[idx]
    return None if pd.isna(sig) else sig  # 전부 None인 컬럼은 pandas가 NaN으로 돌려줄 수 있음


# --- sr_touch (EMA50, EMA=100, 이격률 0.1% = 100.1/99.9 이내가 touch_reject) ---

def test_touch_open_above_ema_is_long_even_for_bearish_candle():
    # 음봉(시가 101 > 종가 100.05), 시가가 EMA 위 -> 지지(long)
    assert _touch_signal([(100, 101, 99, 100), (101, 102, 99, 100.05)], 100) == "long"


def test_touch_open_below_ema_is_short_even_for_bullish_candle():
    # 양봉(시가 99 < 종가 99.95), 시가가 EMA 아래 -> 저항(short)
    assert _touch_signal([(100, 101, 99, 100), (99, 101, 98, 99.95)], 100) == "short"


def test_touch_doji_now_gets_direction_from_open():
    # 도지(시가==종가=100.05, EMA 위) - 예전엔 무신호
    assert _touch_signal([(100, 101, 99, 100), (100.05, 101, 99, 100.05)], 100) == "long"


def test_touch_open_equals_ema_uses_previous_close():
    assert _touch_signal([(101, 102, 100, 101), (100, 101, 99, 100.05)], 100) == "long"
    assert _touch_signal([(99, 100, 98, 99), (100, 101, 99, 99.95)], 100) == "short"


def test_touch_open_equals_ema_and_previous_close_equal_is_no_signal():
    assert _touch_signal([(99, 101, 99, 100), (100, 101, 99, 100.05)], 100) is None


def test_touch_open_equals_ema_on_first_candle_is_no_signal():
    assert _touch_signal([(100, 101, 99, 100.05)], 100) is None


def test_breakout_and_gray_zone_unchanged():
    # 돌파(이격률 +1%): 종가 위치 기준 long. 시가가 EMA 아래여도 바뀌지 않는다.
    df = _df([(99, 102, 98, 101)])
    df["EMA50"] = 100.0
    df["EMA200"] = float("nan")
    out = sr_touch.compute_sr_touch(df)
    assert out["EMA50_case"].iloc[0] == "breakout" and out["EMA50_signal"].iloc[0] == "long"
    # 회색지대(이격률 +0.3%): 무신호
    df = _df([(99, 102, 98, 100.3)])
    df["EMA50"] = 100.0
    df["EMA200"] = float("nan")
    out = sr_touch.compute_sr_touch(df)
    assert out["EMA50_case"].iloc[0] == "gray_zone" and out["EMA50_signal"].iloc[0] is None


# --- manual_lines ---

def _line_signals(rows, line):
    sigs = manual_lines.compute_manual_line_signals(_df(rows), [line])
    return [(i, s.direction, s.text) for i, lst in sigs.items() for s in lst]


HLINE = {"id": 1, "line_type": "horizontal", "price1": 100.0, "time1": None, "time2": None, "price2": None}


def test_horizontal_open_above_line_is_support_even_if_close_below():
    # 시가 101(선 위), 종가 99.5(선 아래) - 예전엔 종가 기준이라 저항
    (i, direction, text), = _line_signals([(101, 101.5, 99, 99.5)], HLINE)
    assert direction == "long" and SUPPORT in text


def test_horizontal_open_below_line_is_resistance_even_if_close_above():
    (i, direction, text), = _line_signals([(99, 101, 98.5, 100.5)], HLINE)
    assert direction == "short" and RESISTANCE in text


def test_horizontal_open_equals_line_uses_previous_close_then_defaults_long():
    far = (95, 96, 94, 95)  # 선에서 멀어서 신호 없음(전날 종가 95 = 선 아래)
    sigs = _line_signals([far, (100, 101, 99, 100.5)], HLINE)
    assert sigs and sigs[0][1] == "short"          # 전날 종가가 선 아래 -> 저항
    sigs = _line_signals([(105, 106, 104, 105), (100, 101, 99, 100.5)], HLINE)
    assert sigs and sigs[0][1] == "long"           # 전날 종가가 선 위 -> 지지
    sigs = _line_signals([(99, 101, 99, 100.0), (100, 101, 99, 100.5)], HLINE)
    assert [s for s in sigs if s[0] == 1][0][1] == "long"  # 전날 종가도 선과 같음 -> long


def test_trend_line_uses_interpolated_price_and_open_for_direction():
    # 추세선은 두 점 사이 선분만 평가한다(선 밖 외삽 없음 - 3단계 신호 정렬로 바뀜. 예전엔 점 (01-01,100)
    # (01-03,110)을 지나 01-05(외삽 120)에서 신호가 났지만, 이제는 같은 가격 기울기를 선분 안쪽(점 사이)에서
    # 확인한다). 두 점 (01-01,100) (01-09,140) -> 01-05의 선 가격은 선형 보간으로 120.
    line = {"id": 2, "line_type": "trend", "time1": "2025-01-01", "price1": 100.0,
            "time2": "2025-01-09", "price2": 140.0}
    rows = [(0, 0, 0, 0)] * 4 + [(121, 122, 119.5, 121)]  # 01-05: 시가 121 > 선 120
    # 앞 4개 캔들은 선(100~115) 근처가 아니게 아주 멀리 둔다
    rows = [(50, 51, 49, 50)] * 4 + rows[4:]
    (i, direction, text), = _line_signals(rows, line)
    assert i == 4 and direction == "long" and SUPPORT in text
    rows = rows[:4] + [(119, 120.5, 118, 118.5)]  # 시가 119 < 선 120 -> 저항
    (i, direction, text), = _line_signals(rows, line)
    assert i == 4 and direction == "short" and RESISTANCE in text
