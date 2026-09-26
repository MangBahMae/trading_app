"""신호 스캐너(대시보드) API 요청/응답 스키마."""
from typing import Literal

from pydantic import BaseModel


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ema9: float | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    rsi: float | None


class DateRange(BaseModel):
    min: str
    max: str


class SignalItem(BaseModel):
    text: str
    direction: Literal["long", "short", "reference"]


class DivergenceMarker(BaseModel):
    type: str
    label: str
    prev_date: str
    prev_price: float
    prev_rsi: float
    structure_date: str
    price: float
    rsi: float
    confirmed_date: str


class ManualLine(BaseModel):
    id: int
    symbol: str
    interval: str
    line_type: Literal["horizontal", "trend"]
    time1: str | None
    price1: float
    time2: str | None
    price2: float | None
    created_at: str
    label: str


class DashboardResponse(BaseModel):
    candles: list[Candle]
    date_range: DateRange
    signals: dict[str, list[SignalItem]]
    divergence_markers: list[DivergenceMarker]
    manual_lines: list[ManualLine]


class HorizontalLineRequest(BaseModel):
    price: float


class TrendLineRequest(BaseModel):
    time1: str
    price1: float
    time2: str
    price2: float


class LineIdResponse(BaseModel):
    id: int
