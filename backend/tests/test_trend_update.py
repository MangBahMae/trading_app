"""
추세선 개선: 끝점 드래그 수정용 PUT /api/lines/trend/{line_id}, POST/PUT 공통 검증, 그리고 추세선
신호가 "time1(이른 쪽 점)부터 오른쪽으로 끝없이 연장한 직선"을 평가하는 규칙(time1 이전은 평가 안 함).
(한동안 "두 점 사이 선분만" 평가했지만, 추세선 돌파는 대부분 두 번째 점 이후에 일어나서 연장 규칙으로 되돌렸다.)

- PUT: 값 갱신, id 유지, created_at은 수정한 시각으로 갱신 / 추세선이 아닌 행·없는 id는 404 / 틀린 값은 422
- POST/PUT 공통: 가격 양수, 날짜 형식(YYYY-MM-DD), 시작 <= 끝(같은 날 허용)
- 신호: time1 전날까지는 신호 없음, time1 당일부터 오른쪽(time2 이후 포함)으로 계속 평가, ref_id/ref_created_at 채움

실데이터 manual_lines.db는 건드리지 않는다 - lines_store.DB_PATH를 임시 파일로 바꿔서 쓴다.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app  # app.services.dashboard가 services 경로를 sys.path에 넣는다

import lines_store  # noqa: E402  (dashboard.py가 쓰는 것과 같은 bare 모듈 객체)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

import manual_lines  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


# 실제 BTC 일봉과 겹쳐서 신호가 나오는 모양(2023년 상승 구간 / 2024년)
TREND_A = {"time1": "2023-01-01", "price1": 16500.0, "time2": "2023-12-31", "price2": 44000.0}
TREND_B = {"time1": "2024-03-01", "price1": 60000.0, "time2": "2024-12-31", "price2": 100000.0}


def _lines(client):
    return {ln["id"]: ln for ln in client.get("/api/dashboard").json()["manual_lines"]}


# --- PUT ---

def test_update_trend_changes_values_keeps_id_and_refreshes_created_at(client):
    trend_id = client.post("/api/lines/trend", json=TREND_A).json()["id"]
    before = _lines(client)[trend_id]

    resp = client.put(f"/api/lines/trend/{trend_id}", json=TREND_B)
    assert resp.status_code == 200
    assert resp.json() == {"id": trend_id}

    lines = _lines(client)
    assert list(lines) == [trend_id]  # 새 행이 생기지 않고 id 유지
    after = lines[trend_id]
    assert (after["time1"], after["price1"], after["time2"], after["price2"]) == (
        "2024-03-01", 60000.0, "2024-12-31", 100000.0)
    assert after["line_type"] == "trend"
    assert after["created_at"] > before["created_at"]  # ISO 문자열이라 사전순 = 시간순


def test_update_trend_allows_same_day(client):
    trend_id = client.post("/api/lines/trend", json=TREND_A).json()["id"]
    same_day = {"time1": "2024-05-01", "price1": 60000.0, "time2": "2024-05-01", "price2": 65000.0}
    assert client.put(f"/api/lines/trend/{trend_id}", json=same_day).status_code == 200
    after = _lines(client)[trend_id]
    assert (after["time1"], after["time2"], after["price1"], after["price2"]) == (
        "2024-05-01", "2024-05-01", 60000.0, 65000.0)   # 있는 그대로 저장(POST와 동일)


def test_update_trend_on_non_trend_row_returns_404_and_changes_nothing(client):
    hline_id = client.post("/api/lines/horizontal", json={"price": 28000.0}).json()["id"]
    zone_id = client.post("/api/lines/zone", json={
        "time1": "2026-01-01", "price1": 100.0, "time2": "2026-02-01", "price2": 90.0}).json()["id"]
    before = _lines(client)
    for line_id in (hline_id, zone_id):
        assert client.put(f"/api/lines/trend/{line_id}", json=TREND_B).status_code == 404
    assert _lines(client) == before


def test_update_trend_on_missing_id_returns_404(client):
    assert client.put("/api/lines/trend/99999", json=TREND_B).status_code == 404


INVALID_PATCHES = [
    {"price1": 0.0},                                   # 가격 0
    {"price2": -1.0},                                  # 가격 음수
    {"time1": "2026-02-01", "time2": "2026-01-01"},    # 시작 > 끝
    {"time1": "2026/01/01"},                           # 날짜 형식
    {"time2": "not-a-date"},
    {"time1": "20260101"},
    {"time1": "2026-02-30"},                           # 없는 날짜
]


@pytest.mark.parametrize("patch", INVALID_PATCHES)
def test_update_trend_rejects_invalid_values_and_keeps_original(client, patch):
    trend_id = client.post("/api/lines/trend", json=TREND_A).json()["id"]
    before = _lines(client)[trend_id]
    assert client.put(f"/api/lines/trend/{trend_id}", json={**TREND_B, **patch}).status_code == 422
    assert _lines(client)[trend_id] == before  # 값도 created_at도 그대로


def test_update_trend_rejects_missing_fields(client):
    trend_id = client.post("/api/lines/trend", json=TREND_A).json()["id"]
    assert client.put(f"/api/lines/trend/{trend_id}", json={"price1": 2.0, "price2": 1.0}).status_code == 422


# --- POST 검증 보완(날짜 형식, 가격 양수, 시작 <= 끝) - 정상 요청은 그대로 통과 ---

@pytest.mark.parametrize("patch", INVALID_PATCHES)
def test_post_trend_rejects_invalid_values(client, patch):
    assert client.post("/api/lines/trend", json={**TREND_A, **patch}).status_code == 422
    assert _lines(client) == {}


@pytest.mark.parametrize("body", [
    TREND_A,
    {"time1": "2026-01-01", "price1": 100.0, "time2": "2026-02-01", "price2": 120.0},  # 기존 테스트가 쓰던 값
    {"time1": "2026-10-01", "price1": 80000.0, "time2": "2027-03-01", "price2": 120000.0},  # 미래 날짜
    {"time1": "2024-05-01", "price1": 60000.0, "time2": "2024-05-01", "price2": 61000.0},   # 같은 날
    {"time1": "2024-05-01", "price1": 70000.0, "time2": "2024-06-01", "price2": 60000.0},   # 내려가는 선
])
def test_post_trend_accepts_normal_requests(client, body):
    resp = client.post("/api/lines/trend", json=body)
    assert resp.status_code == 200
    assert _lines(client)[resp.json()["id"]]["time1"] == body["time1"]


# --- 신호: time1부터 오른쪽으로 끝없이 연장한 직선을 평가 (time1 이전은 평가 안 함) ---

def _df(rows, start="2025-01-01"):
    return pd.DataFrame({
        "open_time": pd.date_range(start, periods=len(rows), freq="D", tz="UTC"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    })


# 가격 100인 평평한 추세선 + 매일 선에 닿는 캔들 -> 평가 구간 밖이면 신호가 안 나는 것을 확인하기 쉽다
TOUCH = (101, 102, 99, 100.5)
CREATED = "2026-10-06T01:02:03+00:00"


def _flat_trend(time1, time2, line_id=11, created_at=CREATED):
    return {"id": line_id, "line_type": "trend", "time1": time1, "price1": 100.0, "time2": time2,
            "price2": 100.0, "created_at": created_at}


def _signal_days(rows, line):
    sigs = manual_lines.compute_manual_line_signals(_df(rows), [line])
    return [i for i, lst in sigs.items() if lst], sigs


def test_trend_signals_start_on_time1_and_continue_to_the_right_without_end():
    rows = [TOUCH] * 7                                  # idx 0..6 = 01-01 .. 01-07, 전부 선에 닿음
    days, _ = _signal_days(rows, _flat_trend("2025-01-03", "2025-01-05"))
    # time1 당일(idx2)부터, time2(idx4)를 지나 마지막 캔들(idx6)까지 계속 평가한다
    assert days == [2, 3, 4, 5, 6]


def test_no_signal_before_time1():
    rows = [TOUCH] * 7
    days, _ = _signal_days(rows, _flat_trend("2025-01-03", "2025-01-05"))
    assert 0 not in days and 1 not in days              # time1 전날(01-02)과 그 이전은 평가 안 함
    assert 5 in days and 6 in days                      # time2 다음날부터도 평가한다(예전 선분 규칙과 다른 점)


def test_single_day_trend_line_is_a_flat_ray_from_that_day():
    # 같은 날 두 점: 백엔드 _trend_line_price가 price1 고정 -> 그 날부터 오른쪽으로 price1 높이의 수평 연장선
    rows = [TOUCH] * 5
    days, _ = _signal_days(rows, _flat_trend("2025-01-03", "2025-01-03"))
    assert days == [2, 3, 4]


def test_reversed_stored_row_starts_at_the_earlier_point():
    # 옛 행처럼 time1 > time2로 저장돼도 이른 쪽 점(01-03)부터 시작해 같은 연장선이어야 한다
    rows = [TOUCH] * 7
    days, _ = _signal_days(rows, _flat_trend("2025-01-05", "2025-01-03"))
    assert days == [2, 3, 4, 5, 6]


def test_price_beyond_the_second_point_is_linearly_extrapolated():
    # (01-01,100) -> (01-09,140): 하루 +5 -> 두 번째 점(01-09) 이후인 01-11(idx 10)의 선 가격은 150
    line = {"id": 2, "line_type": "trend", "time1": "2025-01-01", "price1": 100.0, "time2": "2025-01-09",
            "price2": 140.0, "created_at": CREATED}
    rows = [(50, 51, 49, 50)] * 10 + [(151, 152, 149.5, 151)]   # idx 10: 선 150, 시가 151 > 150 -> 지지
    days, sigs = _signal_days(rows, line)
    assert days == [10] and sigs[10][0].direction == "long" and "지지 시험" in sigs[10][0].text
    rows = rows[:10] + [(149, 150.5, 148, 148.5)]               # 시가 149 < 150 -> 저항
    days, sigs = _signal_days(rows, line)
    assert days == [10] and sigs[10][0].direction == "short" and "저항 시험" in sigs[10][0].text


def test_descending_ray_that_reaches_zero_stops_producing_signals():
    # 가파르게 내려가는 선은 연장하다 0 이하가 되는 날부터 평가하지 않는다 (엉뚱한 신호 방지)
    line = {"id": 3, "line_type": "trend", "time1": "2025-01-01", "price1": 20.0, "time2": "2025-01-03",
            "price2": 10.0, "created_at": CREATED}              # 하루 -5: 20, 15, 10, 5, 0(01-05), -5 ...
    near_line = [(lvl + 0.5, lvl + 1, lvl - 1, lvl + 0.2) for lvl in (20, 15, 10, 5)]   # idx 0..3: 선에 닿음
    touch_zero = [(0.5, 1, 0, 0.5)] * 4                          # idx 4..7: 저가 0 - 선 가격 0/음수에 "닿는" 캔들
    days, _ = _signal_days(near_line + touch_zero, line)
    assert days == [0, 1, 2, 3]                                  # idx 4(선 가격 0)부터는 평가하지 않는다


def test_price_inside_the_segment_is_still_linearly_interpolated():
    # (01-01,100) -> (01-09,140): 01-05 선 가격 120. 시가 121(선 위)이면 지지 시험(long)
    line = {"id": 2, "line_type": "trend", "time1": "2025-01-01", "price1": 100.0, "time2": "2025-01-09",
            "price2": 140.0, "created_at": CREATED}
    rows = [(50, 51, 49, 50)] * 4 + [(121, 122, 119.5, 121)]
    days, sigs = _signal_days(rows, line)
    assert days == [4] and sigs[4][0].direction == "long" and "지지 시험" in sigs[4][0].text


def test_trend_signals_carry_ref_id_and_ref_created_at_but_horizontal_signals_do_not():
    rows = [TOUCH] * 3
    trend = _flat_trend("2025-01-01", "2025-01-03", line_id=42)
    hline = {"id": 7, "line_type": "horizontal", "price1": 100.0, "time1": None, "time2": None,
             "price2": None, "created_at": CREATED}
    sigs = manual_lines.compute_manual_line_signals(_df(rows), [trend, hline])
    for i in range(3):
        by_text = {s.text.split(" 근접")[0].split(" ")[0]: s for s in sigs[i]}
        assert by_text["추세선"].ref_id == 42 and by_text["추세선"].ref_created_at == CREATED
        assert by_text["수평선"].ref_id is None and by_text["수평선"].ref_created_at is None
        assert by_text["추세선"].source is None and by_text["추세선"].tier is None  # 존과 달리 source는 안 채움


def test_horizontal_signals_ignore_the_trend_window():
    # 수평선은 구간 제한이 없다 - 추세선 구간 밖 캔들에도 그대로 신호가 난다
    rows = [TOUCH] * 7
    hline = {"id": 7, "line_type": "horizontal", "price1": 100.0, "time1": None, "time2": None,
             "price2": None, "created_at": CREATED}
    days, _ = _signal_days(rows, hline)
    assert days == list(range(7))


# --- 대시보드: 수정 후 신호가 새 연장선 기준으로 바뀐다 ---

def test_dashboard_trend_signals_follow_the_updated_line(client):
    trend_id = client.post("/api/lines/trend", json=TREND_A).json()["id"]

    def trend_signals():
        data = client.get("/api/dashboard").json()
        return [
            (date, s) for date, v in data["signals"].items() for s in v if s["text"].startswith("추세선")
        ]

    first = trend_signals()
    created = _lines(client)[trend_id]["created_at"]
    assert first, "2023년 상승 구간 추세선이면 신호가 있어야 함"
    assert all(d >= "2023-01-01" for d, _ in first)                                 # time1 이전에는 신호 없음
    assert any(d > "2023-12-31" for d, _ in first), "time2 이후(오른쪽 연장선)에도 신호가 나야 함"
    assert all(s["ref_id"] == trend_id and s["ref_created_at"] == created for _, s in first)

    assert client.put(f"/api/lines/trend/{trend_id}", json=TREND_B).status_code == 200

    second = trend_signals()
    new_created = _lines(client)[trend_id]["created_at"]
    assert second, "2024년 추세선 모양에도 신호가 있어야 함"
    assert all(d >= "2024-03-01" for d, _ in second)
    assert all(s["ref_id"] == trend_id and s["ref_created_at"] == new_created != created for _, s in second)
