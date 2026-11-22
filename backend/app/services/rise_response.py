"""동일한 마감 일봉에서 시장·롱 종료·숏 판단을 각각 표시한다."""
from datetime import date
import sqlite3

from app.services import dashboard, rapid_drop_signals, rapid_drop_support_history as journal

DATA_SOURCE = 'market'
ISSUED = {'high_retry_failed', 'resistance_rejected', 'support_retest_short'}
SOURCE_LABELS = {'swing_low': '확정 스윙 저점', 'EMA50': 'EMA50', 'EMA200': 'EMA200'}


def _source(event):
    if event['kind'] == 'high_retry_failed':
        return '고점 재시도'
    source = event.get('source', 'manual')
    if source == 'manual':
        return '수동 저항' if event['kind'] == 'resistance_rejected' else '수동 지지'
    return SOURCE_LABELS.get(source, source)


def _lifecycle(events, active, day):
    """발행 ID별 당일 상태. 마감된 날짜별 출력에 이후 상태를 덮어쓰지 않는다."""
    ended = []
    for event in events:
        if event['kind'] in ISSUED:
            active[event['id']] = dict(id=event['id'], label=event['label'], kind=event['kind'],
                                       source=_source(event), started_on=event['date'])
            continue
        ref = event.get('related_id') or event.get('related')
        if ref not in active:
            continue
        terminal = event.get('lifecycle')
        if event['kind'] in ('high_watch_released', 'resistance_watch_released'):
            terminal = 'released'
        if terminal in ('released', 'invalidated'):
            ended.append(dict(active.pop(ref), status=terminal, ended_on=day, reason=event['label']))
    items = [dict(item, status='new' if item['started_on'] == day else 'maintained')
             for item in active.values()] + ended
    for item in items:
        item['age_days'] = (date.fromisoformat(day) - date.fromisoformat(item['started_on'])).days + 1
    return items


def _short_summary(events, states):
    """겹친 근거는 상세에 모두 남기고, 기본 줄은 신규·종료를 우선한다."""
    new = [e['label'] for e in events if e['kind'] in ISSUED]
    closing = [item['reason'] for item in states if 'ended_on' in item]
    labels = list(dict.fromkeys(new + closing))
    if labels:
        return ' / '.join(labels)
    return ' / '.join(dict.fromkeys(item['label'] + ' 유지' for item in states)) or '해당 없음'


def build_timeline(frame, versions=()):
    from app.services.rise_market import market_days
    from app.services.rise_support import support_days

    markets = market_days(frame)
    drawings = support_days(frame, versions, markets)
    result = []
    active = {}
    for stamp, market, drawing in zip(frame['open_time'], markets, drawings, strict=True):
        day = stamp.date().isoformat()
        events = market['events'] + drawing['events']
        states = _lifecycle(events, active, day)
        exits = []
        for event in drawing['events']:
            if event['kind'] == 'trendline_exit_long':
                exits.append(event['label'])
            elif event['kind'] == 'support_break':
                exits.append(f"기존 롱 종료 검토 · {_source(event)} {event['price']:,.2f} 이탈")
        result.append(dict(date=day, market=market['market'],
                           long_exit=' / '.join(dict.fromkeys(exits)) or '해당 없음',
                           short_signal=_short_summary(events, states), events=events,
                           details=dict(market=market['details'], lifecycle=states, drawings={
                               **drawing['details'], 'active_short_ids': drawing['active_short_ids']})))
    return result


def response_for_date(day: date, now=None):
    base = dict(enabled=False, symbol='BTCUSDT', interval='1d', date=day.isoformat(),
                data_source=DATA_SOURCE, market='실험 OFF', long_exit='해당 없음',
                short_signal='해당 없음', events=[], details={})
    if not dashboard.feature_flags.ENABLE_RISE_RESPONSE:
        return base

    frame, _, _ = dashboard._get_base_data(False)
    frame = rapid_drop_signals.closed_frame(frame, now)
    frame = frame.loc[frame['open_time'].dt.date <= day].reset_index(drop=True)
    if frame.empty or frame['open_time'].iloc[-1].date() != day:
        raise ValueError('선택 날짜의 마감된 BTCUSDT 일봉이 없습니다.')

    warnings = []
    try:
        rapid_drop_signals.capture_support_snapshot()
    except (OSError, ValueError, sqlite3.Error):
        warnings.append('현재 수동 도형을 기록하지 못했습니다.')
    try:
        versions = journal.load_drawing_versions(as_of=day)['versions']
    except (OSError, ValueError):
        versions = []
        warnings.append('당시 수동 도형 이력을 확인할 수 없습니다.')
    state = build_timeline(frame, versions)[-1]
    state['details']['warnings'] = warnings
    return {**base, **state, 'enabled': True}
