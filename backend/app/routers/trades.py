"""매매 계획/기록(기능 2, Phase 2-1) API 라우터."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.schemas.trades import TradeCloseRequest, TradePlanRequest, TradeResponse
from app.services import trades as svc

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("/signal-tags", response_model=list[str])
def get_signal_tags() -> list[str]:
    return svc.SIGNAL_TAGS


@router.get("", response_model=list[TradeResponse])
def list_trades(status: Literal["draft", "open", "closed"] | None = Query(None)) -> list[TradeResponse]:
    return [TradeResponse(**t) for t in svc.list_trades(status)]


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(trade_id: int) -> TradeResponse:
    try:
        return TradeResponse(**svc.get_trade(trade_id))
    except svc.ValidationError as e:
        raise HTTPException(status_code=404, detail=e.errors) from e


@router.post("", response_model=TradeResponse)
def create_trade(payload: TradePlanRequest, draft: bool = Query(False)) -> TradeResponse:
    try:
        result = svc.create_trade(payload.model_dump(), draft=draft)
        return TradeResponse(**result)
    except svc.ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors) from e


@router.patch("/{trade_id}", response_model=TradeResponse)
def update_trade(trade_id: int, payload: TradePlanRequest, draft: bool = Query(False)) -> TradeResponse:
    try:
        # exclude_unset - 프론트가 안 보낸 필드는 기존 값을 그대로 유지해야 하므로,
        # payload에 아예 없는 키로 취급되게 한다(트레이드 서비스의 dict.get(key, 기존값)
        # 폴백이 정상 동작하려면 필수 - None으로 채워서 보내면 기존 값을 지워버림).
        result = svc.update_trade(trade_id, payload.model_dump(exclude_unset=True), draft=draft)
        return TradeResponse(**result)
    except svc.ValidationError as e:
        status_code = 404 if "trade_not_found" in e.errors else 400
        raise HTTPException(status_code=status_code, detail=e.errors) from e


@router.patch("/{trade_id}/close", response_model=TradeResponse)
def close_trade(trade_id: int, payload: TradeCloseRequest) -> TradeResponse:
    try:
        result = svc.close_trade(
            trade_id,
            [e.model_dump() for e in payload.exits],
            payload.exit_reason,
            payload.exit_memo,
        )
        return TradeResponse(**result)
    except svc.ValidationError as e:
        status_code = 404 if "trade_not_found" in e.errors else 400
        raise HTTPException(status_code=status_code, detail=e.errors) from e


@router.delete("/{trade_id}")
def delete_trade(trade_id: int) -> dict:
    svc.delete_trade(trade_id)
    return {"ok": True}
