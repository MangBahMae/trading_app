"""시장 상태(상승/하락/횡보) API 라우터 - 신호가 아니라 차트 배경 음영 전용."""
from fastapi import APIRouter, HTTPException, Query

from app.schemas.market_state import MarketStateResponse
from app.services import dashboard as svc

router = APIRouter(prefix="/api", tags=["market-state"])


@router.get("/market-state", response_model=MarketStateResponse)
def get_market_state(n: int = Query(10, ge=1, le=500), k: int = Query(4, ge=0, le=500)) -> MarketStateResponse:
    try:
        return MarketStateResponse(**svc.get_market_state(n, k))
    except ValueError as e:  # k > n 등 교차 검증
        raise HTTPException(status_code=422, detail=str(e)) from e
