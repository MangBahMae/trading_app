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
POLICY_SOURCE = 'rapid-drop-v03-draft; research/ccx_rapid_drop/example_config.json'
DATA_SOURCE = 'market'
SHAPES = {'doji': '도지', 'hammer': '망치형', 'inverted_hammer': '역망치형'}
FIRST = {'first_support_reaction', 'support_reaction_while_tracking', 'support_reaction_after_invalidation'}
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


def _reference(event):
    if event.kind == 'reversal_observed' and not event.tracking_anchor:
        return dict(price=None, bottom=None, top=None, source=event.support_source,
                    support_id=None, support_version_id=None)
    if event.kind in ('support_recovery_trap_watch', 'support_reclaim_without_observed_break'):
        return dict(price=event.support_bottom, bottom=event.support_bottom, top=event.support_top,
                    source='manual_support', support_id=event.support_id, support_version_id=event.support_version_id)
    return dict(price=event.reference_price, bottom=event.reference_bottom, top=event.reference_top,
                source='support_reaction_close' if event.kind in FIRST and event.anchor_source == 'support_reversal' else 'automatic_reference',
                support_id=event.support_id, support_version_id=event.support_version_id)


def _volumes(event):
    recent = '미확인' if event.volume_ratio_recent is None else f'{event.volume_ratio_recent:.3f}배'
    red = '기준 장대음봉 없음' if event.volume_ratio_anchor_red is None else f'{event.volume_ratio_anchor_red:.3f}배'
    return [f'직전 평균 대비 거래량 {recent} · 고거래량 {"해당" if event.volume_high_recent else "미해당/미확인"}',
            f'기준 장대음봉 대비 거래량 {red}']


def _signal(kind, day, event=None, prior=(), evidence=(), cautions=(), identity=None):
    titles = {'first_brake_long': '롱 후보 · 첫 제동 반응', 'retest_long': '롱 후보 · 재지지 반응',
              'candidate_invalidated': '기존 롱 후보 무효 · 기준 종가 이탈', 'candidate_expired': '롱 후보 관찰 만료',
              'support_recovery_trap': '이탈 후 회복 · 트랩 후보', 'recovery_observed': '이탈 기록 없는 회복 관찰',
              'acceleration_warning': '추가 가속 경고', 'retest_watch': '재시험 접촉 · 관찰',
              'brake_watch': '첫 제동 관찰'}
    return dict(id=identity or engine().stable_id('signal-v03', day, kind, event.id if event else ''),
        type=kind, title=titles[kind], direction='long' if kind in ('first_brake_long', 'retest_long') else
        'warning' if kind in ('acceleration_warning', 'candidate_invalidated') else 'reference',
        occurred_on=str(day), confirmed_at=datetime.combine(day+timedelta(days=1), datetime.min.time(), timezone.utc).isoformat(),
        anchor_id=event.anchor_id if event else None, anchor_day=str(event.anchor_day) if event else None,
        reference=_reference(event) if event else dict(price=None, bottom=None, top=None, source='market', support_id=None, support_version_id=None),
        evidence=list(evidence), cautions=[*CAUTIONS, *cautions], previous_candidate_ids=list(prior),
        event_ids=([event.id]+([event.related_event_id] if event.related_event_id else [])) if event else [])


SUMMARY_LABELS = {
    'candidate_invalidated': '후보 무효', 'candidate_expired': '관찰 만료',
    'retest_long': '롱 후보 · 재지지', 'first_brake_long': '롱 후보 · 첫 제동',
    'support_recovery_trap': '트랩 관찰', 'recovery_observed': '회복 관찰',
    'brake_watch': '첫 제동 관찰', 'retest_watch': '재시험 접촉 관찰',
}


def _summary(signals, maintained, caution):
    # 당일 종료와 신규 후보가 겹치면 두 사건을 같은 줄에 남긴다.
    kinds = {s['type'] for s in signals}
    new_longs = [kind for kind in ('retest_long', 'first_brake_long') if kind in kinds]
    ended = [kind for kind in ('candidate_invalidated', 'candidate_expired') if kind in kinds]
    if ended and new_longs:
        end_label = '·'.join(SUMMARY_LABELS[kind] for kind in ended)
        new_label = ' / '.join(SUMMARY_LABELS[kind] for kind in new_longs)
        return dict(title=f'이전 {end_label} → 새 {new_label}', badge='new', caution=caution)
    for kind in SUMMARY_LABELS:
        if kind in kinds:
            return dict(title=SUMMARY_LABELS[kind], badge='new', caution=caution)
    if maintained:
        # 유지 후보 중 가장 최근에 발행한 후보를 대표로 표시한다.
        return dict(title=SUMMARY_LABELS[maintained[-1]['type']], badge='maintained', caution=caution)
    return dict(title='신호 없음', badge=None, caution=caution)


