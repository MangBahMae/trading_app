"""매매 계획/기록(기능 2, Phase 2-1) API 검증.

data/trades.db는 실제 사용자 데이터가 쌓일 파일이라, 여기서 만든 테스트
레코드는 전부 끝나면 삭제한다(테스트 자체 id를 추적해 정리).
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_created_ids: list[int] = []


def _create(payload: dict, draft: bool = False) -> dict:
    resp = client.post("/api/trades", json=payload, params={"draft": draft})
    if resp.status_code == 200:
        _created_ids.append(resp.json()["id"])
    return resp


def teardown_module(module):
    for trade_id in _created_ids:
        client.delete(f"/api/trades/{trade_id}")


LONG_PLAN = {
    "direction": "long",
    "entry_rationale": "EMA50 지지 확인",
    "signal_tags": ["EMA50/200 터치"],
    "invalidation_note": "EMA50 종가 이탈 시 근거 소멸",
    "invalidation_price": 113000,
    "stop_loss": 113800,
    "entries": [{"price": 118000, "weight": 100}],
    "take_profits": [{"price": 122000, "weight": 100}],
    "margin": 1000,
    "leverage": 10,
}


def test_signal_tags_endpoint_returns_nonempty_list():
    resp = client.get("/api/trades/signal-tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert len(tags) > 0
    assert "재량 진입 (신호 없음)" in tags


def test_create_plan_computes_avg_entry_quantity_and_risk_amount():
    resp = _create(LONG_PLAN)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "open"
    assert data["avg_entry"] == 118_000
    # notional = margin*leverage = 10,000, quantity = 10,000/118,000
    assert abs(data["quantity"] - 10_000 / 118_000) < 1e-9
    # risk_amount = quantity * |avg_entry - stop_loss| = quantity * 4200
    expected_risk = (10_000 / 118_000) * 4200
    assert abs(data["risk_amount"] - expected_risk) < 1e-6


def test_create_plan_rejects_missing_required_fields():
    # entry_rationale, invalidation_note/price, margin/leverage 전부 스펙상 필수
    bad_plan = dict(LONG_PLAN, entry_rationale=None, margin=None, leverage=None)
    resp = _create(bad_plan)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "entry_rationale_required" in detail
    assert "margin_required" in detail
    assert "leverage_required" in detail


def test_create_plan_with_zero_price_entry_returns_friendly_string_code_not_pydantic_object():
    # 회귀 방지: price=0(타이핑 전 기본값)으로 제출하면 예전엔 pydantic
    # Field(gt=0) 위반으로 422 + 에러 객체 배열(문자열 아님)이 내려가서,
    # 프론트가 그걸 문자열처럼 렌더링하려다 크래시했다("Objects are not
    # valid as a React child"). 이제는 스키마가 ge=0으로 통과시키고
    # validate_plan()이 사람이 읽을 수 있는 문자열 코드로 걸러야 한다.
    bad_plan = dict(LONG_PLAN, entries=[{"price": 0, "weight": 100}])
    resp = _create(bad_plan)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert all(isinstance(d, str) for d in detail)
    assert "entries_price_invalid" in detail


def test_create_plan_rejects_invalid_price_order_for_long():
    bad_plan = dict(LONG_PLAN, stop_loss=119_000)  # SL이 진입가보다 위 - 롱에 모순
    resp = _create(bad_plan)
    assert resp.status_code == 400
    assert "invalid_price_order" in resp.json()["detail"]


def test_create_plan_rejects_weight_sum_not_100():
    bad_plan = dict(LONG_PLAN, entries=[{"price": 118_000, "weight": 90}])
    resp = _create(bad_plan)
    assert resp.status_code == 400
    assert "entries_weight_sum_invalid" in resp.json()["detail"]


def test_create_plan_rejects_empty_entries():
    bad_plan = dict(LONG_PLAN, entries=[])
    resp = _create(bad_plan)
    assert resp.status_code == 400
    assert "entries_empty" in resp.json()["detail"]


def test_draft_mode_skips_validation():
    incomplete = {"direction": "long", "entries": [], "take_profits": []}
    resp = _create(incomplete, draft=True)
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


def test_close_trade_computes_realized_r():
    plan_resp = _create(LONG_PLAN)
    trade_id = plan_resp.json()["id"]
    risk_amount = plan_resp.json()["risk_amount"]

    # realized_pnl을 risk_amount의 정확히 2배로 줘서 realized_r == 2.0이 나오는지 확인
    realized_pnl = risk_amount * 2
    close_resp = client.patch(
        f"/api/trades/{trade_id}/close",
        json={
            "exits": [{"price": 122_000, "weight": 100, "realized_pnl": realized_pnl}],
            "exit_reason": "tp",
            "exit_memo": "계획대로 TP 도달",
        },
    )
    assert close_resp.status_code == 200
    data = close_resp.json()
    assert data["status"] == "closed"
    assert abs(data["realized_r"] - 2.0) < 1e-9
    assert abs(data["realized_pnl_total"] - realized_pnl) < 1e-9


def test_close_trade_partial_exits_sum_realized_pnl():
    plan_resp = _create(LONG_PLAN)
    trade_id = plan_resp.json()["id"]
    risk_amount = plan_resp.json()["risk_amount"]

    close_resp = client.patch(
        f"/api/trades/{trade_id}/close",
        json={
            "exits": [
                {"price": 120_000, "weight": 50, "realized_pnl": risk_amount * 0.5},
                {"price": 122_000, "weight": 50, "realized_pnl": risk_amount * 1.5},
            ],
            "exit_reason": "tp",
        },
    )
    assert close_resp.status_code == 200
    data = close_resp.json()
    assert abs(data["realized_r"] - 2.0) < 1e-9  # 0.5R + 1.5R = 2R


def test_close_trade_rejects_exit_weight_sum_not_100():
    plan_resp = _create(LONG_PLAN)
    trade_id = plan_resp.json()["id"]

    close_resp = client.patch(
        f"/api/trades/{trade_id}/close",
        json={"exits": [{"price": 122_000, "weight": 60, "realized_pnl": 100}], "exit_reason": "tp"},
    )
    assert close_resp.status_code == 400
    assert "exits_weight_sum_invalid" in close_resp.json()["detail"]


def test_cannot_close_already_closed_trade():
    plan_resp = _create(LONG_PLAN)
    trade_id = plan_resp.json()["id"]
    client.patch(
        f"/api/trades/{trade_id}/close",
        json={"exits": [{"price": 122_000, "weight": 100, "realized_pnl": 100}], "exit_reason": "tp"},
    )
    second_close = client.patch(
        f"/api/trades/{trade_id}/close",
        json={"exits": [{"price": 122_000, "weight": 100, "realized_pnl": 100}], "exit_reason": "tp"},
    )
    assert second_close.status_code == 400
    assert "trade_already_closed" in second_close.json()["detail"]


def test_list_and_get_and_delete():
    plan_resp = _create(LONG_PLAN)
    trade_id = plan_resp.json()["id"]

    list_resp = client.get("/api/trades", params={"status": "open"})
    assert list_resp.status_code == 200
    assert any(t["id"] == trade_id for t in list_resp.json())

    get_resp = client.get(f"/api/trades/{trade_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == trade_id

    delete_resp = client.delete(f"/api/trades/{trade_id}")
    assert delete_resp.status_code == 200
    _created_ids.remove(trade_id)

    get_after_delete = client.get(f"/api/trades/{trade_id}")
    assert get_after_delete.status_code == 404
