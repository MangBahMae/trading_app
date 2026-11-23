"""마감 일봉의 돌파·역할 전환을 기존 시장 방향 및 수동 도형 사건과 연결한다."""
from datetime import date

from app.services import dashboard, rapid_drop_signals, rise_response

DATA_SOURCE = 'market'


def build_timeline(frame, versions=()):
    from app.services.breakout_retest import build_days

    versions = tuple(versions)
    rise = rise_response.build_timeline(frame, versions)
    sequence = build_days(frame, versions, rise)
    result = []
    for row, day in zip(sequence, rise, strict=True):
        market = day['details']['market']
        regime = market['ema_regime']
        long_visible = any(event['type'] == 'long_candidate'
                           for events in (row['events'], row['active']) for event in events)
        context = None
        if long_visible and regime == 'bearish':
            context = '역배열 속 반등 · 돌파 가격 지지 확인'
        elif long_visible and regime == 'bullish':
            context = '정배열 · 돌파 가격 지지 확인'
        shared_exits = {e['id'] for e in row['events'] if e['type'] == 'long_exit'}
        remaining_exits = []
        if shared_exits:
            remaining_exits = list(dict.fromkeys(
                label for e in day['events'] if e['id'] not in shared_exits
                if (label := rise_response.long_exit_label(e))))
        result.append(dict(**row, date=day['date'], market_label=day['market'],
                           market_regime=regime, price_direction=market['price_direction'],
                           market_context=context, remaining_long_exits=remaining_exits))
    return result


def response_for_date(day: date, now=None):
    base = dict(enabled=False, symbol='BTCUSDT', interval='1d', date=day.isoformat(),
                data_source=DATA_SOURCE, market_label='실험 OFF', market_regime=None,
                market_context=None, price_direction=None, history_status='unconfirmed',
                known_drawings=0, events=[], active=[], warnings=[], remaining_long_exits=[])
    if not dashboard.feature_flags.ENABLE_BREAKOUT_RETEST:
        return base
    frame = rapid_drop_signals.closed_daily_through(day, now)
    history, warnings = rapid_drop_signals.drawings_as_of(day)
    versions = history['versions']
    known = sum(v['known_from'] <= base['date'] <= v['through'] for v in versions)
    if history['unsupported_line_ids']:
        warnings.append('좌표를 확인할 수 없는 수동 도형은 판정에서 제외했습니다.')
    return {**base, **build_timeline(frame, versions)[-1], 'enabled': True,
            'history_status': history['status'], 'known_drawings': known, 'warnings': warnings}
