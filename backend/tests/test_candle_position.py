"""
캔들 패턴 위치(고점/저점 캔들) 새 판정 - candle_patterns.compute_candle_pattern_signals.

- 고점/저점 캔들은 몸통(max/min(시가, 종가))만 보고 직전 N개와 엄격 비교한다(꼬리 무시)
- 신호: 고점/저점 캔들 당일 모양이면 당일, 아니면 t+1 모양이면 t+1("(다음 봉)", next_bar=True)
- 둘 다 모양이면 당일만, t+1이 또 고점이면 t+1 자신의 신호(당일), 처음 N개 캔들은 신호 없음
- 시세분출 무효는 숏 신호(당일/다음 봉)에만, 참고는 feature_flags.ENABLE_CANDLE_REFERENCE=True일 때만
- 미래 참조 없음(뒤쪽 캔들을 잘라도 앞쪽 신호는 같다)

합성 데이터는 N=3(n_lookback=3)으로 짧게 만든다. 모양은 도지(몸통 0, 두 꼬리 같음)와 장대 양봉(모양 아님)을 쓴다.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

import lines_store  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "regression"))

import candle_patterns  # noqa: E402
import compare_candle_position  # noqa: E402
import feature_flags  # noqa: E402
import pipeline  # noqa: E402

N = 3


def big(top, bottom=None):
    """장대 양봉(모양 아님): 몸통 = bottom~top, 꼬리는 1씩."""
    bottom = top - 10 if bottom is None else bottom
    return (bottom, top + 1, bottom - 1, top)


def doji(mid, wick=5.0):
    """도지: 시가 = 종가 = mid, 위아래 꼬리 같음. 몸통 상단 = 하단 = mid."""
    return (mid, mid + wick, mid - wick, mid)


def make_df(rows):
    n = len(rows)
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows], "low": [r[2] for r in rows],
        "close": [r[3] for r in rows], "volume": [1.0] * n,
    })


def run(rows, **kw):
    sigs = candle_patterns.compute_candle_pattern_signals(make_df(rows), None, n_lookback=N, **kw)
    return {i: [(s.text, s.direction, s.next_bar) for s in v] for i, v in sigs.items() if v}


BASE = [big(1000)] * N    # 몸통 990~1000 세 개 (가격을 크게 잡아 3봉 누적 상승이 시세분출(12%)에 안 걸리게 한다)


# --- 당일 / 다음 봉 ---

def test_high_candle_that_is_a_pattern_signals_short_the_same_day():
    assert run(BASE + [doji(1050)]) == {3: [("도지 - 숏 후보", "short", False)]}


def test_low_candle_that_is_a_pattern_signals_long_the_same_day():
    assert run(BASE + [doji(850)]) == {3: [("도지 - 롱 후보", "long", False)]}


def test_next_bar_signal_when_the_high_candle_is_not_a_pattern():
    # idx3: 장대 양봉(몸통 상단 1030, 고점 캔들, 모양 아님) -> idx4 도지(상단 1005, 고점 아님)에서 신호
    assert run(BASE + [big(1030), doji(1005)]) == {4: [("도지 - 숏 후보 (다음 봉)", "short", True)]}


def test_next_bar_long_mirror():
    assert run(BASE + [big(985, 975), doji(980)]) == {4: [("도지 - 롱 후보 (다음 봉)", "long", True)]}


def test_both_patterns_only_the_high_candle_signals():
    # idx3 도지(고점), idx4 도지(고점 아님) -> idx3에서만 1번
    assert run(BASE + [doji(1050), doji(1040)]) == {3: [("도지 - 숏 후보", "short", False)]}


def test_next_bar_that_is_a_new_high_is_judged_on_its_own_as_a_same_day_signal():
    # idx3 장대 양봉(고점) -> idx4 도지가 또 고점(1050 > 1030): 새 고점 캔들로 재판정 -> 당일 신호(접미사 없음)
    assert run(BASE + [big(1030), doji(1050)]) == {4: [("도지 - 숏 후보", "short", False)]}


def test_chain_of_new_highs_signals_once_when_the_pattern_finally_appears():
    # idx3, idx4 연속 신고점(장대) -> idx5 도지(고점 아님): idx4 기준 다음 봉 신호 한 번
    assert run(BASE + [big(1030), big(1060), doji(1040)]) == {5: [("도지 - 숏 후보 (다음 봉)", "short", True)]}


def test_only_the_next_candle_is_checked_not_t_plus_2():
    assert run(BASE + [big(1030), big(1000), doji(1010)]) == {}


# --- 엄격 비교 / 몸통만 / 처음 N개 ---

def test_equal_to_previous_max_is_not_a_high_candle():
    assert run(BASE + [doji(1000)]) == {}            # 몸통 상단 1000 == 직전 최댓값 1000 (엄격 초과 아님)
    assert run(BASE + [doji(1000.01)]) != {}


def test_wicks_are_ignored_for_the_position_test():
    assert run(BASE + [doji(1000, wick=50)]) == {}   # 위꼬리는 1050까지 가지만 몸통 상단은 1000


def test_first_n_candles_cannot_be_high_or_low_candles():
    # N=3: idx0~2는 직전 N개가 없다 -> 모양이어도 신호 없음
    assert run([doji(2000), big(1000), big(1000)]) == {}
    assert run([big(1000)] * 3 + [doji(1050)]) != {}   # idx3부터는 가능


def test_same_candle_can_have_long_same_day_and_short_next_bar():
    # idx3 장대(고점) -> idx4 도지(850): idx3 기준 숏(다음 봉) + 자신은 저점 캔들이라 롱(당일). 롱 -> 숏 순서로 둘 다
    out = run(BASE + [big(1030), doji(850)])
    assert out == {4: [("도지 - 롱 후보", "long", False), ("도지 - 숏 후보 (다음 봉)", "short", True)]}


# --- 시세분출 무효 (숏에만) ---

RISING = [big(100), (100, 111, 99, 110), (110, 122, 109, 121), (121, 135, 120, 134)]   # idx1~3: 3봉 누적 34%


def test_volatility_expansion_invalidates_short_same_day_and_next_bar_but_not_long():
    log = []
    sigs = candle_patterns.compute_candle_pattern_signals(
        make_df(RISING + [doji(140)]), None, invalidated_log=log, n_lookback=N)
    assert [(s.text, s.direction, s.next_bar) for s in sigs[4]] == [("도지 - 시세분출 무효", "reference", False)]
    assert log and log[0]["index"] == 4 and log[0]["signal_text"] == "도지 - 숏 후보"

    assert run(RISING + [doji(130)]) == {4: [("도지 - 시세분출 무효 (다음 봉)", "reference", True)]}
    # 롱(저점 캔들)은 시세분출과 무관하게 롱 후보 그대로 - 같은 캔들의 숏(다음 봉)만 무효가 된다
    assert run(RISING + [doji(95)]) == {
        4: [("도지 - 롱 후보", "long", False), ("도지 - 시세분출 무효 (다음 봉)", "reference", True)]}


# --- 참고 (기본 꺼짐) ---

def test_reference_is_off_by_default_and_only_for_shapes_without_a_signal_when_on(monkeypatch):
    rows = BASE + [doji(1050), doji(1005), doji(1006)]    # idx3 숏 신호, idx4/5는 모양인데 신호 없음
    off = run(rows)
    assert 3 in off and 4 not in off and 5 not in off
    assert feature_flags.ENABLE_CANDLE_REFERENCE is False

    monkeypatch.setattr(feature_flags, "ENABLE_CANDLE_REFERENCE", True)
    on = run(rows)
    assert on[3] == off[3]                                           # 신호가 있는 캔들에는 참고를 안 붙인다
    assert on[4] == [("도지 - 참고", "reference", False)] and on[5] == [("도지 - 참고", "reference", False)]


# --- near_zone / N 상수 ---

def test_near_zone_is_set_on_the_signal_candle():
    zone = {"id": 1, "line_type": "zone", "time1": "2025-01-01", "price1": 1060.0, "time2": "2025-12-31",
            "price2": 1040.0, "created_at": "x"}
    sigs = candle_patterns.compute_candle_pattern_signals(make_df(BASE + [doji(1050)]), None, zones=[zone], n_lookback=N)
    assert sigs[3][0].near_zone is True and sigs[3][0].next_bar is False
    sigs = candle_patterns.compute_candle_pattern_signals(make_df(BASE + [doji(1050)]), None, zones=[], n_lookback=N)
    assert sigs[3][0].near_zone is False


def test_lookback_constant_is_ten_and_drives_the_default(monkeypatch):
    assert candle_patterns.POSITION_LOOKBACK_N == 10
    rows = BASE + [doji(1050)]
    df = make_df(rows)
    assert candle_patterns.compute_candle_pattern_signals(df, None) == {i: [] for i in range(len(df))}  # N=10: 캔들이 부족
    monkeypatch.setattr(candle_patterns, "POSITION_LOOKBACK_N", 3)
    assert [s.text for s in candle_patterns.compute_candle_pattern_signals(df, None)[3]] == ["도지 - 숏 후보"]


def test_manual_signals_argument_is_ignored():
    from signal_types import Signal
    rows = BASE + [doji(1050)]
    plain = run(rows)
    with_lines = candle_patterns.compute_candle_pattern_signals(
        make_df(rows), {i: [Signal("x", "long")] for i in range(len(rows))}, n_lookback=N)
    assert {i: [(s.text, s.direction, s.next_bar) for s in v] for i, v in with_lines.items() if v} == plain


# --- 실데이터: 비교 스크립트와 일치 / 미래 참조 없음 ---

@pytest.fixture(scope="module")
def real_df():
    df, _, _ = pipeline.load_dashboard_data()
    return df.reset_index(drop=True)


def test_matches_the_comparison_script_on_real_data(real_df):
    shape = candle_patterns.compute_candle_shape(real_df)["shape"]
    expected, _, _ = compare_candle_position.new_method_signals(real_df, shape, 10)
    expected = {(i, d, pat) for i, d, pat, _ in expected}
    sigs = candle_patterns.compute_candle_pattern_signals(real_df, None)
    got = {(i, "long" if s.direction == "long" else "short", s.text.split(" - ")[0])
           for i, v in sigs.items() for s in v}          # 시세분출 무효(reference)는 숏 신호가 바뀐 것
    assert got == expected and len(got) > 50


def test_no_lookahead_prefix_signals_are_identical(real_df):
    key = lambda m, hi: {i: [(s.text, s.direction, s.next_bar) for s in v] for i, v in m.items() if i < hi and v}  # noqa: E731
    full = candle_patterns.compute_candle_pattern_signals(real_df, None)
    for k in (300, 700, 1200, 1500):
        prefix = candle_patterns.compute_candle_pattern_signals(real_df.iloc[:k], None)
        assert key(prefix, k) == key(full, k), f"앞 {k}개만 있어도 그 구간 신호가 같아야 한다"


# --- API ---

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


def test_dashboard_exposes_next_bar_only_on_candle_pattern_signals(client):
    data = client.get("/api/dashboard").json()
    items = [s for v in data["signals"].values() for s in v]
    candle = [s for s in items if s["text"].split(" - ")[0] in ("도지", "망치형", "역망치형")]
    other = [s for s in items if s not in candle]
    assert candle and other
    assert all(s["next_bar"] in (True, False) for s in candle)
    assert any(s["next_bar"] for s in candle) and not all(s["next_bar"] for s in candle)
    assert all(s["next_bar"] is None for s in other)
    assert all(s["text"].endswith("(다음 봉)") == s["next_bar"] for s in candle)
    assert not any(s["text"].endswith(" - 참고") for s in candle)           # 참고는 기본 꺼짐
