"""급등 중 도지, 독립 고점 횡보와 두 번째 시도 실패를 합성 UTC 일봉으로 검증."""
import pandas as pd
import pytest

from app.services import rise_market as engine
from rise_examples import market_example


def frame(rows):
    bars = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close'])
    bars['open_time'] = pd.date_range('2022-01-01', periods=len(bars), tz='UTC')
    bars['volume'] = 100.0
    return bars


def kinds(row):
    return [item['kind'] for item in row['events']]


def test_single_impulse_and_doji_do_not_issue_short():
    rows = engine.market_days(market_example('surge_doji'))
    assert rows[3]['details']['surge_sources'] == ['장대양봉']
    assert 'rise_start' in kinds(rows[3])
    assert rows[4]['details']['candle_shape'] == '도지'
    assert rows[4]['market'] == '배열 미확인'
    assert rows[4]['details']['price_phase'] == rows[5]['details']['price_phase'] == engine.RISING
    assert not any(row['short_watch'] for row in rows)
    assert rows[4]['events'] == []


def test_cumulative_filter_uses_closed_window_as_soon_as_it_finishes():
    # 각 몸통은 작아도 갭을 포함한 창이 3봉 12%, 4봉 16%를 충족한다.
    bars = frame([(100, 102, 99, 101), (104, 107, 103, 106),
                  (110, 113, 109, 112), (115, 117, 114, 116), (116, 117, 115, 116)])
    rows = engine.market_days(bars)
    old = engine.expansion.compute_volatility_expansion(bars)
    assert not rows[1]['details']['surge_sources']
    assert rows[2]['details']['surge_sources'] == ['3봉 누적 급등']
    assert rows[3]['details']['surge_sources'] == ['4봉 누적 급등']
    for i in range(len(bars) - 1):
        matches = [f'{n}봉 누적 급등' for n in old.volatility_expansion_windows[i + 1]]
        assert matches == rows[i]['details']['surge_sources']


def test_sideways_and_retry_have_separate_confirmation_dates_and_release_reference():
    rows = engine.market_days(market_example('high_retry'))
    assert rows[1]['details']['price_phase'] == rows[2]['details']['price_phase'] == engine.RISING
    assert kinds(rows[3]) == ['high_sideways']
    assert rows[3]['details']['price_phase'] == engine.SIDEWAYS
    assert not any(r['short_watch'] for r in rows[:6])
    failed, = rows[6]['events']
    assert failed['kind'] == 'high_retry_failed'
    assert (failed['first_peak_day'], failed['pullback_day'], failed['retry_day'], failed['date']) == (
        '2022-01-04', '2022-01-05', '2022-01-06', '2022-01-07')
    assert failed['peak_relation'] == '비슷한 고점'
    assert rows[7]['short_watch'] and not rows[7]['events']
    released, = rows[8]['events']
    assert released['kind'] == 'high_watch_released'
    assert released['related_id'] == failed['id']
    assert not rows[8]['short_watch']


def test_lower_high_can_fail_without_preceding_sideways():
    rows = engine.market_days(frame([
        (100, 110, 99, 109), (109, 109.5, 105, 106), (106, 106.5, 103, 104),
        (104, 107.8, 103.8, 107), (107, 107.5, 101.5, 103.4)]))
    assert all('high_sideways' not in kinds(r) for r in rows)
    failure, = rows[-1]['events']
    assert failure['kind'] == 'high_retry_failed'
    assert failure['peak_relation'] == '낮은 고점'


def test_wick_under_retry_low_or_above_breakout_does_not_confirm_close():
    bars = market_example('high_retry')
    bars.loc[6, 'close'] = 107.4   # 106.1 꼬리는 두 번째 고점 봉 저가 106.8 아래
    assert not engine.market_days(bars)[6]['short_watch']
    bars = market_example('high_retry')
    bars.loc[8, 'close'] = 110.5   # 113 고가만 돌파
    assert engine.market_days(bars)[8]['short_watch']


def test_market_exit_keeps_existing_short_watch():
    bars = market_example('high_retry').iloc[:8].copy()
    bars.loc[7, ['low', 'close']] = [98, 99]
    rows = engine.market_days(bars)
    assert rows[-1]['details']['price_phase'] == '가격 상승 근거 미확인'
    assert rows[-1]['short_watch'] and not rows[-1]['events']


