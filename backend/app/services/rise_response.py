"""동일한 마감 일봉에서 시장·롱 종료·숏 판단을 각각 표시한다."""
from datetime import date

from app.services import dashboard, rapid_drop_signals

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


def long_exit_label(event):
    if event['kind'] == 'trendline_exit_long':
        return event['label']
    if event['kind'] == 'support_break':
        return f"기존 롱 종료 검토 · {_source(event)} {event['price']:,.2f} 이탈"
    return None


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
        exits = [label for event in drawing['events'] if (label := long_exit_label(event))]
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

    frame = rapid_drop_signals.closed_daily_through(day, now)
    history, warnings = rapid_drop_signals.drawings_as_of(day)
    state = build_timeline(frame, history['versions'])[-1]
    state['details']['warnings'] = warnings
    return {**base, **state, 'enabled': True}
