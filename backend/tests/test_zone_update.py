"""
존 꼭지점 드래그 수정용 PUT /api/lines/zone/{line_id} 검증.

- 수정 성공: 값 갱신, id 유지, created_at은 "수정한 시각"으로 갱신
- 존이 아닌 행/없는 id는 404, 잘못된 값은 422(POST와 같은 검증)
- 수정 후 /api/dashboard의 존 신호가 새 모양 기준으로 바뀌고 ref_created_at도 갱신된다

실데이터 manual_lines.db는 건드리지 않는다 - lines_store.DB_PATH를 임시 파일로 바꿔서 쓴다.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app  # app.services.dashboard가 services 경로를 sys.path에 넣는다

import lines_store  # noqa: E402  (dashboard.py가 쓰는 것과 같은 bare 모듈 객체)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


ZONE = {"time1": "2023-01-01", "price1": 30000.0, "time2": "2023-06-01", "price2": 20000.0}
NEW_SHAPE = {"time1": "2024-03-01", "price1": 70000.0, "time2": "2024-12-31", "price2": 60000.0}


def _lines(client):
    return {ln["id"]: ln for ln in client.get("/api/dashboard").json()["manual_lines"]}


def test_update_zone_changes_values_keeps_id_and_refreshes_created_at(client):
    zone_id = client.post("/api/lines/zone", json=ZONE).json()["id"]
    before = _lines(client)[zone_id]

    resp = client.put(f"/api/lines/zone/{zone_id}", json=NEW_SHAPE)
    assert resp.status_code == 200
    assert resp.json() == {"id": zone_id}

    lines = _lines(client)
    assert list(lines) == [zone_id]  # 새 행이 생기지 않고 id 유지
    after = lines[zone_id]
    assert (after["time1"], after["time2"], after["price1"], after["price2"]) == (
        "2024-03-01", "2024-12-31", 70000.0, 60000.0)
    assert after["line_type"] == "zone"
    assert after["created_at"] > before["created_at"]  # ISO 문자열이라 사전순 = 시간순
    assert after["label"] == "▭ 존 60,000~70,000 (2024-03-01 → 2024-12-31)"


def test_update_zone_on_non_zone_row_returns_404_and_changes_nothing(client):
    hline_id = client.post("/api/lines/horizontal", json={"price": 28000.0}).json()["id"]
    trend_id = client.post(
        "/api/lines/trend",
        json={"time1": "2026-01-01", "price1": 100.0, "time2": "2026-02-01", "price2": 120.0},
    ).json()["id"]
    before = _lines(client)

    for line_id in (hline_id, trend_id):
        assert client.put(f"/api/lines/zone/{line_id}", json=NEW_SHAPE).status_code == 404
    assert _lines(client) == before


def test_update_zone_on_missing_id_returns_404(client):
    assert client.put("/api/lines/zone/99999", json=NEW_SHAPE).status_code == 404


@pytest.mark.parametrize("patch", [
    {"price1": 80000.0, "price2": 90000.0},        # 상단 < 하단
    {"price1": 85000.0, "price2": 85000.0},        # 상단 == 하단
    {"price1": 0.0},                               # 가격 0
    {"price2": -1.0},                              # 가격 음수
    {"time1": "2026-02-01", "time2": "2026-01-01"},  # 시작 > 끝
    {"time1": "2026-01-01", "time2": "2026-01-01"},  # 시작 == 끝
    {"time1": "2026/01/01"},                       # 날짜 형식
    {"time2": "not-a-date"},
    {"time1": "20260101"},
])
def test_update_zone_rejects_invalid_values_and_keeps_original(client, patch):
    zone_id = client.post("/api/lines/zone", json=ZONE).json()["id"]
    before = _lines(client)[zone_id]

    resp = client.put(f"/api/lines/zone/{zone_id}", json={**NEW_SHAPE, **patch})
    assert resp.status_code == 422
    assert _lines(client)[zone_id] == before  # 값도 created_at도 그대로


def test_update_zone_rejects_missing_fields(client):
    zone_id = client.post("/api/lines/zone", json=ZONE).json()["id"]
    assert client.put(f"/api/lines/zone/{zone_id}", json={"price1": 2.0, "price2": 1.0}).status_code == 422


def test_dashboard_zone_signals_follow_the_updated_shape(client):
    zone_id = client.post("/api/lines/zone", json={
        "time1": "2022-03-01", "price1": 45000.0, "time2": "2025-01-01", "price2": 15000.0}).json()["id"]
    first = client.get("/api/dashboard").json()
    old_signals = [(d, s) for d, v in first["signals"].items() for s in v if s["source"] == "zone"]
    assert old_signals and all(s["ref_id"] == zone_id for _, s in old_signals)
    old_created = _lines(client)[zone_id]["created_at"]
    assert all(s["ref_created_at"] == old_created for _, s in old_signals)
    assert all(s["text"].startswith("존 15,000~45,000 ") for _, s in old_signals)

    assert client.put(f"/api/lines/zone/{zone_id}", json=NEW_SHAPE).status_code == 200

    second = client.get("/api/dashboard").json()
    new_created = _lines(client)[zone_id]["created_at"]
    new_signals = [(d, s) for d, v in second["signals"].items() for s in v if s["source"] == "zone"]
    assert new_signals, "새 모양(2024-03~12, 6~7만)에는 신호가 있어야 함"
    for date, s in new_signals:
        assert s["ref_id"] == zone_id                      # id 유지
        assert s["ref_created_at"] == new_created != old_created  # 수정 시각으로 갱신
        assert s["text"].startswith("존 60,000~70,000 ")   # 새 가격 범위
        assert "2024-03-01" <= date <= "2024-12-31"        # 새 유효 기간
    assert {d for d, _ in new_signals} != {d for d, _ in old_signals}

    # 기존(존이 아닌) 신호는 수정과 무관하게 그대로
    def non_zone(data):
        return {d: [s for s in v if s["source"] != "zone"] for d, v in data["signals"].items() if any(
            s["source"] != "zone" for s in v)}
    assert non_zone(first) == non_zone(second)
