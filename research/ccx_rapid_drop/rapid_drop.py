"""급락 대응 관찰기 v0.2. 마감 일봉의 사실만 기록한다. 주문·DB·손익 모델은 없다."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from hashlib import sha256
from math import isfinite, log
from statistics import fmean
from typing import Literal, Sequence

Shape = Literal['doji', 'hammer', 'inverted_hammer'] | None
REVERSALS = frozenset({'doji', 'hammer', 'inverted_hammer'})
EVENT_KINDS = (
    'volume_red_watch_only', 'first_support_reaction', 'support_reaction_while_tracking',
    'support_reaction_after_invalidation', 'reversal_observed', 'bounce_observed',
    'retest_observed', 'anchor_lost_on_close', 'anchor_expired',
    'support_break_observed', 'support_recovery_trap_watch',
    'support_reclaim_without_observed_break',
)


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    shape: Shape = None  # 기존 compute_candle_shape 결과만 받는다.


@dataclass(frozen=True)
class Level:
    key: str                    # 좌표 버전 ID
    bottom: float
    top: float
    known_from: date            # 이 좌표 버전을 사용할 수 있는 첫 마감 봉
    through: date
    support_id: str | None = None  # 같은 도형의 버전들을 묶는 ID, 생략하면 key

    @property
    def identity(self) -> str:
        return self.support_id if self.support_id is not None else self.key


@dataclass(frozen=True)
class Config:
    slope_bars: int
    min_drop_per_bar: float
    min_acceleration: float
    context_bars: int
    volume_bars: int
    volume_multiple: float
    large_red_body: float
    rebound: float
    tolerance: float
    max_age: int

    def __post_init__(self) -> None:
        for x in (self.slope_bars, self.volume_bars, self.context_bars, self.max_age):
            if type(x) is not int or x < 1:
                raise ValueError('봉 수는 양의 정수여야 합니다.')
        for x in (self.min_drop_per_bar, self.min_acceleration, self.large_red_body, self.rebound):
            if not isfinite(x) or not 0 < x < 1:
                raise ValueError('속도·몸통·반등 기준은 0~1 사이 양수입니다.')
        if not (0 <= self.tolerance < self.rebound) or not isfinite(self.volume_multiple) or self.volume_multiple <= 0:
            raise ValueError('재시험 허용 폭은 반등 기준보다 작고, 거래량 배수는 양수여야 합니다.')


def stable_id(*parts: object) -> str:
    # 길이 접두 문자열로 구분하므로 사용자 ID 안의 구분자도 충돌하지 않는다.
    text = ''.join(f'{len(str(x))}:{x}' for x in parts)
    return 'rd02_' + sha256(text.encode('utf-8')).hexdigest()[:24]


@dataclass(frozen=True)
class Anchor:
    id: str
    bar: Bar
    source: str
    manual_support_ids: tuple[str, ...] = ()
    red_bar: Bar | None = None
    bounced_on: date | None = None


def make_anchor(bar: Bar, source: str, supports: tuple[str, ...] = ()) -> Anchor:
    return Anchor(stable_id('anchor', bar.day, source, *supports), bar, source, supports,
                  bar if source == 'volume_red' else None)


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    day: date
    anchor_id: str
    anchor_day: date
    anchor_source: str
    support_id: str | None
    support_version_id: str | None
    support_source: str       # manual / automatic_reference / unconfirmed / known_no_reaction
    manual_support_status: str
    support_bottom: float | None
    support_top: float | None
    manual_support_ids: tuple[str, ...]
    evaluated_support_ids: tuple[str, ...]
    related_event_id: str | None
    previous_anchor_id: str | None
    tracking_anchor: bool
    shape: Shape
    reference_price: float
    reference_bottom: float
    reference_top: float
    close_location: str
    close_far_rebounded: bool
    range_tests_reference: bool
    lower_wick_tests_reference: bool
    first_wick_undercut: bool
    wick_recovered_on_close: bool
    bounce_confirmed_on: date | None
    volume_ratio_recent: float | None
    volume_high_recent: bool
    volume_ratio_anchor_red: float | None
    volume_red_anchor_id: str | None
    volume_red_anchor_day: date | None
    entry_status: str = 'not_evaluated'


@dataclass(frozen=True)
class SupportEvaluation:
    support_id: str
    version_id: str
    bottom: float
    top: float
    status: str


@dataclass(frozen=True)
class Observation:
    day: date
    previous_speed: float | None
    recent_speed: float | None
    accelerating_down: bool | None
    volume_ratio_recent: float | None
    volume_ratio_anchor_red: float | None
    volume_red_anchor_id: str | None
    manual_support_status: str
    support_evaluations: tuple[SupportEvaluation, ...]
    events: tuple[Event, ...]
    active_anchor_id: str | None
    active_anchor_day: date | None
    active_anchor_source: str | None
    reaction_levels: tuple[str, ...]
    unrecovered_levels: tuple[str, ...]
    schema_version: str = '0.2'

    @property
    def event_kinds(self) -> tuple[str, ...]:
        return tuple(e.kind for e in self.events)


def analyze(bars: Sequence[Bar], levels: Sequence[Level], cfg: Config) -> list[Observation]:
    """하나의 기준 추적과 독립적인 사실 기록. 후보/사건 수는 거래 수가 아니다."""
    if len({s.key for s in levels}) != len(levels):
        raise ValueError('도형 버전마다 고유 key가 필요합니다.')
    ordered_levels = sorted(levels, key=lambda s: s.key)
    versions: dict[str, list[Level]] = {}
    for s in ordered_levels:
        if (not isinstance(s.key, str) or not s.key or not isinstance(s.identity, str) or not s.identity
                or not all(map(isfinite, (s.bottom, s.top))) or not 0 < s.bottom <= s.top
                or s.known_from > s.through):
            raise ValueError('지지 ID·가격·유효기간을 확인하세요.')
        versions.setdefault(s.identity, []).append(s)
    for group in versions.values():
        chronological = sorted(group, key=lambda s: s.known_from)
        if any(a.through >= b.known_from for a, b in zip(chronological, chronological[1:])):
            raise ValueError('같은 지지 ID의 좌표 버전 기간은 중첩될 수 없습니다.')

    out: list[Observation] = []
    anchor: Anchor | None = None
    last_invalid: Anchor | None = None
    last_fast: int | None = None
    previous: dict[str, float] = {}
    breaks: dict[str, tuple[Anchor, str]] = {}
    below_initial: dict[str, Anchor] = {}
    n = cfg.slope_bars
    for i, b in enumerate(bars):
        if i and b.day != bars[i-1].day + timedelta(days=1):
            raise ValueError('중복·역순·누락 일봉은 보간하지 않습니다.')
        if (b.shape not in REVERSALS | {None} or not all(map(isfinite, (b.open, b.high, b.low, b.close, b.volume)))
                or not (0 < b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high) or b.volume < 0):
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
        active = [s for s in ordered_levels if s.known_from <= b.day <= s.through]
        events: list[Event] = []

        def emit(kind: str, ref: Anchor, *, level: Level | None = None,
                 unconfirmed: bool = False, related: str | None = None,
                 predecessor: Anchor | None = None) -> Event:
            floor, ceiling = ref.bar.close * (1-cfg.tolerance), ref.bar.close * (1+cfg.tolerance)
            location = ('below_reference_band' if b.close < floor else
                        'above_reference_band' if b.close > ceiling else 'within_reference_band')
            red = ref.red_bar
            red_id = make_anchor(red, 'volume_red').id if red else None
            if level:
                source = 'manual'
            elif unconfirmed:
                source = 'known_no_reaction' if active else 'unconfirmed'
            else:
                source = 'automatic_reference'
            event = Event(
                id=stable_id('event', b.day, kind, ref.id, level.key if level else ''),
                kind=kind, day=b.day, anchor_id=ref.id, anchor_day=ref.bar.day,
                anchor_source=ref.source, support_id=level.identity if level else (None if unconfirmed else ref.id),
                support_version_id=level.key if level else None,
                support_source=source,
                manual_support_status='known' if active else 'unconfirmed',
                support_bottom=level.bottom if level else None, support_top=level.top if level else None,
                manual_support_ids=ref.manual_support_ids,
                evaluated_support_ids=tuple(s.identity for s in active), related_event_id=related,
                previous_anchor_id=predecessor.id if predecessor else None,
                tracking_anchor=anchor is not None and anchor.id == ref.id, shape=b.shape,
                reference_price=ref.bar.close, reference_bottom=floor, reference_top=ceiling,
                close_location=location, close_far_rebounded=b.close >= ref.bar.close * (1+cfg.rebound),
                range_tests_reference=b.low <= ceiling and b.high >= floor,
                lower_wick_tests_reference=b.low < min(b.open, b.close) and b.low <= ceiling and min(b.open, b.close) >= floor,
                first_wick_undercut=b.low < ref.bar.low, wick_recovered_on_close=b.close >= ref.bar.low,
                bounce_confirmed_on=ref.bounced_on, volume_ratio_recent=ratio, volume_high_recent=volume_high,
                volume_ratio_anchor_red=b.volume / red.volume if red and red.volume > 0 else None,
                volume_red_anchor_id=red_id, volume_red_anchor_day=red.day if red else None)
            events.append(event)
            return event

        start_anchor = anchor
        # 이미 지난 봉에서 반등한 기준만 시험한다. 종가 이탈 날도 접촉 사실은 보존한다.
        if anchor:
            age = (b.day - anchor.bar.day).days
            if age <= cfg.max_age and anchor.bounced_on is not None:
                if b.low <= anchor.bar.close * (1+cfg.tolerance) and b.high >= anchor.bar.close * (1-cfg.tolerance):
                    emit('retest_observed', anchor)
            if age > cfg.max_age or b.close < anchor.bar.close * (1-cfg.tolerance):
                emit('anchor_expired' if age > cfg.max_age else 'anchor_lost_on_close', anchor)
                last_invalid, anchor = anchor, None
            elif anchor.bounced_on is None and b.close >= anchor.bar.close * (1+cfg.rebound):
                anchor = replace(anchor, bounced_on=b.day)
                emit('bounce_observed', anchor)

        active_keys = {s.key for s in active}
        previous = {k: v for k, v in previous.items() if k in active_keys}
        breaks = {k: v for k, v in breaks.items() if k in active_keys}
        below_initial = {k: v for k, v in below_initial.items() if k in active_keys}
        reactions: list[Level] = []
        support_rows: list[SupportEvaluation] = []
        for s in active:
            was_unrecovered = s.key in breaks or s.key in below_initial
            status = 'known_no_reaction'
            if b.close < s.bottom:
                if s.key in previous and previous[s.key] >= s.bottom and not was_unrecovered:
                    ref = make_anchor(b, 'support_break', (s.identity,))
                    event = emit('support_break_observed', ref, level=s)
                    breaks[s.key] = (ref, event.id)
                elif s.key not in previous and not was_unrecovered:
                    below_initial[s.key] = make_anchor(b, 'initial_below_support', (s.identity,))
                status = 'broken' if s.key in breaks else 'below_without_observed_break'
            elif b.close >= s.top and was_unrecovered:
                if s.key in breaks:
                    ref, break_event = breaks.pop(s.key)
                    emit('support_recovery_trap_watch', ref, level=s, related=break_event)
                    status = 'recovery_trap_watch'
                else:
                    ref = below_initial.pop(s.key)
                    emit('support_reclaim_without_observed_break', ref, level=s)
                    status = 'reclaim_without_observed_break'
            elif was_unrecovered:
                status = 'broken' if s.key in breaks else 'below_without_observed_break'
            elif b.open < s.bottom and b.close >= s.top:
                emit('support_reclaim_without_observed_break', make_anchor(b, 'unproven_reclaim', (s.identity,)), level=s)
                status = 'reclaim_without_observed_break'
            elif b.low <= s.top and b.high >= s.bottom and b.close >= s.bottom and b.open >= s.bottom:
                reactions.append(s)
                status = 'reaction'
            previous[s.key] = b.close
            support_rows.append(SupportEvaluation(s.identity, s.key, s.bottom, s.top, status))

        # 한 기준만 추적하지만 새 반전과 새 장대음봉의 사실 기록은 가리지 않는다.
        evaluation_context = in_context or start_anchor is not None
        heavy_red = evaluation_context and volume_high and (b.open-b.close)/b.open >= cfg.large_red_body
        reversal = evaluation_context and b.shape in REVERSALS
        prior_active = anchor
        created: Anchor | None = None
        if anchor is None and in_context:
            if heavy_red:
                created = make_anchor(b, 'volume_red')
            elif reversal and reactions:
                created = make_anchor(b, 'support_reversal', tuple(s.identity for s in reactions))
            if created:
                anchor = created
        if heavy_red:
            emit('volume_red_watch_only', make_anchor(b, 'volume_red'))
        if reversal:
            ref = anchor or make_anchor(b, 'reversal_observation')
            if reactions:
                kind = ('support_reaction_while_tracking' if prior_active else
                        'support_reaction_after_invalidation' if last_invalid else 'first_support_reaction')
                for s in reactions:
                    emit(kind, ref, level=s, predecessor=last_invalid if kind == 'support_reaction_after_invalidation' else None)
            else:
                emit('reversal_observed', ref, unconfirmed=True)
        if created:
            last_invalid = None
        measured_anchor = anchor or start_anchor
        red = measured_anchor.red_bar if measured_anchor else None
        out.append(Observation(
            day=b.day, previous_speed=prev, recent_speed=recent, accelerating_down=accel,
            volume_ratio_recent=ratio,
            volume_ratio_anchor_red=b.volume / red.volume if red and red.volume > 0 else None,
            volume_red_anchor_id=make_anchor(red, 'volume_red').id if red else None,
            manual_support_status='known' if active else 'unconfirmed', support_evaluations=tuple(support_rows),
            events=tuple(events), active_anchor_id=anchor.id if anchor else None,
            active_anchor_day=anchor.bar.day if anchor else None, active_anchor_source=anchor.source if anchor else None,
            reaction_levels=tuple(s.key for s in reactions),
            unrecovered_levels=tuple(sorted(set(breaks) | set(below_initial)))))
    return out
