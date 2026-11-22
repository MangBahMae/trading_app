"""v0.2 단일 엔진의 관찰을 v0.3 검증용 신호로 투영한다. 주문·계좌 모델은 없다."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.services import dashboard

REPO = Path(__file__).resolve().parents[3]
POLICY_SOURCE = 'rapid-drop-v03-draft/2026-11-22 · research/ccx_rapid_drop/example_config.json'
DATA_SOURCE = 'market'
SHAPES = {'doji': '도지', 'hammer': '망치형', 'inverted_hammer': '역망치형'}
CAUTIONS = ['급락 대응 v0.3 검증용 초안 · 체결·포지션·수익성이 아닙니다.', '기존 독립 신호의 근거 개수에 합산하지 않습니다.']


@lru_cache(maxsize=1)
def engine():
    """연구 폴더의 실제 단일 파일을 재사용한다. 운영용 사본은 없다."""
    name = 'ccx_rapid_drop_engine'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, REPO/'research/ccx_rapid_drop/rapid_drop.py')
        if spec is None or spec.loader is None:
            raise RuntimeError('급락 대응 엔진을 읽을 수 없습니다.')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def config():
    values = json.loads((REPO/'research/ccx_rapid_drop/example_config.json').read_text(encoding='utf-8'))
    return engine().Config(**values)


def closed_frame(frame, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError('마감 판정에는 UTC 시각이 필요합니다.')
    result = frame.copy()
    result['open_time'] = pd.to_datetime(result['open_time'], utc=True)
    completed = (pd.to_datetime(result['close_time'], utc=True) < now if 'close_time' in result
                 else result['open_time']+pd.Timedelta(days=1) <= now)
    return result.loc[completed].reset_index(drop=True)


CANDIDATE_TYPES = ('manual_retest_long', 'manual_first_long', 'auto_retest_long')
REASON_NAMES = {
    'manual_zone_or_first_low_broken': '종가가 수동 존 하단 또는 기준 봉 저가를 이탈',
    'automatic_zone_close_broken': '종가가 자동 기준대 하단을 이탈',
    'candidate_reaction_low_broken': '종가가 이 후보의 반응 봉 저가를 이탈',
    'candidate_wick_undercut_recovered': '꼬리가 반응 봉 저가를 하회한 뒤 종가로 회복',
    'support_version_replaced': '같은 수동 지지의 좌표 버전 교체',
    'support_version_ended': '수동 지지 버전의 유효기간 종료',
    'max_age': '기준일로부터 관찰 기한 경과',
}
TITLES = {
    'manual_retest_long': '롱 후보 · 수동 지지 재시험',
    'manual_first_long': '롱 후보 · 수동 지지 첫 반응',
    'auto_retest_long': '롱 후보 · 자동 기준대 재시험',
    'candidate_invalidated': '기존 후보 무효', 'candidate_expired': '후보 관찰 만료',
    'candidate_replaced': '기준 교체', 'support_recovery_trap': '지지 회복 관찰',
    'recovery_observed': '지지 회복 관찰', 'retest_watch': '재시험 접촉 관찰',
    'strong_recovery_observed': '강한 회복 관찰', 'acceleration_warning': '추가 가속',
    'wick_recovery': '꼬리 이탈 후 종가 회복',
}
OBSERVATION_TYPES = {
    'reversal_observed': 'brake_watch', 'support_recovery_trap_watch': 'support_recovery_trap',
    'support_reclaim_without_observed_break': 'recovery_observed',
    'candidate_wick_recovered': 'wick_recovery', 'retest_observed': 'retest_watch',
}


def _wire(record):
    """연구 레코드의 원시 속성을 JSON에서 직접 사용할 수 있게 날짜만 정규화한다."""
    return {key: value.isoformat() if isinstance(value, date) else value
            for key, value in vars(record).items()}


def _blank_reference(source='market'):
    return dict(price=None, bottom=None, top=None, source=source, support_id=None, support_version_id=None)


def _reference(event):
    if event.kind == 'reversal_observed':
        if event.support_version_id is not None:
            return dict(price=None, bottom=event.support_bottom, top=event.support_top, source='manual_support',
                        support_id=event.support_id, support_version_id=event.support_version_id)
        return _blank_reference(event.support_source)
    manual = event.support_version_id is not None
    return dict(price=event.reference_price, bottom=event.reference_bottom, top=event.reference_top,
                source='manual_support' if manual else 'automatic_reference',
                support_id=event.support_id if manual else None, support_version_id=event.support_version_id)


def _market(row, cfg, last_acceleration=None):
    phase = row.regime_phase if row else 'insufficient'
    def day_string(value):
        return value.isoformat() if value else None

    return dict(phase=phase, strong_drop=row.strong_down if row else None,
        accelerating_now=row.accelerating_down if row else None, accelerating_down=row.accelerating_down if row else None,
        previous_speed=row.previous_speed if row else None, recent_speed=row.recent_speed if row else None,
        observation_window=phase in ('sharp_drop', 'post_drop'), last_acceleration_date=day_string(last_acceleration),
        episode_id=row.regime_id if row else None, episode_start=day_string(row.regime_started_on) if row else None,
        last_drop_date=day_string(row.regime_last_sharp_on) if row else None, recovery_line=row.regime_recovery_anchor if row else None,
        post_drop_bars=(row.regime_bars_since_last_sharp or 0) if row else 0, price_recovery_streak=row.regime_price_recovery_streak if row else 0,
        speed_stable_count=row.regime_speed_votes if row else 0, exit_reason=({'price_recovered': 'price_recovery', 'speed_normalized': 'speed_stability'}.get(row.regime_end_reason) if row else None),
        reworsened=row.regime_reaggravated_today if row else False, strong_speed_threshold=-cfg.min_drop_per_bar if cfg else None,
        ease_speed_threshold=-cfg.regime_ease_drop_per_bar if cfg else None, acceleration_delta=cfg.min_acceleration if cfg else None)


def _signal(kind, day, title, evidence, event=None):
    identity = event.candidate_id if kind in CANDIDATE_TYPES else engine().stable_id(
        'signal-v03', day, kind, event.id if event else '')
    return dict(id=identity, type=kind, title=title,
        direction='long' if kind in CANDIDATE_TYPES else 'warning' if kind in ('candidate_invalidated', 'acceleration_warning') else 'reference',
        occurred_on=day.isoformat(), confirmed_at=datetime.combine(day+timedelta(days=1), datetime.min.time(), timezone.utc).isoformat(),
        anchor_id=event.anchor_id if event else None, anchor_day=event.anchor_day.isoformat() if event and event.anchor_day else None,
        reference=_reference(event) if event else _blank_reference(),
        reaction_low=event.candidate_reaction_low if event else None, evidence=evidence, cautions=list(CAUTIONS),
        previous_candidate_ids=list(event.previous_candidate_ids) if event else [],
        event_ids=([event.id] + ([event.related_event_id] if event.related_event_id else [])) if event else [])


def _project_event(event):
    kind = event.kind if event.kind in TITLES else OBSERVATION_TYPES.get(event.kind)
    if not kind:
        return None
    title = TITLES.get(kind)
    shape = SHAPES.get(event.shape, '없음')
    if kind == 'brake_watch':
        title = f'{shape} 관찰'
        if event.support_source == 'unconfirmed':
            title += ' · 지지 미확인'
        elif event.support_source == 'known_no_reaction':
            title += ' · 확인된 지지 반응 없음'
    recent = '미확인' if event.volume_ratio_recent is None else f'{event.volume_ratio_recent:.3f}배'
    previous = '미확인' if event.volume_ratio_anchor_red is None else f'{event.volume_ratio_anchor_red:.3f}배'
    evidence = [f'반전 모양 {shape}', f'직전 3봉 평균 대비 거래량 {recent} · 고거래량 {"해당" if event.volume_high_recent else "미해당/미확인"}',
                f'선행 최근 장대음봉 대비 거래량 {previous}']
    if event.bounce_confirmed_on:
        evidence.append(f'이전 봉까지 반등 확인 {event.bounce_confirmed_on}')
    if event.support_version_id:
        evidence.append(f'수동 지지 {event.support_id} · 버전 {event.support_version_id} · {event.support_bottom}~{event.support_top}')
    if event.related_event_id:
        evidence.append(f'연결 이탈 사건 {event.related_event_id}')
    if event.anchor_initial_low is not None:
        evidence.append(f'기준 봉 저가 {event.anchor_initial_low:,.2f}')
    if event.volume_red_anchor_day:
        evidence.append(f'거래량 비교 장대음봉 {event.volume_red_anchor_day}')
    if event.terminal_reason:
        reason = REASON_NAMES.get(event.terminal_reason, event.terminal_reason)
        evidence.append(reason)
    return _signal(kind, event.day, title, evidence, event)


def _summary(signals, anchors):
    # 같은 날의 모든 사건은 상세에 보존하고 대표 신호만 이 순서로 선택한다.
    priorities = (*CANDIDATE_TYPES, 'candidate_invalidated', 'brake_watch', 'support_recovery_trap',
                  'recovery_observed', 'strong_recovery_observed')
    for kind in priorities:
        chosen = next((s for s in signals if s['type'] == kind), None)
        if chosen:
            title = chosen['title']
            if kind == 'brake_watch' and any(s['type'] in ('support_recovery_trap', 'recovery_observed') for s in signals):
                title = title.split(' · ')[0] + ' · 지지 회복 관찰'
            return dict(title=title, badge='new', caution=None)
    if anchors:
        return dict(title='기준 추적 중', badge='maintained', caution=None)
    for signal in signals:
        if signal['type'] != 'acceleration_warning':
            return dict(title=signal['title'], badge='new', caution=None)
    return dict(title='신호 없음', badge=None, caution=None)


def _anchor(snapshot):
    return dict(id=snapshot.id, day=snapshot.day.isoformat(), source=snapshot.source,
                reference_price=snapshot.reference_price, initial_low=snapshot.initial_low,
                bottom=snapshot.zone_bottom, top=snapshot.zone_top,
                bounced_on=snapshot.bounce_confirmed_on.isoformat() if snapshot.bounce_confirmed_on else None,
                support_id=snapshot.support_id, support_version_id=snapshot.support_version_id)


def project_observations(observations, cfg, prices=None):
    """엔진이 확정한 사건만 표시 모델로 변환한다. 유지 여부와 과거 발행 이력은 분리한다."""
    issued, history, by_date = {}, [], {}
    last_acceleration = None
    for row in observations:
        today = []
        if row.accelerating_down:
            last_acceleration = row.day
            today.append(_signal('acceleration_warning', row.day, TITLES['acceleration_warning'],
                                 ['최근 2봉 속도와 이전 2봉 속도를 마감 시점에서 비교했습니다.']))
        classified_retests = {e.anchor_id for e in row.events
                              if e.kind in ('auto_retest_long', 'manual_retest_long', 'strong_recovery_observed')}
        for event in row.events:
            if event.kind == 'retest_observed' and event.anchor_id in classified_retests:
                continue
            signal = _project_event(event)
            if signal:
                today.append(signal)
                if signal['type'] in CANDIDATE_TYPES:
                    issued[signal['id']] = signal
        history.extend(today)
        maintained = [issued[c.id] for c in row.active_candidates if issued[c.id]['occurred_on'] != row.day.isoformat()]
        anchors = [_anchor(a) for a in row.active_anchors]
        by_date[row.day.isoformat()] = dict(market=_market(row, cfg, last_acceleration), raw_events=[_wire(e) for e in row.events],
            signals=today, maintained_candidates=maintained, active_anchors=anchors, summary=_summary(today, anchors),
            history=list(history), manual_support_status=row.manual_support_status, known_versions=len(row.support_evaluations))
    return by_date


def build_timeline(frame, levels=(), cfg=None):
    cfg = cfg or config()
    shaped = dashboard.candle_patterns.compute_candle_shape(frame)
    bars = [engine().Bar(r.open_time.date(), r.open, r.high, r.low, r.close, r.volume, r.shape) for r in shaped.itertuples()]
    return project_observations(engine().analyze(bars, levels, cfg), cfg)


def read_manual_lines():
    path = Path(dashboard.lines_store.DB_PATH)
    if not path.is_file():
        return []
    # 기존 _connect는 스키마 이관도 하므로 신호 API에서는 읽기 전용 연결만 쓴다.
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM lines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY id")]


def capture_support_snapshot():
    from app.services import rapid_drop_support_history as journal
    return journal.record_snapshot(read_manual_lines())


def response_for_date(day: date, now=None):
    from app.services import rapid_drop_support_history as journal
    empty = dict(enabled=False, schema_version='0.3', symbol='BTCUSDT', interval='1d', date=str(day),
        data_source=DATA_SOURCE, policy_source=POLICY_SOURCE,
        market=_market(None, None), summary=_summary([], []), active_anchors=[], raw_events=[],
        support=dict(status='unconfirmed', known_versions=0, recording_started_at=None, unsupported_line_ids=[], warnings=[]),
        signals=[], maintained_candidates=[], history=[], warnings=[])
    if not dashboard.feature_flags.ENABLE_RAPID_DROP_SIGNALS:
        return empty
    df, _, _ = dashboard._get_base_data(False)
    df = closed_frame(df, now)
    df = df.loc[df['open_time'].dt.date <= day].reset_index(drop=True)
    if df.empty or df['open_time'].iloc[-1].date() != day:
        raise ValueError('선택 날짜의 마감된 BTCUSDT 일봉이 없습니다.')
    warnings = []
    try:
        capture_support_snapshot()
        support = journal.load_levels(as_of=day)
    except (OSError, ValueError, sqlite3.Error) as exc:
        support = dict(levels=[], recording_started_at=None, unsupported_line_ids=[], warnings=[])
        warnings.append(f'지지 이력 확인 실패 · 지지 미확인: {exc}')
    levels = [engine().Level(x['key'], x['bottom'], x['top'], date.fromisoformat(x['known_from']),
                            date.fromisoformat(x['through']), x.get('support_id')) for x in support['levels']]
    state = build_timeline(df, levels)[str(day)]
    return {**empty, 'enabled': True, 'market': state['market'], 'summary': state['summary'], 'raw_events': state['raw_events'],
        'active_anchors': state['active_anchors'],
        'support': dict(status=state['manual_support_status'], known_versions=state['known_versions'],
            recording_started_at=support.get('recording_started_at'),
            unsupported_line_ids=[int(x) for x in support.get('unsupported_line_ids', [])], warnings=support.get('warnings', [])),
        'signals': state['signals'], 'maintained_candidates': state['maintained_candidates'], 'history': state['history'], 'warnings': warnings}
