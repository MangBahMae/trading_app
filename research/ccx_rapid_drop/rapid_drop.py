"""마감 일봉의 시장 상태·수동 지지·자동 기준·후보 수명을 분리한 단일 엔진."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from hashlib import sha256
from math import isfinite, log
from statistics import fmean
from typing import Literal, Sequence

Shape = Literal['doji', 'hammer', 'inverted_hammer'] | None
RegimePhase = Literal['insufficient', 'normal', 'sharp_drop', 'post_drop']
REVERSALS = frozenset({'doji', 'hammer', 'inverted_hammer'})
LONG_KINDS = frozenset({'manual_first_long', 'manual_retest_long', 'auto_retest_long'})
EVENT_KINDS = (
    'volume_red_watch_only', 'first_support_reaction', 'support_reaction_while_tracking',
    'support_reaction_after_invalidation', 'reversal_observed', 'bounce_observed',
    'retest_observed', 'strong_recovery_observed', 'anchor_lost_on_close', 'anchor_expired',
    'support_version_replaced', 'support_break_observed', 'support_recovery_trap_watch',
    'support_reclaim_without_observed_break', 'manual_first_long', 'manual_retest_long',
    'auto_retest_long', 'candidate_invalidated', 'candidate_expired', 'candidate_replaced',
    'candidate_wick_recovered',
)


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    shape: Shape = None  # 모양은 기존 compute_candle_shape 결과를 받는다.


@dataclass(frozen=True)
class Level:
    key: str
    bottom: float
    top: float
    known_from: date
    through: date
    support_id: str | None = None

    @property
    def identity(self) -> str:
        return self.support_id if self.support_id is not None else self.key


@dataclass(frozen=True)
class Config:
    slope_bars: int
    min_drop_per_bar: float
    min_acceleration: float
    context_bars: int  # 이전 실험 설정 호환용. 시장 종료 시계로 사용하지 않는다.
    volume_bars: int
    volume_multiple: float
    large_red_body: float
    rebound: float
    tolerance: float
    max_age: int
    regime_ease_drop_per_bar: float = 0.01
    regime_ease_bars: int = 3  # 속도 정상화 투표의 최근 봉 수
    regime_speed_votes: int = 2
    regime_price_recovery_bars: int = 2
    regime_min_post_drop_bars: int = 3

    def __post_init__(self) -> None:
        for x in (self.slope_bars, self.volume_bars, self.context_bars, self.max_age,
                  self.regime_ease_bars, self.regime_speed_votes, self.regime_price_recovery_bars,
                  self.regime_min_post_drop_bars):
            if type(x) is not int or x < 1:
                raise ValueError('봉 수와 투표 수는 양의 정수여야 합니다.')
        for x in (self.min_drop_per_bar, self.min_acceleration, self.large_red_body, self.rebound):
            if not isfinite(x) or not 0 < x < 1:
                raise ValueError('속도·몸통·반등 기준은 0~1 사이 양수입니다.')
        if not (0 <= self.tolerance < self.rebound) or not isfinite(self.volume_multiple) or self.volume_multiple <= 0:
            raise ValueError('재시험 허용 폭은 반등 기준보다 작고 거래량 배수는 양수여야 합니다.')
        if not isfinite(self.regime_ease_drop_per_bar) or not 0 < self.regime_ease_drop_per_bar < self.min_drop_per_bar:
            raise ValueError('속도 정상화 기준은 0보다 크고 강한 하락 기준보다 작아야 합니다.')
        if self.regime_speed_votes > self.regime_ease_bars:
            raise ValueError('속도 정상화 투표 수는 관찰 봉 수를 넘을 수 없습니다.')


def stable_id(*parts: object) -> str:
    text = ''.join(f'{len(str(x))}:{x}' for x in parts)
    return 'rd02_' + sha256(text.encode('utf-8')).hexdigest()[:24]


@dataclass(frozen=True)
class Anchor:
    id: str
    bar: Bar
    source: str  # manual / auto
    zone_bottom: float
    zone_top: float
    level: Level | None = None
    bounced_on: date | None = None


@dataclass(frozen=True)
class AnchorSnapshot:
    id: str
    source: str
    day: date
    reference_price: float
    initial_low: float
    zone_bottom: float
    zone_top: float
    support_id: str | None
    support_version_id: str | None
    bounce_confirmed_on: date | None


@dataclass(frozen=True)
class CandidateSnapshot:
    id: str
    type: str
    anchor_id: str
    source: str
    issued_on: date
    reaction_low: float
    reference_price: float
    reference_bottom: float
    reference_top: float
    support_id: str | None
    support_version_id: str | None
    previous_candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    day: date
    anchor_id: str | None = None
    anchor_day: date | None = None
    anchor_source: str | None = None
    support_id: str | None = None
    support_version_id: str | None = None
    support_source: str = 'unconfirmed'
    manual_support_status: str = 'unconfirmed'
    support_bottom: float | None = None
    support_top: float | None = None
    manual_support_ids: tuple[str, ...] = ()
    evaluated_support_ids: tuple[str, ...] = ()
    related_event_id: str | None = None
    previous_anchor_id: str | None = None
    tracking_anchor: bool = False
    shape: Shape = None
    reference_price: float | None = None
    reference_bottom: float | None = None
    reference_top: float | None = None
    close_location: str = 'unavailable'
    close_far_rebounded: bool | None = None
    range_tests_reference: bool = False
    lower_wick_tests_reference: bool = False
    first_wick_undercut: bool = False
    wick_recovered_on_close: bool | None = None
    bounce_confirmed_on: date | None = None
    volume_ratio_recent: float | None = None
    volume_high_recent: bool = False
    volume_ratio_anchor_red: float | None = None
    volume_red_anchor_id: str | None = None
    volume_red_anchor_day: date | None = None
    entry_status: str = 'not_evaluated'
    candidate_id: str | None = None
    lifecycle_id: str | None = None
    previous_candidate_ids: tuple[str, ...] = ()
    candidate_reaction_low: float | None = None
    anchor_initial_low: float | None = None
    terminal_reason: str | None = None


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
    strong_down: bool | None = None
    regime_phase: RegimePhase = 'insufficient'
    regime_id: str | None = None
    regime_started_on: date | None = None
    regime_started_today: bool = False
    regime_last_sharp_on: date | None = None
    regime_recovery_anchor: float | None = None
    regime_bars_since_last_sharp: int | None = None
    regime_price_recovery_streak: int = 0
    regime_speed_votes: int = 0
    regime_ended_on: date | None = None
    regime_end_reason: str | None = None
    regime_reaggravated_today: bool = False
    regime_ended_today: bool = False
    active_anchors: tuple[AnchorSnapshot, ...] = ()
    active_candidates: tuple[CandidateSnapshot, ...] = ()
    # 이전 관측 호환용 진단값이며 시장 종료 조건에는 사용하지 않는다.
    regime_eased_on: date | None = None
    regime_eased_today: bool = False
    regime_recovery_streak: int = 0
    regime_previous_lowest_close: float | None = None
    regime_lowest_close: float | None = None
    regime_no_new_closing_low: bool | None = None
    schema_version: str = '0.3'

    @property
    def event_kinds(self) -> tuple[str, ...]:
        return tuple(e.kind for e in self.events)


def _anchor_snapshot(anchor: Anchor) -> AnchorSnapshot:
    return AnchorSnapshot(anchor.id, anchor.source, anchor.bar.day, anchor.bar.close, anchor.bar.low,
                          anchor.zone_bottom, anchor.zone_top,
                          anchor.level.identity if anchor.level else None,
                          anchor.level.key if anchor.level else None, anchor.bounced_on)


def analyze(bars: Sequence[Bar], levels: Sequence[Level], cfg: Config) -> list[Observation]:
    """시장·여러 기준·각 후보의 시간축을 마감된 봉 순서대로 독립 평가한다."""
    if len({s.key for s in levels}) != len(levels):
        raise ValueError('도형 버전마다 고유 key가 필요합니다.')
    ordered_levels = sorted(levels, key=lambda s: s.key)
    versions: dict[str, list[Level]] = {}
    for level in ordered_levels:
        if (not level.key or not level.identity or not all(map(isfinite, (level.bottom, level.top)))
                or not 0 < level.bottom <= level.top or level.known_from > level.through):
            raise ValueError('지지 ID·가격·유효기간을 확인하세요.')
        versions.setdefault(level.identity, []).append(level)
    for group in versions.values():
        group = sorted(group, key=lambda s: s.known_from)
        if any(a.through >= b.known_from for a, b in zip(group, group[1:])):
            raise ValueError('같은 지지 ID의 좌표 버전 기간은 중첩될 수 없습니다.')

    anchors: dict[str, Anchor] = {}
    candidates: dict[str, CandidateSnapshot] = {}
    issued_by_anchor: dict[str, list[str]] = {}
    issued_kinds: set[tuple[str, str]] = set()
    manual_predecessors: dict[str, tuple[str, ...]] = {}
    last_manual_anchor: dict[str, str] = {}
    previous_support_close: dict[str, float] = {}
    broken: dict[str, tuple[Anchor, str | None]] = {}
    latest_red: Bar | None = None
    phase: RegimePhase = 'insufficient'
    regime_id = started_on = last_sharp_on = ended_on = end_reason = None
    last_sharp_index = None
    recovery_anchor = None
    price_streak = 0
    recovery_speeds: list[float] = []
    lowest_close = None
    speeds: list[float | None] = []
    out: list[Observation] = []
    n = cfg.slope_bars

    for i, b in enumerate(bars):
        if i and b.day != bars[i-1].day + timedelta(days=1):
            raise ValueError('중복·역순·누락 일봉은 보간하지 않습니다.')
        if (b.shape not in REVERSALS | {None} or not all(map(isfinite, (b.open, b.high, b.low, b.close, b.volume)))
                or not (0 < b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high) or b.volume < 0):
            raise ValueError(f'잘못된 캔들: {b.day}')
        recent = log(b.close / bars[i-n].close) / n if i >= n else None
        prev = speeds[i-n] if i >= 2*n else None
        strong = recent <= -cfg.min_drop_per_bar if recent is not None else None
        accel = bool(strong and recent - prev <= -cfg.min_acceleration) if prev is not None else None
        speeds.append(recent)
        started_today = reaggravated_today = ended_today = False
        previous_lowest = lowest_close if phase in ('sharp_drop', 'post_drop') else None
        no_new_low = b.close >= previous_lowest if previous_lowest is not None else None
        speed_votes = 0
        if strong:
            if phase not in ('sharp_drop', 'post_drop'):
                regime_id = stable_id('decline-regime', b.day)
                started_on, ended_on, end_reason = b.day, None, None
                lowest_close = b.close
                previous_lowest = no_new_low = None
                started_today = True
            elif phase == 'post_drop':
                reaggravated_today = True
            phase, last_sharp_on, last_sharp_index = 'sharp_drop', b.day, i
            recovery_anchor = bars[i-n].close
            price_streak = 0
            recovery_speeds.clear()
        elif phase in ('sharp_drop', 'post_drop'):
            phase = 'post_drop'
            recovery_speeds.append(recent)
            speed_votes = sum(v > -cfg.regime_ease_drop_per_bar
                              for v in recovery_speeds[-cfg.regime_ease_bars:])
            price_streak = price_streak + 1 if b.close >= recovery_anchor else 0
            price_done = price_streak >= cfg.regime_price_recovery_bars
            speed_done = (i - last_sharp_index >= cfg.regime_min_post_drop_bars
                          and recent > -cfg.regime_ease_drop_per_bar
                          and len(speeds) >= cfg.regime_ease_bars
                          and speed_votes >= cfg.regime_speed_votes)
            if price_done or speed_done:
                phase, ended_on, ended_today = 'normal', b.day, True
                end_reason = 'price_recovered' if price_done else 'speed_normalized'
        elif recent is not None:
            phase = 'normal'
            price_streak = 0
        if lowest_close is not None and (phase in ('sharp_drop', 'post_drop') or ended_today):
            lowest_close = min(lowest_close, b.close)

        average = fmean(x.volume for x in bars[i-cfg.volume_bars:i]) if i >= cfg.volume_bars else None
        ratio = b.volume / average if average is not None and average > 0 else None
        volume_high = ratio is not None and ratio >= cfg.volume_multiple
        large_red = b.close / b.open <= 1 - cfg.large_red_body
        # 당일을 분모에 쓰지 않도록 이 봉 처리가 모두 끝난 뒤 latest_red를 갱신한다.
        volume_reference = latest_red
        red_ratio = b.volume / volume_reference.volume if volume_reference and volume_reference.volume > 0 else None
        red_id = stable_id('large-red-volume-reference', volume_reference.day) if volume_reference else None
        active_levels = [s for s in ordered_levels if s.known_from <= b.day <= s.through]
        level_by_key = {s.key: s for s in active_levels}
        level_by_identity = {s.identity: s for s in active_levels}
        events: list[Event] = []

        def make_anchor(source: str, level: Level | None = None, marker='anchor') -> Anchor:
            bottom, top = ((level.bottom, level.top) if level else
                           (b.close * (1-cfg.tolerance), b.close * (1+cfg.tolerance)))
            return Anchor(stable_id(marker, source, level.key if level else '', b.day), b, source, bottom, top, level)

        def emit(kind: str, ref: Anchor | None = None, *, level: Level | None = None,
                 candidate: CandidateSnapshot | None = None, related=None, predecessor=None,
                 reason=None, prior=()) -> Event:
            level = level or (ref.level if ref else None)
            bottom, top = (ref.zone_bottom, ref.zone_top) if ref else (None, None)
            location = ('unavailable' if bottom is None else 'below_reference_band' if b.close < bottom else
                        'above_reference_band' if b.close > top else 'within_reference_band')
            source = ('manual' if level else 'automatic_reference' if ref else
                      'known_no_reaction' if active_levels else 'unconfirmed')
            event = Event(
                id=stable_id('event', b.day, kind, ref.id if ref else '',
                             level.key if level else '', candidate.id if candidate else ''),
                kind=kind, day=b.day, anchor_id=ref.id if ref else None,
                anchor_day=ref.bar.day if ref else None, anchor_source=ref.source if ref else None,
                support_id=level.identity if level else (ref.id if ref else None),
                support_version_id=level.key if level else None, support_source=source,
                manual_support_status='known' if active_levels else 'unconfirmed',
                support_bottom=level.bottom if level else None, support_top=level.top if level else None,
                manual_support_ids=(level.identity,) if level else (),
                evaluated_support_ids=tuple(s.identity for s in active_levels), related_event_id=related,
                previous_anchor_id=predecessor, tracking_anchor=bool(ref and ref.id in anchors), shape=b.shape,
                reference_price=ref.bar.close if ref else None, reference_bottom=bottom, reference_top=top,
                close_location=location, close_far_rebounded=b.close >= ref.bar.close * (1+cfg.rebound) if ref else None,
                range_tests_reference=bool(ref and b.low <= top and b.high >= bottom),
                lower_wick_tests_reference=bool(ref and b.low < min(b.open, b.close) and b.low <= top and min(b.open, b.close) >= bottom),
                first_wick_undercut=bool(ref and b.low < ref.bar.low),
                wick_recovered_on_close=b.close >= ref.bar.low if ref else None,
                bounce_confirmed_on=ref.bounced_on if ref else None,
                volume_ratio_recent=ratio, volume_high_recent=volume_high,
                volume_ratio_anchor_red=red_ratio, volume_red_anchor_id=red_id,
                volume_red_anchor_day=volume_reference.day if volume_reference else None,
                entry_status='candidate_only' if kind in LONG_KINDS else 'not_evaluated',
                candidate_id=candidate.id if candidate else None, lifecycle_id=candidate.id if candidate else None,
                previous_candidate_ids=tuple(prior), candidate_reaction_low=candidate.reaction_low if candidate else None,
                anchor_initial_low=ref.bar.low if ref else None, terminal_reason=reason)
            events.append(event)
            return event

        def issue(kind: str, ref: Anchor, inherited=()) -> None:
            if (kind, ref.id) in issued_kinds:
                return
            prior = tuple(dict.fromkeys((*inherited, *issued_by_anchor.get(ref.id, ()))))
            candidate = CandidateSnapshot(
                stable_id('candidate', kind, ref.id, b.day), kind, ref.id, ref.source, b.day, b.low,
                ref.bar.close, ref.zone_bottom, ref.zone_top,
                ref.level.identity if ref.level else None, ref.level.key if ref.level else None, prior)
            candidates[candidate.id] = candidate
            issued_kinds.add((kind, ref.id))
            issued_by_anchor.setdefault(ref.id, []).append(candidate.id)
            emit(kind, ref, candidate=candidate, prior=prior)

        # 수동 버전의 관찰된 이탈과 회복은 후보·시장 상태와 독립이다.
        previous_support_close = {k: v for k, v in previous_support_close.items() if k in level_by_key}
        broken = {k: v for k, v in broken.items() if k in level_by_key}
        reactions: list[Level] = []
        support_rows = []
        for level in active_levels:
            previous_close = bars[i-1].close if i else None
            observed_previous = previous_support_close.get(level.key)
            status = 'known_no_reaction'
            if b.close < level.bottom:
                if level.key not in broken:
                    ref = make_anchor('manual', level, 'support-break')
                    event = emit('support_break_observed', ref) if observed_previous is not None and observed_previous >= level.bottom else None
                    broken[level.key] = (ref, event.id if event else None)
                status = 'broken' if broken[level.key][1] else 'below_without_observed_break'
            elif previous_close is not None and previous_close < level.bottom:
                ref, break_id = broken.pop(level.key, (make_anchor('manual', level, 'unproven-recovery'), None))
                kind = 'support_recovery_trap_watch' if break_id else 'support_reclaim_without_observed_break'
                emit(kind, ref, related=break_id)
                status = 'recovery_trap_watch' if break_id else 'reclaim_without_observed_break'
            elif (previous_close is not None and previous_close >= level.bottom
                  and b.low <= level.top and b.high >= level.bottom and b.close >= level.bottom):
                reactions.append(level)
                status = 'reaction'
            previous_support_close[level.key] = b.close
            support_rows.append(SupportEvaluation(level.identity, level.key, level.bottom, level.top, status))

        # 기준 종료를 먼저 처리해야 같은 기준의 종료일에 유효 롱을 만들지 않는다.
        for anchor_id, ref in list(anchors.items()):
            age = (b.day-ref.bar.day).days
            reason = terminal_kind = None
            if ref.level and ref.level.key not in level_by_key:
                if ref.level.identity in level_by_identity:
                    reason, terminal_kind = 'support_version_replaced', 'support_version_replaced'
                else:
                    reason, terminal_kind = 'support_version_ended', 'anchor_expired'
            elif age > cfg.max_age:
                reason, terminal_kind = 'max_age', 'anchor_expired'
            elif ref.source == 'manual' and (b.close < ref.zone_bottom or b.close < ref.bar.low):
                reason, terminal_kind = 'manual_zone_or_first_low_broken', 'anchor_lost_on_close'
            elif ref.source == 'auto' and b.close < ref.zone_bottom:
                reason, terminal_kind = 'automatic_zone_close_broken', 'anchor_lost_on_close'
            if terminal_kind is not None:
                # 같은 날 무효화돼도 접촉 사실은 보존한다.
                if age <= cfg.max_age and ref.bounced_on is not None and b.low <= ref.zone_top and b.high >= ref.zone_bottom:
                    emit('retest_observed', ref)
                emit(terminal_kind, ref, reason=reason)
                linked = tuple(issued_by_anchor.get(ref.id, ()))
                for candidate in list(candidates.values()):
                    if candidate.anchor_id == ref.id:
                        ending = ('candidate_replaced' if terminal_kind == 'support_version_replaced' else
                                  'candidate_expired' if terminal_kind == 'anchor_expired' else 'candidate_invalidated')
                        emit(ending, ref, candidate=candidate, reason=reason, prior=(candidate.id,))
                        del candidates[candidate.id]
                if ref.level:
                    manual_predecessors[ref.level.identity] = linked
                    last_manual_anchor[ref.level.identity] = ref.id
                del anchors[anchor_id]

        for anchor_id, ref in list(anchors.items()):
            for candidate in list(candidates.values()):
                if candidate.anchor_id != ref.id:
                    continue
                if b.close < candidate.reaction_low:
                    emit('candidate_invalidated', ref, candidate=candidate,
                         reason='candidate_reaction_low_broken', prior=(candidate.id,))
                    del candidates[candidate.id]
                elif b.low < candidate.reaction_low:
                    emit('candidate_wick_recovered', ref, candidate=candidate,
                         reason='candidate_wick_undercut_recovered', prior=(candidate.id,))
            if ref.bounced_on is None:
                if b.day > ref.bar.day and b.close >= ref.bar.close * (1+cfg.rebound) and b.close > ref.zone_top:
                    ref = replace(ref, bounced_on=b.day)
                    anchors[anchor_id] = ref
                    emit('bounce_observed', ref)
            elif b.day > ref.bounced_on and b.low <= ref.zone_top and b.high >= ref.zone_bottom:
                emit('retest_observed', ref)
                if ref.source == 'auto' and b.close > ref.zone_top:
                    emit('strong_recovery_observed', ref)
                shape_ok = b.shape in REVERSALS
                close_ok = b.close >= ref.zone_bottom and (ref.source == 'manual' or b.close <= ref.zone_top)
                wick_ok = b.low >= ref.bar.low or b.close >= ref.bar.low
                if shape_ok and close_ok and wick_ok:
                    issue('manual_retest_long' if ref.source == 'manual' else 'auto_retest_long', ref)

        # 새 수동 기준은 기존 자동 기준이나 시장 phase에 막히지 않는다.
        if b.shape in REVERSALS:
            for level in reactions:
                existing = next((a for a in anchors.values() if a.level and a.level.key == level.key), None)
                if existing is None:
                    ref = make_anchor('manual', level)
                    anchors[ref.id] = ref
                    previous_anchor = last_manual_anchor.get(level.identity)
                    emit('support_reaction_after_invalidation' if previous_anchor else 'first_support_reaction', ref,
                         predecessor=previous_anchor)
                    issue('manual_first_long', ref, manual_predecessors.get(level.identity, ()))
                else:
                    emit('support_reaction_while_tracking', existing)

        if large_red and volume_high:
            ref = make_anchor('auto')
            anchors[ref.id] = ref
            emit('volume_red_watch_only', ref)

        # 모양 관찰만 시장 경보·관찰 상태에 한정한다. 후보와 기준 생성은 독립 축이다.
        if phase in ('sharp_drop', 'post_drop') and b.shape in REVERSALS:
            level = reactions[0] if reactions else None
            emit('reversal_observed', level=level)

        ordered_anchors = sorted(anchors.values(), key=lambda a: (a.source != 'manual', a.bar.day, a.id))
        primary = ordered_anchors[0] if ordered_anchors else None
        out.append(Observation(
            day=b.day, previous_speed=prev, recent_speed=recent, accelerating_down=accel,
            volume_ratio_recent=ratio, volume_ratio_anchor_red=red_ratio, volume_red_anchor_id=red_id,
            manual_support_status='known' if active_levels else 'unconfirmed', support_evaluations=tuple(support_rows),
            events=tuple(events), active_anchor_id=primary.id if primary else None,
            active_anchor_day=primary.bar.day if primary else None, active_anchor_source=primary.source if primary else None,
            reaction_levels=tuple(s.key for s in reactions), unrecovered_levels=tuple(sorted(broken)),
            strong_down=strong, regime_phase=phase, regime_id=regime_id, regime_started_on=started_on,
            regime_started_today=started_today, regime_last_sharp_on=last_sharp_on,
            regime_recovery_anchor=recovery_anchor,
            regime_bars_since_last_sharp=(i-last_sharp_index if last_sharp_index is not None
                                          and (phase in ('sharp_drop', 'post_drop') or ended_today) else None),
            regime_price_recovery_streak=price_streak, regime_speed_votes=speed_votes,
            regime_ended_on=ended_on, regime_end_reason=end_reason,
            regime_reaggravated_today=reaggravated_today, regime_ended_today=ended_today,
            active_anchors=tuple(_anchor_snapshot(a) for a in ordered_anchors),
            active_candidates=tuple(sorted(candidates.values(), key=lambda c: (c.issued_on, c.id))),
            regime_eased_on=ended_on, regime_eased_today=ended_today, regime_recovery_streak=price_streak,
            regime_previous_lowest_close=previous_lowest, regime_lowest_close=lowest_close,
            regime_no_new_closing_low=no_new_low))
        if large_red:
            latest_red = b
    return out
