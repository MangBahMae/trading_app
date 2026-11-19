"""CoinCloudX 실험: 완료된 BTC 일봉을 순서대로 읽는 관찰 엔진. 주문·DB·네트워크 없음."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite, log
from statistics import fmean
from typing import Literal, Sequence

Shape = Literal['doji', 'hammer', 'inverted_hammer'] | None
REVERSALS = {'doji', 'hammer', 'inverted_hammer'}


@dataclass(frozen=True)
class Bar:
    day: date                   # UTC 봉 시작 날짜. 완료된 일봉만 입력한다.
    open: float
    high: float
    low: float
    close: float
    volume: float
    shape: Shape = None         # 기존 compute_candle_shape의 결과. 중복 판정 금지.


@dataclass(frozen=True)
class Level:
    key: str
    bottom: float
    top: float                  # 수평선이면 bottom == top
    known_from: date            # 이 버전을 사용해도 되는 첫 봉(UTC 날짜)
    through: date               # 종료 봉(포함). 수정 전 버전은 종료일을 끊는다.


@dataclass(frozen=True)
class Config:
    slope_bars: int             # 인접한 같은 길이 2개 구간: 각 구간의 봉 수
    min_drop_per_bar: float     # 로그수익률 절댓값/봉. 0.01은 약 1%/봉
    min_acceleration: float     # 이전보다 더 내려가는 최소 속도 차이/봉
    context_bars: int           # 급락 감지 봉 포함 이후 관찰하는 봉 수
    volume_bars: int            # 당일 제외, 직전 평균 거래량
    volume_multiple: float
    large_red_body: float       # (시가-종가)/시가
    rebound: float              # 첫 저점 기준가 위로 종가가 반등한 최소 비율
    tolerance: float            # 기준 몸통 종가 주변의 재시험 허용 폭
    max_age: int                # 기준 봉 이후 최대 재시험 대기 일수

    def __post_init__(self) -> None:
        for x in (self.slope_bars, self.volume_bars, self.context_bars, self.max_age):
            if type(x) is not int or x < 1:
                raise ValueError('봉 수는 양의 정수여야 합니다.')
        for x in (self.min_drop_per_bar, self.min_acceleration, self.large_red_body, self.rebound):
            if not isfinite(x) or not 0 < x < 1:
                raise ValueError('속도·몸통·반등 기준은 0~1 사이 양수입니다.')
        if not (0 <= self.tolerance < self.rebound) or not isfinite(self.volume_multiple) or self.volume_multiple <= 0:
            raise ValueError('재시험 허용 폭은 반등 기준보다 작고, 거래량 배수는 양수여야 합니다.')


@dataclass(frozen=True)
class Observation:
    day: date
    previous_speed: float | None
    recent_speed: float | None
    accelerating_down: bool | None
    volume_ratio: float | None
    events: tuple[str, ...]
    anchor_day: date | None
    reaction_levels: tuple[str, ...]
    unrecovered_levels: tuple[str, ...]


def analyze(bars: Sequence[Bar], levels: Sequence[Level], cfg: Config) -> list[Observation]:
    """날짜순·연속 일봉만 허용. 후보는 종가 확정 후 관찰값이지 체결/수익률이 아니다."""
    if len({s.key for s in levels}) != len(levels):
        raise ValueError('도형 버전마다 고유 key가 필요합니다.')
    for s in levels:
        if not all(map(isfinite, (s.bottom, s.top))) or not 0 < s.bottom <= s.top or s.known_from > s.through:
            raise ValueError('지지 가격·유효기간을 확인하세요.')
    out: list[Observation] = []
    anchor: Bar | None = None
    bounced = False
    unshaped_seen = False
    last_fast: int | None = None
    broken: set[str] = set()
    n = cfg.slope_bars
    for i, b in enumerate(bars):
        if i and b.day != bars[i-1].day + timedelta(days=1):
            raise ValueError('중복·역순·누락 일봉은 보간하지 않습니다.')
        if (b.shape not in REVERSALS | {None} or not all(map(isfinite, (b.open,b.high,b.low,b.close,b.volume)))
            or not (0 < b.low <= min(b.open,b.close) <= max(b.open,b.close) <= b.high) or b.volume < 0):
            raise ValueError(f'잘못된 캔들: {b.day}')
        prev = recent = accel = None
        if i >= 2*n:
            prev = log(bars[i-n].close / bars[i-2*n].close) / n
            recent = log(b.close / bars[i-n].close) / n
            accel = recent <= -cfg.min_drop_per_bar and recent <= prev - cfg.min_acceleration
            if accel:
                last_fast = i
        in_context = last_fast is not None and i - last_fast < cfg.context_bars
        avg = fmean(x.volume for x in bars[i-cfg.volume_bars:i]) if i >= cfg.volume_bars else None
        ratio = b.volume / avg if avg is not None and avg > 0 else None
        volume_high = ratio is not None and ratio >= cfg.volume_multiple
        active = [s for s in levels if s.known_from <= b.day <= s.through]
        broken &= {s.key for s in active}
        reactions = []
        for s in active:
            was_broken = s.key in broken
            if b.close < s.bottom:
                broken.add(s.key)
            elif b.close >= s.top and s.key in broken:
                broken.discard(s.key)  # 존 안으로만 복귀한 것은 완전 회복이 아니다.
            if b.low <= s.top and b.high >= s.bottom and b.close >= s.bottom and s.key not in broken and not was_broken and b.open >= s.bottom:
                reactions.append(s.key)
        events: list[str] = []
        event_anchor: date | None = None
        if anchor:
            ref = anchor.close  # 실험용 '저점 몸통 마감가': 꼬리 저가와 분리
            age = (b.day - anchor.day).days
            if age > cfg.max_age or b.close < ref*(1-cfg.tolerance):
                events.append('anchor_expired' if age > cfg.max_age else 'anchor_lost_on_close')
                event_anchor, anchor, bounced = anchor.day, None, False
            elif not bounced:
                if b.close >= ref*(1+cfg.rebound):
                    bounced = True
                    events.append('bounce_observed')
                    event_anchor = anchor.day
            elif b.low <= ref*(1+cfg.tolerance) and b.high >= ref*(1-cfg.tolerance):
                # 이전 봉에서 이미 반등 확인. 같은 봉 안에서 반등과 재시험 순서를 가정하지 않는다.
                if b.low < anchor.low and b.close < anchor.low:
                    events.append('wick_not_recovered')
                else:
                    shaped = b.shape in REVERSALS
                    if shaped or not unshaped_seen:
                        events.append('retest_preferred' if shaped else 'retest_observed')
                        if b.low < anchor.low:
                            events.append('first_wick_undercut_recovered')
                    event_anchor = anchor.day
                    if shaped:
                        anchor, bounced = None, False
                    else:
                        unshaped_seen = True
        # 기존 기준을 처리한 날 중복 후보를 방지. 이탈 후 새 하단 지지가 생기면 새 기준 봉은 허용한다.
        if in_context and anchor is None and not any(e.startswith('retest_') for e in events):
            heavy_red = volume_high and (b.open-b.close)/b.open >= cfg.large_red_body
            if heavy_red:
                events.append('volume_red_watch_only')
                anchor = b
            elif b.shape == 'doji' and reactions:
                events.append('direct_doji_candidate' if volume_high else 'doji_anchor_watch')
                anchor = b
            elif b.shape in REVERSALS:
                events.append('shape_observed_only')
            if anchor is not None:
                event_anchor, bounced, unshaped_seen = anchor.day, False, False
        out.append(Observation(b.day,prev,recent,accel,ratio,tuple(events),
                               event_anchor or (anchor.day if anchor else None),tuple(reactions),tuple(sorted(broken))))
    return out
