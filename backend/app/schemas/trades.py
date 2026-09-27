"""매매 계획/기록(기능 2, Phase 2-1) API 요청/응답 스키마."""
from typing import Literal

from pydantic import BaseModel, Field


class PriceWeight(BaseModel):
    # price는 ge=0(0 허용)으로 느슨하게 받는다 - gt=0으로 막으면 아직 입력을
    # 안 채운 기본값(0)만으로도 draft 저장/타이핑 도중 매 요청이 422로 튕겨서
    # 프론트가 그 에러(문자열이 아니라 pydantic 에러 객체 배열)를 렌더링하려다
    # 크래시했다(발견한 버그). 0/음수 등 실제로 유효하지 않은 가격은 저장소
    # 계층의 validate_plan()/validate_close()가 사람이 읽을 수 있는 코드로
    # 걸러낸다 - pydantic은 "숫자 타입인지"만 보고, "유효한 가격인지"는 거기서 본다.
    price: float = Field(ge=0)
    weight: float = Field(ge=0, le=100)


class ExitItem(BaseModel):
    price: float = Field(ge=0)
    weight: float = Field(ge=0, le=100)
    realized_pnl: float


class TradePlanRequest(BaseModel):
    """진입 전 계획 저장 요청 (POST /api/trades, PATCH /api/trades/{id})."""
    direction: Literal["long", "short"]
    entry_rationale: str | None = None
    signal_tags: list[str] = []
    invalidation_note: str | None = None
    invalidation_price: float | None = None
    stop_loss: float | None = None
    entries: list[PriceWeight] = []
    take_profits: list[PriceWeight] = []
    margin: float | None = None
    leverage: float | None = None


class TradeCloseRequest(BaseModel):
    """청산 후 기록 요청 (PATCH /api/trades/{id}/close)."""
    exits: list[ExitItem]
    exit_reason: Literal["tp", "sl", "invalidation", "manual"]
    exit_memo: str | None = None


class TradeResponse(BaseModel):
    id: int
    status: Literal["draft", "open", "closed"]
    direction: Literal["long", "short"]

    entry_rationale: str | None
    signal_tags: list[str]
    invalidation_note: str | None
    invalidation_price: float | None
    stop_loss: float | None
    entries: list[PriceWeight]
    take_profits: list[PriceWeight]
    margin: float | None
    leverage: float | None
    avg_entry: float | None
    quantity: float | None
    risk_amount: float | None
    planned_at: str

    exits: list[ExitItem] | None
    exit_reason: str | None
    exit_memo: str | None
    realized_pnl_total: float | None
    realized_r: float | None
    closed_at: str | None


class ValidationErrorResponse(BaseModel):
    errors: list[str]
