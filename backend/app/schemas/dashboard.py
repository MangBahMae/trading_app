"""신호 스캐너(대시보드) API 요청/응답 스키마."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    source: Literal["zone", "line", "ema"] | None = None
    tier: Literal["strong", "mid", "weak"] | None = None
    evidence: list[str] = []
    ref_id: int | None = None            # 신호를 만든 도형(존)의 lines.id
    ref_created_at: str | None = None    # 그 도형의 생성일(ISO) - 백테스트에서 사후 신호를 거를 때 사용


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
    line_type: Literal["horizontal", "trend", "zone"]
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
    """추세선(두 점 사이 선분). POST/PUT 공통 검증: 가격 양수, 날짜 형식(YYYY-MM-DD), 시작 <= 끝.
    같은 날(시작 == 끝)은 허용한다(그 하루의 수평 선분으로 취급, 기존 동작과 같다). 프론트가 두 점을
    시간순으로 정규화해서 보내며, 서버는 정규화하지 않고 틀린 값을 거부한다."""
    time1: str
    price1: float = Field(gt=0)
    time2: str
    price2: float = Field(gt=0)

    @model_validator(mode="after")
    def _check_trend(self):
        try:
            start, end = date.fromisoformat(self.time1), date.fromisoformat(self.time2)
        except ValueError as e:
            raise ValueError("time1/time2는 YYYY-MM-DD 형식이어야 함") from e
        if len(self.time1) != 10 or len(self.time2) != 10:
            raise ValueError("time1/time2는 YYYY-MM-DD 형식이어야 함")
        if start > end:
            raise ValueError("시작 시간(time1)은 끝 시간(time2)보다 늦을 수 없음")
        return self


class ZoneRequest(BaseModel):
    """존(가격 구간 직사각형). price1=상단, price2=하단, time1=시작, time2=끝 (YYYY-MM-DD).
    프론트가 두 모서리를 정규화해서 보내며, 서버는 정규화하지 않고 잘못된 값을 거부한다."""
    time1: str
    price1: float = Field(gt=0)
    time2: str
    price2: float = Field(gt=0)

    @model_validator(mode="after")
    def _check_zone(self):
        try:
            start, end = date.fromisoformat(self.time1), date.fromisoformat(self.time2)
        except ValueError as e:
            raise ValueError("time1/time2는 YYYY-MM-DD 형식이어야 함") from e
        if len(self.time1) != 10 or len(self.time2) != 10:
            raise ValueError("time1/time2는 YYYY-MM-DD 형식이어야 함")
        if not self.price1 > self.price2:
            raise ValueError("상단 가격(price1)은 하단 가격(price2)보다 커야 함")
        if not start < end:
            raise ValueError("시작 시간(time1)은 끝 시간(time2)보다 앞이어야 함")
        return self


class LineIdResponse(BaseModel):
    id: int