def _market(row, cfg, last_acceleration=None):
    def day_string(value):
        return value.isoformat() if value else None

    phase = row.regime_phase if row else 'insufficient'
    accelerating = row.accelerating_down if row else None
    no_new_low = row.regime_no_new_closing_low if row else None
    return dict(
        phase=phase, strong_drop=row.strong_down if row else None,
        accelerating_now=accelerating, accelerating_down=accelerating,
        observation_window=phase == 'active', last_acceleration_date=day_string(last_acceleration),
        previous_speed=row.previous_speed if row else None, recent_speed=row.recent_speed if row else None,
        episode_id=row.regime_id if row else None, episode_start=day_string(row.regime_started_on) if row else None,
        eased_on=day_string(row.regime_eased_on) if row else None,
        previous_low_close=row.regime_previous_lowest_close if row else None,
        episode_low_close=row.regime_lowest_close if row else None,
        new_closing_low=None if no_new_low is None else not no_new_low,
        stable_bars=row.regime_recovery_streak if row else 0, stable_bars_required=cfg.regime_ease_bars if cfg else None,
        strong_speed_threshold=-cfg.min_drop_per_bar if cfg else None,
        ease_speed_threshold=-cfg.regime_ease_drop_per_bar if cfg else None,
        acceleration_delta=cfg.min_acceleration if cfg else None,
    )


