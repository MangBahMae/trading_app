"""시장 상태(차트 음영 전용) API 응답 스키마."""
from typing import Literal

from pydantic import BaseModel


class MarketStateParams(BaseModel):
    n: int
    k: int


class MarketStateCandle(BaseModel):
    date: str
    state: Literal["상승", "하락", "횡보"] | None  # None = 데이터 부족(EMA50 없음)
    reason: Literal["A", "BC", "없음"] | None
    a: bool
    b: bool
    c: bool
    gap_now: float | None       # |EMA9-EMA50| 오늘
    gap_prev: float | None      # |EMA9-EMA50| N봉 전 (구할 수 없으면 None)
    cross_count: int | None     # 최근 N봉 종가-EMA9 교차 횟수 (구할 수 없으면 None)


class MarketStateBlock(BaseModel):
    start: str
    end: str
    length: int
    reason: Literal["A", "BC"]


class MarketStateResponse(BaseModel):
    params: MarketStateParams
    counts: dict[str, int]
    candles: list[MarketStateCandle]
    blocks: list[MarketStateBlock]
