"""
기능1 개편 3b단계: 존 신호 판정(zone_signals.py) 단위 테스트 - 가짜 캔들 사용.

존: 상단 T=110, 하단 B=100. 캔들은 (시가, 고가, 저가, 종가). 날짜는 2025-01-01부터 하루씩.
"""
import random
import sys
from pathlib import Path

import pandas as pd

SERVICES_DIR = Path(__file__).resolve().parents[1] / "app" / "services"
sys.path.insert(0, str(SERVICES_DIR))

import zone_signals  # noqa: E402

T, B = 110.0, 100.0
CREATED = "2026-10-06T01:09:20+00:00"


def _df(rows):
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=len(rows), freq="D", tz="UTC"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    })


def _zone(time1="2025-01-01", time2="2025-12-31", zone_id=7):
    return {"id": zone_id, "line_type": "zone", "time1": time1, "price1": T, "time2": time2,
            "price2": B, "created_at": CREATED}


def _run(rows, first_touch_only=True, **zone_kw):
    sigs = zone_signals.compute_zone_signals(_df(rows), [_zone(**zone_kw)], first_touch_only=first_touch_only)
    return [(i, s.text, s.direction) for i, lst in sigs.items() for s in lst]


ABOVE = (120, 121, 119, 120)   # 존 위에서 마감(다음 날의 직전 종가 = 120)
BELOW = (90, 91, 89, 90)       # 존 아래에서 마감(직전 종가 = 90)
INSIDE = (105, 106, 104, 105)  # 존 안에서 마감(직전 종가 = 105)


# --- 반응 ---

def test_support_reaction_from_above():
    out = _run([ABOVE, (115, 116, 108, 112)])  # O>=T, L<=T, C>=B
    assert out == [(1, "존 100~110 지지 반응 (매수 후보)", "long")]


def test_support_reaction_may_close_inside_zone():
    out = _run([ABOVE, (115, 116, 108, 105)])
    assert out == [(1, "존 100~110 지지 반응 (매수 후보)", "long")]


def test_resistance_reaction_from_below():
    out = _run([BELOW, (95, 102, 94, 98)])  # O<=B, H>=B, C<=T
    assert out == [(1, "존 100~110 저항 반응 (매도 후보)", "short")]


def test_no_reaction_when_candle_does_not_reach_zone():
    assert _run([ABOVE, (118, 119, 112, 115)]) == []   # 저가 112 > 상단
    assert _run([BELOW, (95, 98, 94, 96)]) == []       # 고가 98 < 하단


def test_open_exactly_on_boundary_uses_boundary_rules():
    assert _run([ABOVE, (110, 111, 108, 109)]) == [(1, "존 100~110 지지 반응 (매수 후보)", "long")]  # O==T
    assert _run([BELOW, (100, 102, 94, 98)]) == [(1, "존 100~110 저항 반응 (매도 후보)", "short")]    # O==B


# --- 갭으로 존 안에서 시작 ---

def test_gap_open_inside_zone_with_previous_close_above_is_support():
    out = _run([ABOVE, (105, 106, 103, 104)])
    assert out == [(1, "존 100~110 지지 반응 (매수 후보)", "long")]


def test_gap_open_inside_zone_with_previous_close_below_is_resistance():
    out = _run([BELOW, (105, 106, 103, 104)])
    assert out == [(1, "존 100~110 저항 반응 (매도 후보)", "short")]


def test_gap_open_inside_zone_with_previous_close_inside_gives_no_signal():
    assert _run([INSIDE, (105, 106, 103, 104)]) == []


def test_gap_open_inside_zone_then_closing_beyond_is_exit_not_reaction():
    # 직전 종가 위, 시가 존 안, 종가가 하단 아래 -> 하방 이탈 하나만
    assert _run([ABOVE, (105, 106, 98, 99)]) == [(1, "존 100~110 하방 이탈 (숏)", "short")]
    assert _run([BELOW, (105, 112, 104, 111)]) == [(1, "존 100~110 상방 이탈 (롱)", "long")]


# --- 이탈 ---

def test_upside_exit_first_day_only():
    rows = [INSIDE, (106, 114, 105, 112), (112, 116, 111, 115)]
    out = _run(rows)
    assert out == [(1, "존 100~110 상방 이탈 (롱)", "long")]  # 둘째 날은 직전 종가가 이미 상단 위


def test_downside_exit_first_day_only():
    rows = [INSIDE, (104, 105, 96, 98), (98, 99, 94, 95)]
    assert _run(rows) == [(1, "존 100~110 하방 이탈 (숏)", "short")]


def test_exit_requires_close_strictly_beyond_boundary():
    assert _run([INSIDE, (106, 112, 105, 110)]) == []   # 종가 == 상단 -> 이탈 아님
    assert _run([INSIDE, (104, 106, 98, 100)]) == []    # 종가 == 하단 -> 이탈 아님


def test_jump_across_whole_zone_is_exit():
    assert _run([BELOW, (95, 125, 94, 120)]) == [(1, "존 100~110 상방 이탈 (롱)", "long")]
    assert _run([ABOVE, (118, 119, 85, 90)]) == [(1, "존 100~110 하방 이탈 (숏)", "short")]


def test_reaction_and_exit_do_not_overlap_exit_wins():
    # 직전 종가 존 안, 시가 갭상승(>=T), 저가가 존 안으로, 종가가 상단 위: 이탈 하나만(반응 아님)
    for first_touch_only in (True, False):
        out = _run([INSIDE, (112, 116, 108, 115)], first_touch_only=first_touch_only)
        assert out == [(1, "존 100~110 상방 이탈 (롱)", "long")]


