"""
캔들 패턴 신호 규칙 (candle_patterns.compute_candle_pattern_signals) - 2026-10 규칙.

- 숏: 몸통 상단 >= 직전 N개 몸통 상단 최댓값(동률 포함)인 고점 캔들 당일이 모양이면 당일, 아니면 t+1이 모양이면 t+1("(다음 봉)")
- 롱: 직전 캔들이 음봉(몸통 변화율 >= LOW_PREV_BEAR_MIN_PCT)이고 오늘이 모양이면 당일 (다음 봉 규칙 없음, 처음 N개 제한도 없음)
- 같은 캔들에 숏/롱이 동시에 걸리면 둘 다 (롱 -> 숏 순서)
- 장대봉(몸통 >= BIG_CANDLE_MIN_PCT)/급등락 후 BIG_CANDLE_SUPPRESS_BARS봉 안의 반대 방향 신호는 "무효"(reference)와 원인 문구
- 참고는 feature_flags.ENABLE_CANDLE_REFERENCE=True일 때만, 신호(무효 포함)가 없는 모양 캔들에
- 예전 몸통 신저점 롱 판정은 USE_BODY_NEW_LOW_FOR_LONG=True로 되살릴 수 있다(미사용)
- 미래 참조 없음(뒤쪽 캔들을 잘라도 앞쪽 신호는 같다)

합성 데이터는 N=3(n_lookback=3)으로 짧게 만든다. 모양은 도지(몸통 0, 두 꼬리 같음), 모양이 아닌 캔들은 몸통이 큰 양/음봉을 쓴다.
날짜는 idx 0 = 2025-01-01 이라 idx k의 "MM/DD"는 01/(k+1)이다.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

import lines_store  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

import candle_patterns  # noqa: E402
import feature_flags  # noqa: E402
import pipeline  # noqa: E402
import volatility_expansion  # noqa: E402

N = 3
ORIGINAL_REFERENCE_DEFAULT = feature_flags.ENABLE_CANDLE_REFERENCE   # fixture가 바꾸기 전의 실제 기본값


@pytest.fixture(autouse=True)
def _reference_off_by_default_in_this_module(monkeypatch):
    """신호 테스트는 신호만 본다 - 참고(reference)는 끄고, 참고 테스트가 직접 켠다."""
    monkeypatch.setattr(feature_flags, "ENABLE_CANDLE_REFERENCE", False)


def big(top, bottom=None):
    """모양 아닌 양봉: 몸통 = bottom~top (기본 10), 꼬리는 1씩."""
    bottom = top - 10 if bottom is None else bottom
    return (bottom, top + 1, bottom - 1, top)


def bear(open_, close):
    """모양 아닌 음봉."""
    return (open_, open_ + 1, close - 1, close)


def doji(mid, wick=5.0):
    """도지: 시가 = 종가 = mid, 위아래 꼬리 같음."""
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


BASE = [big(1000)] * N    # 몸통 990~1000 세 개 (몸통 1%라 장대봉이 아니고, 3봉 누적도 급등이 아니다)

BIG_BULL = (1000, 1041, 999, 1040)     # 몸통 4.0% >= 3.5% 장대 양봉
BIG_BEAR = (999, 1000, 958, 959)       # 몸통 4.004% 장대 음봉


def step_bars(up, n=3, start=1000.0, body=0.034, gap=0.015):
    """몸통 3.4%(장대봉 3.5% 미만)에 매 봉 1.5% 갭을 이어 붙인 n개 봉 - 3봉 누적이 급등/급락(봉당 4%)이 되게 한다."""
    rows, prev_close = [], None
    for _ in range(n):
        o = start if prev_close is None else prev_close * ((1 + gap) if up else (1 - gap))
        c = o * ((1 + body) if up else (1 - body))
        rows.append((o, c * 1.001, o * 0.999, c) if up else (o, o * 1.001, c * 0.999, c))
        prev_close = c
    return rows


# --- 숏: 고점 캔들 당일 / 다음 봉 ---

def test_high_candle_that_is_a_pattern_signals_short_the_same_day():
    assert run(BASE + [doji(1050)]) == {3: [("도지 - 숏 후보", "short", False)]}


def test_tie_with_the_previous_max_counts_as_a_high_candle():
    assert run(BASE + [doji(1000)]) == {3: [("도지 - 숏 후보", "short", False)]}   # 몸통 상단 1000 >= 최댓값 1000
    assert run(BASE + [doji(999.99)]) == {}


def test_next_bar_short_when_the_high_candle_is_not_a_pattern():
    # idx3: 장대 아닌 양봉(몸통 상단 1030, 고점 캔들, 모양 아님) -> idx4 도지(상단 1005, 고점 아님)에서 신호
    assert run(BASE + [big(1030), doji(1005)]) == {4: [("도지 - 숏 후보 (다음 봉)", "short", True)]}


def test_both_patterns_only_the_high_candle_signals():
    assert run(BASE + [doji(1050), doji(1040)]) == {3: [("도지 - 숏 후보", "short", False)]}


def test_next_bar_that_is_a_new_high_is_judged_on_its_own_as_a_same_day_signal():
    assert run(BASE + [big(1030), doji(1050)]) == {4: [("도지 - 숏 후보", "short", False)]}


def test_chain_of_new_highs_signals_once_when_the_pattern_finally_appears():
    assert run(BASE + [big(1030), big(1060), doji(1040)]) == {5: [("도지 - 숏 후보 (다음 봉)", "short", True)]}


def test_only_the_next_candle_is_checked_not_t_plus_2():
    assert run(BASE + [big(1030), big(1000), doji(1010)]) == {}


def test_wicks_are_ignored_for_the_high_test():
    assert run(BASE + [doji(995, wick=50)]) == {}    # 위꼬리는 1045까지 가지만 몸통 상단은 995


def test_short_needs_the_first_n_candles_but_long_does_not():
    assert run([doji(2000), big(1000), big(1000)]) == {}                     # 처음 N개는 고점 캔들이 될 수 없다
    assert run([big(1000)] * 3 + [doji(1050)]) != {}
    # 롱은 직전 캔들만 보므로 처음 N개 제한이 없다: idx1이 N(=3)보다 앞이어도 신호
    assert run([bear(999, 989), doji(995)]) == {1: [("도지 - 롱 후보", "long", False)]}


# --- 롱: 직전 음봉 + 오늘 모양 ---

def test_long_when_previous_candle_is_bearish_and_today_is_a_pattern():
    assert run(BASE + [bear(999, 989), doji(995)]) == {4: [("도지 - 롱 후보", "long", False)]}


def test_no_long_when_previous_candle_is_bullish_or_flat():
    assert run(BASE + [doji(995)]) == {}                                      # 직전 양봉
    assert run(BASE + [bear(999, 989), doji(995), doji(994)]) == {            # 직전이 도지(시가 = 종가)는 음봉이 아니다
        4: [("도지 - 롱 후보", "long", False)]}


def test_long_has_no_next_bar_rule():
    # idx5 도지는 직전(idx4)이 음봉이라 당일 롱. 롱에는 "다음 봉 이월"이 없고 next_bar는 항상 False
    out = run(BASE + [bear(999, 989), bear(989, 980), doji(975)])
    assert out == {5: [("도지 - 롱 후보", "long", False)]}


def test_low_prev_bear_min_pct_threshold(monkeypatch):
    rows = BASE + [bear(999, 989), doji(995)]                                 # 직전 음봉 몸통 변화율 10/999 = 1.001%
    monkeypatch.setattr(candle_patterns, "LOW_PREV_BEAR_MIN_PCT", 1.0)
    assert run(rows) != {}
    monkeypatch.setattr(candle_patterns, "LOW_PREV_BEAR_MIN_PCT", 1.01)
    assert run(rows) == {}


def test_same_candle_can_have_long_and_short_both_shown_long_first():
    # idx3 음봉(고점 아님), idx4 도지(고점 캔들): 직전 음봉 -> 롱, 고점 캔들 -> 숏
    assert run(BASE + [bear(999, 989), doji(1050)]) == {
        4: [("도지 - 롱 후보", "long", False), ("도지 - 숏 후보", "short", False)]}


def test_old_body_new_low_long_rule_is_kept_but_unused(monkeypatch):
    rows = BASE + [big(985, 975), doji(980)]    # idx3: 몸통 하단 975 < 직전 N개 최솟값 990(저점 캔들, 모양 아님) -> idx4 다음 봉
    assert run(rows) == {}                       # 기본(새 규칙): 직전이 양봉이라 롱 없음
    monkeypatch.setattr(candle_patterns, "USE_BODY_NEW_LOW_FOR_LONG", True)
    assert run(rows) == {4: [("도지 - 롱 후보 (다음 봉)", "long", True)]}      # 예전 규칙(다음 봉 포함)이 그대로 살아난다


# --- 무효: 장대봉 / 급등락 (숏은 상승 원인, 롱은 하락 원인) ---

def test_big_bullish_candle_invalidates_a_short_with_the_cause_in_the_text():
    log = []
    sigs = candle_patterns.compute_candle_pattern_signals(
        make_df(BASE + [BIG_BULL, doji(1050)]), None, invalidated_log=log, n_lookback=N)
    assert [(s.text, s.direction, s.next_bar) for s in sigs[4]] == [("도지 - 숏 무효 (장대 양봉 01/04)", "reference", False)]
    assert log and log[0]["index"] == 4 and log[0]["signal_text"] == "도지 - 숏 후보"
    assert log[0]["cause"] == "장대 양봉 01/04" and log[0]["n"] is None


def test_big_bearish_candle_invalidates_a_long():
    assert run(BASE + [BIG_BEAR, doji(960)]) == {4: [("도지 - 롱 무효 (장대 음봉 01/04)", "reference", False)]}


def test_next_bar_invalidation_keeps_the_next_bar_suffix():
    rows = BASE + [BIG_BULL, doji(1030)]     # idx3 장대 양봉(고점) -> idx4 도지(상단 1030 < 1040)는 다음 봉 숏
    assert run(rows) == {4: [("도지 - 숏 무효 (장대 양봉 01/04) (다음 봉)", "reference", True)]}


def test_opposite_direction_big_candle_does_not_invalidate():
    # 숏을 막는 건 상승 원인뿐: 하락 장대봉 뒤 도지가 고점 캔들이면 롱은 무효지만 숏은 후보 그대로
    assert run(BASE + [BIG_BEAR, doji(1050)]) == {4: [("도지 - 롱 무효 (장대 음봉 01/04)", "reference", False),
                                                      ("도지 - 숏 후보", "short", False)]}
    # 롱을 막는 건 하락 원인뿐: 상승 장대봉 2봉 전, 직전은 평범한 음봉 -> 롱 후보 그대로
    assert run(BASE + [BIG_BULL, bear(1035, 1025), doji(1020)]) == {5: [("도지 - 롱 후보", "long", False)]}


def test_suppress_window_is_bounded_by_big_candle_suppress_bars(monkeypatch):
    rows = BASE + [BIG_BULL, big(1000), doji(1045)]    # idx3 장대 양봉, idx5 도지(고점 캔들): 장대봉이 2봉 전
    assert run(rows) == {5: [("도지 - 숏 무효 (장대 양봉 01/04)", "reference", False)]}
    monkeypatch.setattr(candle_patterns, "BIG_CANDLE_SUPPRESS_BARS", 1)
    assert run(rows) == {5: [("도지 - 숏 후보", "short", False)]}            # 1봉이면 idx3는 범위 밖


def test_big_candle_threshold_is_inclusive(monkeypatch):
    rows = BASE + [(1000, 1036, 999, 1035), doji(1050)]    # 몸통 3.5%
    assert run(rows) == {4: [("도지 - 숏 무효 (장대 양봉 01/04)", "reference", False)]}
    monkeypatch.setattr(candle_patterns, "BIG_CANDLE_MIN_PCT", 3.51)
    assert run(rows) == {4: [("도지 - 숏 후보", "short", False)]}


def test_surge_invalidates_a_short_and_crash_invalidates_a_long():
    up = step_bars(True)                          # 장대봉은 아니지만(3.4%) 3봉 누적 +13.9% = 봉당 4.6%
    assert run(up + [doji(up[-1][3] * 1.02)]) == {3: [("도지 - 숏 무효 (급등 3봉 01/01~01/03)", "reference", False)]}
    down = step_bars(False)
    assert run(down + [doji(down[-1][3] * 0.98)]) == {3: [("도지 - 롱 무효 (급락 3봉 01/01~01/03)", "reference", False)]}


def test_surge_up_matches_volatility_expansion_module_on_real_data():
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    ve = volatility_expansion.compute_volatility_expansion(df)
    expected = {(j, w) for w in volatility_expansion.WINDOWS for j in range(len(df)) if ve[f"expansion_{w}"].iloc[j]}
    got = {(j, w) for j, ms in candle_patterns._surge_matches(df)["up"].items() for w, _, _ in ms}
    assert got == expected and expected
    assert candle_patterns._surge_matches(df)["down"]                         # 하락 방향 대칭도 실데이터에서 잡힌다


# --- 참고 (기본 켜짐, 신호/무효가 없는 모양 캔들에만) ---

def test_reference_is_on_by_default_only_for_shapes_without_a_signal_and_can_be_turned_off(monkeypatch):
    rows = BASE + [doji(1050), doji(1005), doji(1006)]    # idx3 숏 신호, idx4/5는 모양인데 신호 없음
    assert ORIGINAL_REFERENCE_DEFAULT is True                           # 실제 기본값은 켜짐
    monkeypatch.setattr(feature_flags, "ENABLE_CANDLE_REFERENCE", True)
    ref = ("도지 - 참고 (고점/저점 아님)", "reference", False)
    on = run(rows)
    assert on[3] == [("도지 - 숏 후보", "short", False)]               # 신호가 있는 캔들에는 참고를 안 붙인다
    assert on[4] == [ref] and on[5] == [ref]
    # 무효도 신호가 난 것이므로 참고를 안 붙인다
    assert run(BASE + [BIG_BULL, doji(1050)]) == {4: [("도지 - 숏 무효 (장대 양봉 01/04)", "reference", False)]}

    monkeypatch.setattr(feature_flags, "ENABLE_CANDLE_REFERENCE", False)
    assert run(rows) == {3: [("도지 - 숏 후보", "short", False)]}        # 끄면 아무것도 안 낸다


def test_reference_keeps_near_zone_flag_and_does_not_count_as_long_or_short(monkeypatch):
    monkeypatch.setattr(feature_flags, "ENABLE_CANDLE_REFERENCE", True)
    zone = {"id": 1, "line_type": "zone", "time1": "2025-01-01", "price1": 1000.0, "time2": "2025-12-31",
            "price2": 990.0, "created_at": "x"}
    rows = BASE + [doji(995)]                                           # 고점도 아니고 직전 음봉도 아닌 도지
    sigs = candle_patterns.compute_candle_pattern_signals(make_df(rows), None, zones=[zone], n_lookback=N)
    s = sigs[3][0]
    assert (s.text, s.direction, s.near_zone, s.next_bar) == ("도지 - 참고 (고점/저점 아님)", "reference", True, False)
    far = {**zone, "price1": 2010.0, "price2": 2000.0}
    sigs = candle_patterns.compute_candle_pattern_signals(make_df(rows), None, zones=[far], n_lookback=N)
    assert sigs[3][0].near_zone is False
    assert candle_patterns.compute_candle_pattern_signals(make_df(rows), None)[3][0].near_zone is None


# --- near_zone / 상수 ---

def test_near_zone_is_set_on_the_signal_candle():
    zone = {"id": 1, "line_type": "zone", "time1": "2025-01-01", "price1": 1060.0, "time2": "2025-12-31",
            "price2": 1040.0, "created_at": "x"}
    sigs = candle_patterns.compute_candle_pattern_signals(make_df(BASE + [doji(1050)]), None, zones=[zone], n_lookback=N)
    assert sigs[3][0].near_zone is True and sigs[3][0].next_bar is False
    sigs = candle_patterns.compute_candle_pattern_signals(make_df(BASE + [doji(1050)]), None, zones=[], n_lookback=N)
    assert sigs[3][0].near_zone is False


def test_rule_constants_and_defaults(monkeypatch):
    assert candle_patterns.POSITION_LOOKBACK_N == 10
    assert candle_patterns.LOW_PREV_BEAR_MIN_PCT == 0.0
    assert candle_patterns.BIG_CANDLE_MIN_PCT == 3.5
    assert candle_patterns.BIG_CANDLE_SUPPRESS_BARS == 2
    assert candle_patterns.USE_BODY_NEW_LOW_FOR_LONG is False
    assert candle_patterns.SURGE_CUM_PCT_PER_N_MIN == volatility_expansion.CUM_PCT_PER_N_MIN == 4.0
    assert list(candle_patterns.SURGE_WINDOWS) == list(volatility_expansion.WINDOWS) == [3, 4]
    df = make_df(BASE + [doji(1050)])
    assert candle_patterns.compute_candle_pattern_signals(df, None) == {i: [] for i in range(len(df))}  # N=10: 숏은 캔들 부족
    monkeypatch.setattr(candle_patterns, "POSITION_LOOKBACK_N", 3)
    assert [s.text for s in candle_patterns.compute_candle_pattern_signals(df, None)[3]] == ["도지 - 숏 후보"]


def test_manual_signals_argument_is_ignored():
    from signal_types import Signal
    rows = BASE + [doji(1050)]
    plain = run(rows)
    with_lines = candle_patterns.compute_candle_pattern_signals(
        make_df(rows), {i: [Signal("x", "long")] for i in range(len(rows))}, n_lookback=N)
    assert {i: [(s.text, s.direction, s.next_bar) for s in v] for i, v in with_lines.items() if v} == plain


# --- 실데이터: 독립 구현과 일치 / 미래 참조 없음 ---

@pytest.fixture(scope="module")
def real_df():
    df, _, _ = pipeline.load_dashboard_data()
    return df.reset_index(drop=True)


def _expected_events(df, n_lookback=10):
    """규칙을 독립적으로 다시 구현한 기대값: {(신호 캔들, 방향, 패턴, next_bar)} - 무효 처리 전."""
    shape = candle_patterns.compute_candle_shape(df)["shape"].tolist()
    name = candle_patterns.PATTERN_LABEL_KR
    o, c = df["open"].tolist(), df["close"].tolist()
    top = [max(a, b) for a, b in zip(o, c)]
    n = len(df)
    high = [t >= n_lookback and top[t] >= max(top[t - n_lookback:t]) for t in range(n)]
    ev = {}
    for t in range(n):
        if high[t]:
            if shape[t]:
                ev[(t, "short")] = (name[shape[t]], False)
            elif t + 1 < n and shape[t + 1]:
                ev.setdefault((t + 1, "short"), (name[shape[t + 1]], not high[t + 1]))
    for t in range(1, n):
        if shape[t] and c[t - 1] < o[t - 1] and (o[t - 1] - c[t - 1]) / o[t - 1] * 100 >= 0:
            ev[(t, "long")] = (name[shape[t]], False)
    return {(i, d, p, nb) for (i, d), (p, nb) in ev.items()}


def test_matches_an_independent_implementation_on_real_data(real_df):
    expected = _expected_events(real_df)
    sigs = candle_patterns.compute_candle_pattern_signals(real_df, None)
    got, kinds = set(), {"롱 후보": 0, "숏 후보": 0, "롱 무효": 0, "숏 무효": 0}
    for i, v in sigs.items():
        for s in v:
            label, rest = s.text.split(" - ", 1)
            kind = rest.replace(" (다음 봉)", "").split(" (")[0]
            kinds[kind] += 1
            got.add((i, "long" if kind.startswith("롱") else "short", label, s.next_bar))
            assert (s.direction == "reference") == kind.endswith("무효")
    assert got == expected and all(v > 0 for v in kinds.values())
    assert sum(1 for _, d, _, nb in got if d == "long" and nb) == 0         # 롱에는 다음 봉이 없다


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


def test_dashboard_exposes_next_bar_only_on_candle_pattern_signals(client, monkeypatch):
    monkeypatch.setattr(feature_flags, "ENABLE_CANDLE_REFERENCE", True)
    data = client.get("/api/dashboard").json()
    items = [s for v in data["signals"].values() for s in v]
    candle = [s for s in items if s["text"].split(" - ")[0] in ("도지", "망치형", "역망치형")]
    other = [s for s in items if s not in candle]
    assert candle and other
    assert all(s["next_bar"] in (True, False) for s in candle)
    assert any(s["next_bar"] for s in candle) and not all(s["next_bar"] for s in candle)
    assert all(s["next_bar"] is None for s in other)
    assert all(s["text"].endswith("(다음 봉)") == s["next_bar"] for s in candle)
    refs = [s for s in candle if "참고" in s["text"]]
    assert refs and all(s["text"].endswith("참고 (고점/저점 아님)") and s["direction"] == "reference" for s in refs)
    invalid = [s for s in candle if " 무효 (" in s["text"]]
    assert invalid and all(s["direction"] == "reference" for s in invalid)
    assert {s["text"].split(" - ")[1].startswith("롱") for s in invalid} == {True, False}      # 롱 무효 / 숏 무효 둘 다
