"""포지션 사이징 API 요청/응답 스키마."""
from typing import Literal

from pydantic import BaseModel, Field


class PriceWeightItem(BaseModel):
    price: float = Field(ge=0)
    weight: float = Field(ge=0, le=100)


class CalculateRequest(BaseModel):
    balance: float = Field(ge=0)
    risk_pct: float = Field(ge=0)
    direction: Literal["long", "short"]
    entries: list[PriceWeightItem]
    stop_loss: float = Field(ge=0)
    take_profits: list[PriceWeightItem] = []
    margin: float | None = None


class TpResult(BaseModel):
    price: float
    weight_pct: float
    r_multiple: float


class CalculateResponse(BaseModel):
    avg_entry: float
    stop_pct: float
    risk_amount: float
    position_size: float | None
    btc_quantity: float | None
    leverage: float | None
    tp_results: list[TpResult]
    weighted_avg_r: float | None
    warnings: list[str]
    warning_messages: list[str]


class ExchangeRateResponse(BaseModel):
    rate: float
    source: Literal["live", "fallback"]