def project_observations(observations, cfg, prices=None):
    """발행 기록을 지우지 않고 당일까지의 유지/종료 상태를 따로 반환한다."""
    prices = prices or {}
    issued_keys, active, history, by_date = set(), {}, [], {}
    issued_by_anchor = {}
    last_acceleration = None
    for row in observations:
        today = []
        terminal = {x.anchor_id for x in row.events if x.kind in ('anchor_lost_on_close', 'anchor_expired')}
        if row.accelerating_down:
            last_acceleration = row.day
            today.append(_signal('acceleration_warning', row.day,
                evidence=['현재 인접한 두 구간의 하락 속도가 기존 실험 기준상 가속됐습니다.'],
                cautions=['롱 후보 발생 여부와 별도로 유지되는 시장 경고입니다.']))
        for event in row.events:
            if event.kind not in ('anchor_lost_on_close', 'anchor_expired'):
                continue
            linked = sorted(cid for cid, candidate in active.items() if candidate['anchor_id'] == event.anchor_id)
            if linked:
                kind = 'candidate_invalidated' if event.kind == 'anchor_lost_on_close' else 'candidate_expired'
                today.append(_signal(kind, row.day, event, linked, [f'기준 봉 {event.anchor_day} · {event.kind}'],
                                     ['후보 종료이며 청산·손절 체결·자동 숏 진입이 아닙니다.']))
                for cid in linked:
                    del active[cid]
        eligible = {x.anchor_id for x in row.events if x.kind == 'retest_observed' and x.anchor_id not in terminal
            and x.shape in engine().REVERSALS and x.bounce_confirmed_on is not None and x.bounce_confirmed_on < row.day
            and x.close_location == 'within_reference_band' and (not x.first_wick_undercut or x.wick_recovered_on_close)}
        for event in row.events:
            kind = None
            if event.kind == 'reversal_observed' and row.regime_phase == 'active':
                support_note = '지지 미확인' if event.support_source == 'unconfirmed' else '확인된 지지 반응 없음'
                today.append(_signal('brake_watch', row.day, event, evidence=[
                    f'{SHAPES[event.shape]} · {support_note}', *_volumes(event)]))
            if (event.kind in FIRST and event.tracking_anchor and event.support_source == 'manual'
                    and event.shape in engine().REVERSALS and event.anchor_id not in terminal and event.anchor_id not in eligible):
                kind, key = 'first_brake_long', ('first_brake_long', event.anchor_id, event.support_version_id)
            elif event.kind == 'retest_observed' and event.anchor_id in eligible:
                kind, key = 'retest_long', ('retest_long', event.anchor_id)
            if kind and key not in issued_keys:
                issued_keys.add(key)
                identity = engine().stable_id('candidate-v03', *key)
                previous = sorted(cid for cid, c in active.items() if c['anchor_id'] == event.anchor_id)
                if event.previous_anchor_id:
                    previous = sorted(set(previous) | set(issued_by_anchor.get(event.previous_anchor_id, [])))
                evidence = [f'{SHAPES[event.shape]} · {event.kind}', f'기준 봉 {event.anchor_day} · {event.reference_price:,.2f}', *_volumes(event)]
                if kind == 'first_brake_long':
                    evidence += [f'당시 알려진 수동 지지 {event.support_id} / {event.support_version_id} · {event.support_bottom}~{event.support_top}',
                                 f'유효성 기준은 추적 기준 봉 종가 주변의 자동 기준대입니다. 출처 {event.anchor_source}']
                else:
                    evidence += [f'이전 봉까지 반등 확인 {event.bounce_confirmed_on}', '종가가 기존 허용대 안에서 마감',
                                 f'첫 꼬리 하회 {event.first_wick_undercut} · 종가 회복 {event.wick_recovered_on_close}']
                candidate = _signal(kind, row.day, event, previous, evidence,
                    ['기존 독립 캔들 신호의 장대음봉 무효 규칙과 다른 실험 정책입니다.', '거래량은 근거이며 새로운 필수 조건이 아닙니다.'], identity)
                today.append(candidate)
                active[identity] = candidate
                issued_by_anchor.setdefault(event.anchor_id, []).append(identity)
            if event.kind == 'retest_observed' and event.anchor_id not in eligible:
                distance = (prices[row.day]/event.reference_price-1)*100 if row.day in prices else None
                today.append(_signal('retest_watch', row.day, event, evidence=[
                    f'종가 위치 {event.close_location} · 기준 대비 거리 {distance:.3f}%' if distance is not None else f'종가 위치 {event.close_location}',
                    f'기존 반등 폭 이상 높음 {event.close_far_rebounded} · 반전 모양 {event.shape or "없음"}', *_volumes(event)],
                    cautions=['접촉 사실만으로 롱 후보를 발행하지 않습니다.']))
            if event.kind in ('support_recovery_trap_watch', 'support_reclaim_without_observed_break'):
                kind = 'support_recovery_trap' if event.kind == 'support_recovery_trap_watch' else 'recovery_observed'
                today.append(_signal(kind, row.day, event, evidence=[f'수동 지지 {event.support_id} / 버전 {event.support_version_id}',
                    f'연결 이탈 사건 {event.related_event_id or "없음"}'], cautions=['회복만으로 자동 롱이나 매도 전환을 만들지 않습니다.']))
        history.extend(today)
        maintained = [c for c in active.values() if c['occurred_on'] < str(row.day)]
        caution = None
        if row.manual_support_status == 'unconfirmed' and (row.regime_phase == 'active' or today or maintained):
            caution = '지지 미확인'
        elif any(e.support_source == 'known_no_reaction' for e in row.events if e.kind == 'reversal_observed'):
            caution = '확인된 지지 반응 없음'
        by_date[str(row.day)] = dict(market=_market(row, cfg, last_acceleration), signals=today,
            summary=_summary(today, maintained, caution), raw_events=[vars(e).copy() for e in row.events],
            maintained_candidates=maintained,
            history=list(history), manual_support_status=row.manual_support_status, known_versions=len(row.support_evaluations))
    return by_date


def build_timeline(frame, levels=(), cfg=None):
    cfg = cfg or config()
    shaped = dashboard.candle_patterns.compute_candle_shape(frame)
    bars = [engine().Bar(r.open_time.date(), r.open, r.high, r.low, r.close, r.volume, r.shape) for r in shaped.itertuples()]
    return project_observations(engine().analyze(bars, levels, cfg), cfg, {b.day: b.close for b in bars})


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
        market=_market(None, None), summary=_summary([], [], None), raw_events=[],
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
        'support': dict(status=state['manual_support_status'], known_versions=state['known_versions'],
            recording_started_at=support.get('recording_started_at'),
            unsupported_line_ids=[int(x) for x in support.get('unsupported_line_ids', [])], warnings=support.get('warnings', [])),
        'signals': state['signals'], 'maintained_candidates': state['maintained_candidates'], 'history': state['history'], 'warnings': warnings}
