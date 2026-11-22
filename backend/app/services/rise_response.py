"""동일한 마감 일봉에서 시장·롱 종료·숏 판단을 각각 표시한다."""
from datetime import date
import sqlite3

from app.services import dashboard, rapid_drop_signals, rapid_drop_support_history as journal

DATA_SOURCE = 'market'


def build_timeline(frame, versions=()):
    from app.services.rise_market import market_days
    from app.services.rise_support import support_days

    result = []
    for stamp, market, drawing in zip(frame['open_time'], market_days(frame),
                                      support_days(frame, versions), strict=True):
        events = market['events'] + drawing['events']
        labels = {event['kind']: event['label'] for event in events}
        short = [labels[kind] for kind in ('support_retest_short', 'high_retry_failed',
                                           'high_watch_released') if kind in labels]
        if drawing['active_short_ids'] and 'support_retest_short' not in labels:
            short.append('지지 재시험 실패 후보 유지')
        if market['short_watch'] and 'high_retry_failed' not in labels:
            short.append('고점 재시도 실패 관찰 유지')
        result.append(dict(date=stamp.date().isoformat(), market=market['market'],
                           long_exit=labels.get('trendline_exit_long', '해당 없음'),
                           short_signal=' / '.join(short) or '해당 없음', events=events,
                           details=dict(market=market['details'], drawings={
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