def test_independent_episode_and_two_releases_on_one_close_keep_distinct_ids():
    first = market_example('high_retry').iloc[:7]
    bars = frame(first[['open', 'high', 'low', 'close']].values.tolist() + [
        (106.6, 107, 94, 95), (95, 103, 94.8, 102), (102, 102.5, 99, 100),
        (100, 101.2, 98.5, 99), (99, 102.4, 98.8, 101.8), (101.8, 101.9, 97, 98.3),
        (98.3, 114, 98, 113)])
    rows = engine.market_days(bars)
    old, = rows[6]['events']
    new, = rows[-2]['events']
    assert old['kind'] == new['kind'] == 'high_retry_failed'
    assert len(rows[-2]['details']['active_watches']) == 2
    releases = rows[-1]['events']
    assert len(releases) == 2 and len({e['id'] for e in releases}) == 2
    assert {e['related_id'] for e in releases} == {old['id'], new['id']}
    assert not rows[-1]['short_watch']


@pytest.mark.parametrize('name', ['surge_doji', 'high_retry'])
def test_all_synthetic_prefixes_reproduce_entire_history(name):
    bars = market_example(name)
    expected = engine.market_days(bars)
    assert all(engine.market_days(bars.iloc[:n]) == expected[:n] for n in range(len(bars) + 1))
    ids = [e['id'] for row in expected for e in row['events']]
    assert len(set(ids)) == len(ids)


def test_gentle_staircase_has_direction_and_retry_without_any_surge():
    bars = market_example('gentle_rise')
    rows = engine.market_days(bars)
    assert all(not row['details']['surge_sources'] for row in rows)
    assert all(not row['details']['surge_context'] for row in rows)
    assert rows[48]['market'] == '배열 미확인'
    assert rows[48]['details']['price_direction'] == 'up'
    assert rows[49]['market'] == '롱 우세 · 정배열 유지'
    failed = [e for row in rows for e in row['events'] if e['kind'] == 'high_retry_failed']
    assert len(failed) == 1
    event = failed[0]
    assert (event['first_peak_day'], event['retry_day'], event['date']) == (
        '2022-03-09', '2022-03-13', '2022-03-15')
    assert not event['surge_since_peak']
    assert rows[-1]['market'] == '롱 우세 · 정배열 유지 · 고점 갱신 둔화'
    assert rows[-1]['details']['active_watches'][0]['age_bars'] == 1


@pytest.mark.parametrize(('case', 'day', 'direction', 'label'), [
    ('mixed_structure', '2022-04-08', 'mixed', '방향 미확인 · 혼조'),
    ('mixed_structure', '2022-04-10', 'up', '상승 우세 · 혼조'),
    ('mixed_fall', '2022-04-10', 'down', '하락 우세 · 혼조'),
])
def test_mixed_uses_both_confirmed_highs_and_lows(case, day, direction, label):
    bars = market_example(case)
    n = bars.index[bars.open_time.dt.strftime('%Y-%m-%d') == day][0] + 1
    row = engine.market_days(bars.iloc[:n])[-1]
    assert row == engine.market_days(bars)[n-1]
    assert row['details']['ema_regime'] == 'mixed'
    assert row['details']['price_direction'] == direction and row['market'] == label
    highs, lows = row['details']['swing_highs'], row['details']['swing_lows']
    points = sorted(highs + lows, key=lambda p: p['date'])
    assert len(points) == 4
    assert all(a['kind'] != b['kind'] for a, b in zip(points, points[1:]))
    for point in points:
        assert pd.Timestamp(point['confirmed_on']) - pd.Timestamp(point['date']) == pd.Timedelta(days=2)
        assert point['confirmed_on'] <= day


def test_new_surge_or_array_change_does_not_clear_tracking():
    rows = engine.market_days(market_example('high_retry'))
    assert rows[7]['details']['active_watches'][0]['age_bars'] == 2
    released = rows[8]['events'][0]
    assert released['started_on'] == '2022-01-07' and released['age_bars'] == 3
    assert rows[8]['details']['surge_sources'] == ['장대양봉']
