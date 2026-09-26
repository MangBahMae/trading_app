"""POST /api/position-sizing/calculate 검증.

scripts/position_sizing.py의 if __name__ == "__main__" 테스트케이스 1/2와
동일한 입력을 실제 API 엔드포인트에 보내서 같은 결과가 나오는지 확인한다.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_case_1_no_tp():
    resp = client.post(
        "/api/position-sizing/calculate",
        json={
            "balance": 500_000,
            "risk_pct": 1.0,
            "direction": "long",
            "entries": [{"price": 118_000, "weight": 100}],
            "stop_loss": 113_800,
            "take_profits": [],
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["avg_entry"] == 118_000
    assert data["risk_amount"] == 5_000
    assert abs(data["stop_pct"] * 100 - 3.5593) < 0.01
    # 스펙의 "약 140,449"는 stop_pct를 3.56%로 반올림한 뒤 역산한 근사치 -
    # 실제 계산은 반올림 없이 풀정밀도로 하므로 140,476.19가 정확한 값.
    assert abs(data["position_size"] - 140_476.19) < 1
    assert data["warnings"] == []


def test_case_2_two_tps():
    resp = client.post(
        "/api/position-sizing/calculate",
        json={
            "balance": 500_000,
            "risk_pct": 1.0,
            "direction": "long",
            "entries": [{"price": 118_000, "weight": 100}],
            "stop_loss": 113_800,
            "take_profits": [
                {"price": 122_000, "weight": 50},
                {"price": 126_000, "weight": 50},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert abs(data["tp_results"][0]["r_multiple"] - 0.9524) < 0.01
    assert abs(data["tp_results"][1]["r_multiple"] - 1.9048) < 0.01
    assert abs(data["weighted_avg_r"] - 1.4286) < 0.01


def test_warning_messages_are_korean():
    # 진입 비중 합이 100이 아니고, 리스크%가 기본값(1%)이 아닌 경우 경고 2개 발생
    resp = client.post(
        "/api/position-sizing/calculate",
        json={
            "balance": 500_000,
            "risk_pct": 2.0,
            "direction": "long",
            "entries": [{"price": 118_000, "weight": 90}],
            "stop_loss": 113_800,
            "take_profits": [],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "entries_sum_invalid" in data["warnings"]
    assert "risk_pct_deviation" in data["warnings"]
    assert "진입 비중 합이 100%가 아닙니다" in data["warning_messages"]
    assert "기본값(1%)에서 벗어났습니다" in data["warning_messages"]


def test_exchange_rate_endpoint_returns_valid_shape():
    resp = client.get("/api/position-sizing/exchange-rate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] in ("live", "fallback")
    assert data["rate"] > 0
