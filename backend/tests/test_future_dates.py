"""
마지막 캔들 오른쪽(미래) 날짜의 도형이 백엔드에서 문제없이 저장/조회/평가되는지 검증한다.
백엔드 코드는 바꾸지 않았다 - 날짜 검증은 형식(YYYY-MM-DD)과 시작<끝만 하고 상한이 없다.

- POST/PUT/조회: 미래 날짜 존, 추세선, 수평선이 저장되고 /api/dashboard에 내려간다
- 존 신호: 미래 time2의 존은 새 캔들이 붙을 때마다 time2까지 이어서 평가된다(미래 캔들은 평가 안 함)
- 추세선: 마지막 점 이후(외삽 구간)에도 신호가 난다
"""
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app  # app.services.dashboard가 services 경로를 sys.path에 넣는다

import lines_store  # noqa: E402  (dashboard.py가 쓰는 것과 같은 bare 모듈 객체)

SERVICES_DIR = Path(__file__).resolve().parents[1] / "app" / "services"
sys.path.insert(0, str(SERVICES_DIR))

import manual_lines  # noqa: E402
import zone_signals  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


def _lines(client):
    return {ln["id"]: ln for ln in client.get("/api/dashboard").json()["manual_lines"]}


# --- API: 미래 날짜 저장/수정/조회 ---

def test_future_zone_post_put_and_dashboard(client):
    zone_id = client.post("/api/lines/zone", json={
        "time1": "2099-01-01", "price1": 90000.0, "time2": "2099-06-01", "price2": 80000.0}).json()["id"]
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    zone = {ln["id"]: ln for ln in resp.json()["manual_lines"]}[zone_id]
    assert (zone["time1"], zone["time2"], zone["line_type"]) == ("2099-01-01", "2099-06-01", "zone")
    assert zone["label"] == "▭ 존 80,000~90,000 (2099-01-01 → 2099-06-01)"
    # 캔들이 없는 미래뿐이라 존 신호는 없다
    assert all(s["source"] != "zone" for v in resp.json()["signals"].values() for s in v)

    # 존을 미래 구간에서 미래 구간으로 수정
    assert client.put(f"/api/lines/zone/{zone_id}", json={
        "time1": "2100-03-01", "price1": 95000.0, "time2": "2100-12-31", "price2": 85000.0}).status_code == 200
    after = _lines(client)[zone_id]
    assert (after["time1"], after["time2"], after["price1"], after["price2"]) == (
        "2100-03-01", "2100-12-31", 95000.0, 85000.0)


def test_zone_may_start_in_the_past_and_end_in_the_future(client):
    zone_id = client.post("/api/lines/zone", json={
        "time1": "2026-01-01", "price1": 90000.0, "time2": "2099-12-31", "price2": 20000.0}).json()["id"]
    data = client.get("/api/dashboard").json()
    zone_sigs = [s for v in data["signals"].values() for s in v if s["source"] == "zone"]
    assert zone_sigs and all(s["ref_id"] == zone_id for s in zone_sigs)
    last_candle = data["date_range"]["max"]
    dates = [d for d, v in data["signals"].items() if any(s["source"] == "zone" for s in v)]
    assert max(dates) <= last_candle  # 미래 날짜에는 캔들이 없으므로 신호도 없다


def test_future_trend_and_horizontal_lines_are_saved(client):
    trend_id = client.post("/api/lines/trend", json={
        "time1": "2026-10-01", "price1": 80000.0, "time2": "2027-03-01", "price2": 120000.0}).json()["id"]
    hline_id = client.post("/api/lines/horizontal", json={"price": 123456.0}).json()["id"]
    lines = _lines(client)
    assert lines[trend_id]["time2"] == "2027-03-01" and lines[trend_id]["line_type"] == "trend"
    assert lines[hline_id]["price1"] == 123456.0


def test_date_validation_is_still_enforced_for_zones(client):
    assert client.post("/api/lines/zone", json={
        "time1": "2099/01/01", "price1": 2.0, "time2": "2099-06-01", "price2": 1.0}).status_code == 422
    assert client.post("/api/lines/zone", json={
        "time1": "2099-06-01", "price1": 2.0, "time2": "2099-01-01", "price2": 1.0}).status_code == 422


# --- 존 신호: 미래 time2는 새 캔들에서도 이어진다 ---

T, B = 110.0, 100.0


def _df(rows, start="2025-01-01"):
    return pd.DataFrame({
        "open_time": pd.date_range(start, periods=len(rows), freq="D", tz="UTC"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    })


def _zone(time2):
    return {"id": 9, "line_type": "zone", "time1": "2025-01-01", "price1": T, "time2": time2,
            "price2": B, "created_at": "2026-10-06T00:00:00+00:00"}


def _sig_days(df, zone):
    sigs = zone_signals.compute_zone_signals(df, [zone])
    return {df["open_time"].iloc[i].strftime("%Y-%m-%d"): [s.text for s in lst] for i, lst in sigs.items() if lst}


def test_zone_with_future_time2_keeps_signalling_on_newly_added_candles():
    above = (120, 121, 119, 120)
    reaction = (115, 116, 108, 112)   # 지지 반응(직전 종가가 존 위)
    rows = [above, reaction]          # 2025-01-01, 2025-01-02 (마지막 캔들)
    zone = _zone(time2="2025-03-01")  # 마지막 캔들(01-02)보다 한참 뒤

    first = _sig_days(_df(rows), zone)
    assert list(first) == ["2025-01-02"]

    # 새 일봉이 마감되어 붙는다: 다시 존 위 마감 -> 또 지지 반응
    rows2 = rows + [above, reaction]  # 2025-01-03, 2025-01-04
    second = _sig_days(_df(rows2), zone)
    assert list(second) == ["2025-01-02", "2025-01-04"]
    assert second["2025-01-02"] == first["2025-01-02"]   # 이미 있던 날의 신호는 그대로
    assert second["2025-01-04"] == ["존 100~110 지지 반응 (매수 후보)"]


def test_zone_stops_after_its_time2_even_when_more_candles_arrive():
    above = (120, 121, 119, 120)
    reaction = (115, 116, 108, 112)
    rows = [above, reaction, above, reaction, above, reaction]  # 01-01 ~ 01-06
    zone = _zone(time2="2025-01-04")
    assert list(_sig_days(_df(rows), zone)) == ["2025-01-02", "2025-01-04"]  # 01-06 반응은 time2 이후라 평가 안 함


# --- 추세선: 두 점 사이 선분 구간(time1 <= 날짜 <= time2)만 평가한다 ---

def test_trend_line_has_no_signals_after_its_last_point():
    """3단계 신호 정렬로 바뀐 규칙: 예전엔 마지막 점 이후(외삽 구간)에도 신호가 났지만, 이제는 화면의
    선분과 같은 구간만 평가한다. 선분 밖(미래 캔들 포함)에는 신호가 나지 않는다."""
    far = (50, 51, 49, 50)
    # 점: (01-01,100) (01-03,110) -> 하루 +5. 01-07 = 130, 01-08 = 135 (둘 다 마지막 점 이후이고 선 근처 캔들)
    trend = {"id": 3, "line_type": "trend", "time1": "2025-01-01", "price1": 100.0,
             "time2": "2025-01-03", "price2": 110.0, "created_at": "2026-10-06T00:00:00+00:00"}
    rows = [far] * 6 + [(131, 132, 129, 131), (134, 136, 133, 134)]   # idx 6 = 01-07, idx 7 = 01-08
    sigs = manual_lines.compute_manual_line_signals(_df(rows), [trend])
    assert [i for i, lst in sigs.items() if lst] == []
