"""
추세선 돌파/이탈 신호(manual_lines.compute_trend_breakout_events / compute_manual_line_state_signals).

수평선 돌파 규칙을 그대로 따른다 (종가 기준, 진입/유지/종료, 다음 수평선 접촉 시 종료). 다른 점은 선 가격이
날짜마다 다르다는 것 하나 - 추세선은 이른 쪽 점(time1)부터 오른쪽으로 끝없이 연장한 직선의 그날 값이다.

핵심 검증:
- 기울기 0인 추세선은 같은 가격 수평선과 (time1 이후) 정확히 같은 돌파 이벤트를 만든다 (같은 스캔 함수 재사용 증명)
- 스캔 함수 일반화 전의 옛 수평선 구현(이 파일에 그대로 복사해 둠)과 일반화 후 래퍼의 결과가 같다 (수평선 불변 증명)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app  # app.services.dashboard가 services 경로를 sys.path에 넣는다

import lines_store  # noqa: E402  (dashboard.py가 쓰는 것과 같은 bare 모듈 객체)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

import manual_lines  # noqa: E402

CREATED = "2026-10-06T01:02:03+00:00"


def _df(rows, start="2025-01-01"):
    return pd.DataFrame({
        "open_time": pd.date_range(start, periods=len(rows), freq="D", tz="UTC"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    })


def _c(close, spread=1.0):
    """종가만 지정한 단순 캔들 (시가=종가, 위아래 spread)."""
    return (close, close + spread, close - spread, close)


def _trend(time1, price1, time2, price2, line_id=11):
    return {"id": line_id, "line_type": "trend", "time1": time1, "price1": float(price1), "time2": time2,
            "price2": float(price2), "created_at": CREATED}


def _hline(price, line_id=7):
    return {"id": line_id, "line_type": "horizontal", "price1": float(price), "time1": None, "time2": None,
            "price2": None, "created_at": CREATED}


def _events(df, line, lines=None):
    levels = manual_lines._horizontal_levels(lines or [line])
    if line["line_type"] == "trend":
        evs = manual_lines.compute_trend_breakout_events(df, line, levels)
    else:
        evs = manual_lines.compute_line_breakout_events(df, line, levels)
    return [(e["direction"], e["trigger_index"], e["state_end_index"], e["end_reason"]) for e in evs]


FLAT_FROM_0102 = _trend("2025-01-02", 100, "2025-01-02", 100)   # 01-02(idx1)부터 오른쪽으로 price 100 수평 연장


# --- 기본 동작: 종가 기준, 진입/유지/종료 ---

def test_up_breakout_enters_stays_and_ends_when_close_returns_below():
    # idx: 0=95(선 없음) 1=95 2=95 3=105(상향 돌파 진입) 4=106(유지) 5=99(종가가 선 아래로 복귀 -> idx4에서 끝)
    df = _df([_c(95), _c(95), _c(95), _c(105), _c(106), _c(99)])
    # idx5 종가 99는 상향 상태를 끝내면서 같은 날 하향 이탈(숏) 상태를 새로 연다
    assert _events(df, FLAT_FROM_0102) == [("up", 3, 4, "reverse"), ("down", 5, 5, "ongoing")]

    sigs = manual_lines.compute_manual_line_state_signals(df, [FLAT_FROM_0102])
    assert [s.text.split("100) ")[-1] for s in sigs[3]] == ["상향 돌파 (롱) 진입"]
    assert [s.text.split("100) ")[-1] for s in sigs[4]] == ["상향 돌파 (롱) 유지 중"]
    assert sigs[3][0].direction == sigs[4][0].direction == "long"
    assert sigs[2] == []
    assert [s.text.split("100) ")[-1] for s in sigs[5]] == ["하향 이탈 (숏) 진입"]   # 복귀한 날 반대 방향이 새로 열림


def test_down_breakout_is_the_mirror_image():
    df = _df([_c(105), _c(105), _c(105), _c(95), _c(94), _c(101)])
    assert _events(df, FLAT_FROM_0102) == [("down", 3, 4, "reverse"), ("up", 5, 5, "ongoing")]
    sigs = manual_lines.compute_manual_line_state_signals(df, [FLAT_FROM_0102])
    assert sigs[3][0].direction == "short" and sigs[3][0].text.endswith("하향 이탈 (숏) 진입")
    assert sigs[4][0].text.endswith("하향 이탈 (숏) 유지 중")


def test_only_the_close_matters_not_the_wick():
    # 윗꼬리가 선(100)을 넘었지만(high 108) 종가는 선 아래(99) -> 돌파 아님
    df = _df([_c(95), _c(95), (96, 108, 94, 99), (97, 109, 95, 98)])
    assert _events(df, FLAT_FROM_0102) == []
    # 시가가 선 위, 종가만 선 위로 마감해도 돌파 (시가는 무관)
    df = _df([_c(95), _c(95), (90, 106, 89, 101)])
    assert _events(df, FLAT_FROM_0102) == [("up", 2, 2, "ongoing")]


def test_the_first_day_of_the_line_cannot_trigger():
    # 직전 날(선 없음)과 비교할 수 없으므로 선이 시작하는 날은 이미 선 위에 있어도 돌파가 아니다
    df = _df([_c(95), _c(105), _c(106), _c(107)])
    assert _events(df, FLAT_FROM_0102) == []


def test_state_stays_open_until_the_last_candle():
    df = _df([_c(95), _c(95), _c(105), _c(106), _c(107)])
    assert _events(df, FLAT_FROM_0102) == [("up", 2, 4, "ongoing")]


# --- 날짜마다 다른 선 가격 / 오른쪽 연장 ---

def test_daily_line_value_is_used_so_a_rising_line_can_cross_a_flat_price():
    # (01-01,100) 하루 +5 -> 선: 100,105,110,115,120. 종가는 112로 계속 같다.
    # 고정 가격 선이었다면 아무 일도 없지만, 오르는 추세선이 112 위로 올라가면서 idx3부터 아래로 이탈한다.
    line = _trend("2025-01-01", 100, "2025-01-03", 110)
    df = _df([_c(112)] * 6)
    assert _events(df, line) == [("down", 3, 5, "ongoing")]


def test_breakout_after_the_second_point_is_caught():
    # 두 점은 01-01~01-03 (선: 100,105,110) 이고 돌파는 두 번째 점 한참 뒤(idx6: 선 130)에 일어난다
    line = _trend("2025-01-01", 100, "2025-01-03", 110)
    closes = [90, 95, 100, 105, 110, 115, 135]          # idx6: 종가 135 > 선 130 (직전 idx5: 115 < 125)
    df = _df([_c(c) for c in closes])
    assert _events(df, line) == [("up", 6, 6, "ongoing")]


def test_same_day_two_points_make_a_flat_ray_from_that_day():
    line = _trend("2025-01-03", 100, "2025-01-03", 777)  # 같은 날 -> price1(100) 고정, 그 날부터 오른쪽
    df = _df([_c(90), _c(90), _c(90), _c(90), _c(105)])
    assert _events(df, line) == [("up", 4, 4, "ongoing")]


def test_reversed_stored_row_starts_at_the_earlier_point():
    line = _trend("2025-01-04", 100, "2025-01-02", 100)  # time1 > time2로 저장된 옛 행 -> 01-02(idx1)부터
    df = _df([_c(95), _c(95), _c(95), _c(105)])
    assert _events(df, line) == [("up", 3, 3, "ongoing")]


def test_descending_line_that_reaches_zero_ends_the_state_as_line_gone():
    line = _trend("2025-01-01", 20, "2025-01-03", 10)    # 하루 -5: 20,15,10,5,0,-5 -> idx4부터 선 가격 0 이하
    df = _df([_c(12, 0.5)] * 7)
    # idx2: 종가 12 > 선 10 (직전 idx1: 12 < 15) -> 상향 돌파. idx3까지 유지, idx4에서 선이 없어져 상태 종료
    assert _events(df, line) == [("up", 2, 3, "line_gone")]


# --- 종료 조건: 다음 수평선 접촉 ---

def test_state_ends_when_the_candle_touches_the_next_horizontal_line():
    df = _df([_c(95), _c(95), _c(105), (105, 111, 104, 106), _c(107)])
    lines = [FLAT_FROM_0102, _hline(110)]
    # idx3의 고가 111이 110(다음 수평선)에 닿음 -> idx2에서 상태 종료
    assert _events(df, FLAT_FROM_0102, lines) == [("up", 2, 2, "next_level")]
    # 수평선이 없으면 계속 유지
    assert _events(df, FLAT_FROM_0102, [FLAT_FROM_0102]) == [("up", 2, 4, "ongoing")]


def test_close_return_wins_over_next_level_touch_on_the_same_candle():
    df = _df([_c(95), _c(95), _c(105), (105, 111, 90, 99)])  # idx3: 110에도 닿고 종가 99로 선 아래 복귀
    assert _events(df, FLAT_FROM_0102, [FLAT_FROM_0102, _hline(110)]) == [("up", 2, 2, "reverse"), ("down", 3, 3, "ongoing")]


def test_next_level_is_fixed_at_the_trigger_day_line_value():
    # 선: 90,91,92,93,94 (하루 +1). 돌파 시작일(idx2, 선 92) 기준 위의 가장 가까운 수평선(112)이 종료선이 된다
    line = _trend("2025-01-01", 90, "2025-01-03", 92)
    df = _df([_c(80), _c(80), _c(95), _c(96), (96, 113, 95, 100)])  # idx4 고가 113 >= 112 -> idx3에서 종료
    assert _events(df, line, [line, _hline(112), _hline(85)]) == [("up", 2, 3, "next_level")]


# --- 같은 스캔 함수 재사용 증명: 기울기 0 추세선 == 같은 가격 수평선 ---

@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_flat_trend_line_behaves_exactly_like_a_horizontal_line_after_its_start(seed):
    rng = np.random.default_rng(seed)
    closes = 100 + np.cumsum(rng.normal(0, 2.0, 400))
    rows = [(c + rng.normal(0, 0.5), c + abs(rng.normal(0, 1.5)), c - abs(rng.normal(0, 1.5)), c) for c in closes]
    df = _df(rows)
    start_idx = 30
    start_date = df["open_time"].iloc[start_idx].strftime("%Y-%m-%d")
    price = float(np.median(closes))
    others = [_hline(price + 6), _hline(price - 6)]     # 다음 수평선 종료 조건도 함께 검증

    trend = _trend(start_date, price, start_date, price)               # 기울기 0
    horiz = _hline(price)
    trend_ev = _events(df, trend, [trend] + others)
    horiz_ev = [e for e in _events(df, horiz, [horiz] + others) if e[1] > start_idx]  # 시작 다음 날부터 판정 가능
    assert trend_ev == horiz_ev
    assert len(trend_ev) > 2, "무작위 데이터에서 돌파가 거의 안 나오면 이 검증이 의미 없다"


# --- 수평선 불변 증명: 일반화 전 구현(그대로 복사)과 일반화 후 래퍼가 같다 ---

def _old_scan_breakout_direction(df, level, next_level, direction):
    """일반화(_scan_breakout_series) 이전의 수평선 돌파 스캔 구현 - 그대로 복사한 기준선."""
    close, low, high = df["close"], df["low"], df["high"]
    n = len(df)
    if direction == "up":
        is_breakout = lambda c: c > level
    else:
        is_breakout = lambda c: c < level
    episodes, in_state, trigger_idx = [], False, None
    for i in range(1, n):
        if not in_state:
            if is_breakout(close.iloc[i]) and not is_breakout(close.iloc[i - 1]):
                in_state, trigger_idx = True, i
            continue
        reversed_ = not is_breakout(close.iloc[i])
        touched_next = next_level is not None and low.iloc[i] <= next_level <= high.iloc[i]
        if reversed_ or touched_next:
            episodes.append({"trigger_index": trigger_idx, "state_end_index": i - 1,
                             "end_reason": "reverse" if reversed_ else "next_level"})
            in_state, trigger_idx = False, None
    if in_state:
        episodes.append({"trigger_index": trigger_idx, "state_end_index": n - 1, "end_reason": "ongoing"})
    return episodes


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("direction", ["up", "down"])
def test_horizontal_breakout_scan_is_identical_to_the_pre_generalization_implementation(seed, direction):
    rng = np.random.default_rng(100 + seed)
    closes = 100 + np.cumsum(rng.normal(0, 2.5, 500))
    df = _df([(c, c + abs(rng.normal(0, 2)), c - abs(rng.normal(0, 2)), c) for c in closes])
    level = float(np.median(closes))
    for next_level in (None, level + 7, level - 7):
        assert manual_lines._scan_breakout_direction(df, level, next_level, direction) == \
            _old_scan_breakout_direction(df, level, next_level, direction)


# --- 신호/대시보드 ---

def test_trend_breakout_signals_carry_ref_fields_and_horizontal_ones_do_not():
    df = _df([_c(95), _c(95), _c(105), _c(106)])
    trend = _trend("2025-01-02", 100, "2025-01-02", 100, line_id=42)
    hline = _hline(100, line_id=7)
    sigs = manual_lines.compute_manual_line_state_signals(df, [trend, hline])
    by_kind = {("추세선" if s.text.startswith("추세선") else "수평선"): s for s in sigs[2]}
    assert by_kind["추세선"].ref_id == 42 and by_kind["추세선"].ref_created_at == CREATED
    assert by_kind["수평선"].ref_id is None and by_kind["수평선"].ref_created_at is None


def test_zone_rows_are_ignored_by_both_line_functions():
    df = _df([_c(95), _c(95), _c(105)])
    zone = {"id": 9, "line_type": "zone", "time1": "2025-01-01", "price1": 110.0, "time2": "2025-01-03",
            "price2": 90.0, "created_at": CREATED}
    assert all(not v for v in manual_lines.compute_manual_line_state_signals(df, [zone]).values())
    assert all(not v for v in manual_lines.compute_manual_line_signals(df, [zone]).values())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


def test_dashboard_lists_trend_breakout_signals_with_ref(client):
    # 2023년 상승 구간 추세선을 오른쪽으로 연장하면 이후 실제 BTC 가격이 그 선을 위/아래로 가로지른다
    body = {"time1": "2023-01-01", "price1": 16500.0, "time2": "2023-12-31", "price2": 44000.0}
    trend_id = client.post("/api/lines/trend", json=body).json()["id"]
    data = client.get("/api/dashboard").json()
    created = next(ln for ln in data["manual_lines"] if ln["id"] == trend_id)["created_at"]

    breakouts = [
        (date, s) for date, v in data["signals"].items() for s in v
        if s["text"].startswith("추세선") and ("돌파" in s["text"] or "이탈" in s["text"])
    ]
    assert breakouts, "연장한 추세선을 실제 가격이 가로지르는 구간이 있어야 함"
    assert all(d >= "2023-01-01" for d, _ in breakouts)
    assert all(s["ref_id"] == trend_id and s["ref_created_at"] == created for _, s in breakouts)
    assert {s["direction"] for _, s in breakouts} <= {"long", "short"}
    assert any(s["text"].endswith("진입") for _, s in breakouts)
