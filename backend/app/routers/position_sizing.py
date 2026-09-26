"""포지션 사이징 계산기 API 라우터."""
from fastapi import APIRouter

from app.schemas.position_sizing import (
    CalculateRequest,
    CalculateResponse,
    ExchangeRateResponse,
)
from app.services import position_sizing as svc

router = APIRouter(prefix="/api/position-sizing", tags=["position-sizing"])


@router.post("/calculate", response_model=CalculateResponse)
def calculate(payload: CalculateRequest) -> CalculateResponse:
    entries = [(item.price, item.weight) for item in payload.entries]
    take_profits = [(item.price, item.weight) for item in payload.take_profits]

    result = svc.calculate_position(
        balance=payload.balance,
        risk_pct=payload.risk_pct,
        direction=payload.direction,
        entries=entries,
        stop_loss=payload.stop_loss,
        take_profits=take_profits,
        margin=payload.margin if payload.margin else None,
    )

    warning_messages = [svc.WARNING_MESSAGES_KR.get(w, w) for w in result["warnings"]]

    return CalculateResponse(
        avg_entry=result["avg_entry"],
        stop_pct=result["stop_pct"],
        risk_amount=result["risk_amount"],
        position_size=result["position_size"],
        btc_quantity=result["btc_quantity"],
        leverage=result["leverage"],
        tp_results=result["tp_results"],
        weighted_avg_r=result["weighted_avg_r"],
        warnings=result["warnings"],
        warning_messages=warning_messages,
    )


@router.get("/exchange-rate", response_model=ExchangeRateResponse)
def exchange_rate(refresh: bool = False) -> ExchangeRateResponse:
    rate = svc.fetch_usdt_krw_rate(force_refresh=refresh)
    if rate is not None:
        return ExchangeRateResponse(rate=rate, source="live")
    return ExchangeRateResponse(rate=svc.EXCHANGE_RATE_KRW_PER_USDT, source="fallback")