def test_reaction_excluded_when_close_crosses_to_opposite_side():
    # 롱 반응 조건에서 종가가 하단 아래면 반응이 아니라 하방 이탈
    assert _run([ABOVE, (115, 116, 95, 97)]) == [(1, "존 100~110 하방 이탈 (숏)", "short")]
    # 숏 반응 조건에서 종가가 상단 위면 상방 이탈
    assert _run([BELOW, (95, 120, 94, 115)]) == [(1, "존 100~110 상방 이탈 (롱)", "long")]


# --- 안에 머무는 날 / 중복 ---

def test_candles_staying_inside_zone_give_no_signal():
    rows = [INSIDE, (105, 108, 102, 106), (106, 109, 101, 103), (103, 107, 100, 104)]
    assert _run(rows) == []


def test_at_most_one_signal_per_zone_per_day_and_never_both_directions():
    rng = random.Random(1234)
    price = 105.0
    rows = []
    for _ in range(3000):
        o = price + rng.uniform(-8, 8)
        c = o + rng.uniform(-10, 10)
        h = max(o, c) + rng.uniform(0, 6)
        l = min(o, c) - rng.uniform(0, 6)
        rows.append((o, h, l, c))
        price = c
    for first_touch_only in (True, False):
        sigs = zone_signals.compute_zone_signals(_df(rows), [_zone()], first_touch_only=first_touch_only)
        assert sum(len(v) for v in sigs.values()) > 30  # 의미 있는 표본인지
        for lst in sigs.values():
            assert len(lst) <= 1


def test_two_zones_each_give_their_own_signal():
    sigs = zone_signals.compute_zone_signals(
        _df([ABOVE, (115, 116, 108, 112)]), [_zone(zone_id=1), _zone(zone_id=2)])
    assert [s.ref_id for s in sigs[1]] == [1, 2]


# --- B안(직전 종가가 존 밖일 때만) vs A안 ---

def test_first_touch_only_skips_reaction_when_previous_close_is_inside_zone():
    rows = [ABOVE, (115, 116, 108, 105), (112, 113, 108, 109)]
    #       0: 존 위 마감 / 1: 반응(종가 존 안) / 2: 갭상승 시작, 존 터치, 존 안에서 마감
    assert _run(rows, first_touch_only=True) == [(1, "존 100~110 지지 반응 (매수 후보)", "long")]
    assert _run(rows, first_touch_only=False) == [
        (1, "존 100~110 지지 반응 (매수 후보)", "long"),
        (2, "존 100~110 지지 반응 (매수 후보)", "long"),
    ]


def test_first_candle_without_previous_close():
    rows = [(115, 116, 108, 112)]
    assert _run(rows, first_touch_only=True) == []                                           # B안: 직전 종가 필요
    assert _run(rows, first_touch_only=False) == [(0, "존 100~110 지지 반응 (매수 후보)", "long")]
    assert _run([(105, 106, 103, 104)], first_touch_only=False) == []                         # 갭 규칙도 직전 종가 필요


# --- 유효 기간 ---

def test_validity_window_is_inclusive_on_both_ends():
    rows = [ABOVE] + [(115, 116, 108, 112)] * 6   # 인덱스 1~6이 매일 지지 반응(직전 종가 > T)
    # 날짜: idx0=01-01 ... idx3=01-04, idx5=01-06
    out = _run(rows, time1="2025-01-03", time2="2025-01-05")
    assert [i for i, *_ in out] == [2, 3, 4]       # time1 당일(idx2)과 time2 당일(idx4) 포함, 그 밖은 제외


def test_candles_before_time1_provide_previous_close_but_are_not_evaluated():
    rows = [ABOVE, (115, 116, 108, 112)]
    assert _run(rows, time1="2025-01-02", time2="2025-12-31") == [(1, "존 100~110 지지 반응 (매수 후보)", "long")]
    assert _run(rows, time1="2025-01-03", time2="2025-12-31") == []


def test_nothing_after_time2():
    rows = [ABOVE, (115, 116, 108, 112), (112, 113, 108, 111)]
    assert _run(rows, time1="2025-01-01", time2="2025-01-02") == [(1, "존 100~110 지지 반응 (매수 후보)", "long")]


# --- 신호 필드 / 다른 선 종류 ---

def test_signal_fields_source_tier_evidence_and_refs():
    sigs = zone_signals.compute_zone_signals(_df([ABOVE, (115, 116, 108, 112)]), [_zone(zone_id=42)])
    (s,) = sigs[1]
    assert (s.source, s.tier, s.evidence, s.ref_id, s.ref_created_at) == ("zone", None, (), 42, CREATED)


def test_non_zone_lines_and_empty_inputs_are_ignored():
    hline = {"id": 1, "line_type": "horizontal", "price1": 105.0, "time1": None, "time2": None,
             "price2": None, "created_at": CREATED}
    sigs = zone_signals.compute_zone_signals(_df([ABOVE, (115, 116, 108, 112)]), [hline])
    assert all(not v for v in sigs.values())
    assert all(not v for v in zone_signals.compute_zone_signals(_df([ABOVE]), []).values())


def test_text_shows_price_range():
    out = _run([ABOVE, (115, 116, 108, 112)])
    assert out[0][1].startswith("존 100~110 ")
