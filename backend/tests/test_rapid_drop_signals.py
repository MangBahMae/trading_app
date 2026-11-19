"""급락 v0.3 후보 정책: 합성 OHLCV와 기존 모양 함수로 발행·유지·종료를 검증한다."""
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.services import rapid_drop_signals as svc

START = date(2022, 1, 1)
DOJI = (97, 99, 94, 97, 300)
BOUNCE = (97, 103, 96, 102, 80)
HAMMER = (98, 98.2, 93, 97.5, 90)
RED = (97, 98, 89, 91, 350)


def synthetic_frame(*extra):
    rows = [(108, 109, 107, 108, 100), (108, 109, 106, 107, 100),
            (107, 108, 105, 106, 100), (106, 107, 101, 102, 100),
            (102, 103, 96, 97, 100), *extra]
    result = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    result['open_time'] = pd.date_range(START, periods=len(result), tz='UTC')
    result['close_time'] = result['open_time'] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    return result


def known_support(**changes):
    return replace(svc.engine().Level('zone:v1', 96, 98, START, START + timedelta(days=30), 'zone'), **changes)


def signals(state, kind):
    return [x for x in state['signals'] if x['type'] == kind]


def longs(state):
    return [x for x in state['signals'] if x['direction'] == 'long']


def test_single_engine_is_the_research_source_and_is_reused():
    first = svc.engine()
    assert svc.engine() is first
    assert Path(first.__file__).resolve() == (svc.REPO / 'research/ccx_rapid_drop/rapid_drop.py').resolve()


@pytest.mark.parametrize('shape,sample', [
    ('doji', (97, 99, 94, 97, 1)),
    ('hammer', (97, 97.2, 93, 96.8, 1)),
    ('inverted_hammer', (97, 103, 96.8, 97.5, 1)),
])
def test_all_existing_reversal_shapes_can_issue_a_first_candidate_without_new_volume_gate(shape, sample):
    timeline = svc.build_timeline(synthetic_frame(sample), (known_support(),))
    row = timeline['2022-01-06']
    candidate, = signals(row, 'first_brake_long')
    assert candidate['direction'] == 'long'
    assert any(svc.SHAPES[shape] in item for item in candidate['evidence'])
    assert any('고거래량 미해당' in item for item in candidate['evidence'])
    assert candidate['reference']['source'] == 'support_reaction_close'
    assert candidate['reference']['support_version_id'] == 'zone:v1'
    assert candidate['occurred_on'] == '2022-01-06'
    assert candidate['confirmed_at'] == '2022-01-07T00:00:00+00:00'


@pytest.mark.parametrize('shape,sample', [
    ('doji', (97, 99, 94, 97, 90)),
    ('hammer', HAMMER),
    ('inverted_hammer', (97, 103, 96.8, 97.5, 90)),
])
def test_all_existing_reversal_shapes_can_issue_a_retest_candidate(shape, sample):
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, sample), (known_support(),))
    candidate, = signals(timeline['2022-01-08'], 'retest_long')
    first, = signals(timeline['2022-01-06'], 'first_brake_long')
    assert candidate['previous_candidate_ids'] == [first['id']]
    assert any(svc.SHAPES[shape] in item for item in candidate['evidence'])
    assert any('이전 봉까지 반등 확인 2022-01-07' in item for item in candidate['evidence'])
    assert candidate['reference']['source'] == 'automatic_reference'


def test_unknown_support_and_heavy_red_alone_never_issue_first_long():
    timeline = svc.build_timeline(synthetic_frame(RED), ())
    assert not any(longs(row) for row in timeline.values())
    assert timeline['2022-01-06']['manual_support_status'] == 'unconfirmed'


def test_overlapping_heavy_red_and_manual_reversal_issue_one_first_candidate():
    timeline = svc.build_timeline(synthetic_frame((102, 110, 73, 97, 350)), (known_support(),))
    row = timeline['2022-01-06']
    candidate, = longs(row)
    assert candidate['type'] == 'first_brake_long'
    assert candidate['reference']['price'] == 97
    assert any('고거래량 해당' in item for item in candidate['evidence'])


def test_new_manual_reaction_during_red_tracking_has_explicit_different_price_sources():
    support = known_support(bottom=96, top=98, known_from=START + timedelta(days=6))
    timeline = svc.build_timeline(synthetic_frame(RED, (97, 99, 94, 97, 1000)), (support,))
    candidate, = signals(timeline['2022-01-07'], 'first_brake_long')
    assert candidate['reference']['price'] == 91
    assert candidate['reference']['source'] == 'automatic_reference'
    assert any('96' in item and '98' in item and '수동 지지' in item for item in candidate['evidence'])
    assert any('volume_red' in item for item in candidate['evidence'])
    assert any('2.857배' in item for item in candidate['evidence'])


def test_repeated_first_reactions_are_maintained_not_reissued():
    repeated = (97, 99, 94, 97, 100)
    timeline = svc.build_timeline(synthetic_frame(DOJI, repeated, repeated), (known_support(),))
    first, = signals(timeline['2022-01-06'], 'first_brake_long')
    for day in ('2022-01-07', '2022-01-08'):
        assert not signals(timeline[day], 'first_brake_long')
        assert timeline[day]['maintained_candidates'] == [first]
        assert first in timeline[day]['history']
    assert first['occurred_on'] == '2022-01-06'


def test_repeated_retests_are_maintained_and_same_day_first_is_suppressed():
    repeat = (97, 99, 94, 97, 100)
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, repeat, repeat, repeat), (known_support(),))
    issued, = signals(timeline['2022-01-08'], 'retest_long')
    assert len(longs(timeline['2022-01-08'])) == 1
    for day in ('2022-01-09', '2022-01-10'):
        assert not longs(timeline[day])
        assert issued in timeline[day]['maintained_candidates']
    all_retests = [s for row in timeline.values() for s in signals(row, 'retest_long')]
    assert all_retests == [issued]


def test_contact_without_reversal_is_watch_only():
    row = svc.build_timeline(synthetic_frame(RED, (91, 96, 90, 95, 100), (92, 92.1, 90.8, 91, 100)))['2022-01-08']
    assert not longs(row)
    watch, = signals(row, 'retest_watch')
    assert any('없음' in text for text in watch['evidence'])


def test_above_band_hammer_is_watch_with_distance_not_a_long():
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, (115, 120.5, 96, 120, 90)), (known_support(),))
    row = timeline['2022-01-08']
    assert not longs(row)
    watch, = signals(row, 'retest_watch')
    assert any('above_reference_band' in item and '23.711%' in item for item in watch['evidence'])
    assert any('기존 반등 폭 이상 높음 True' in item for item in watch['evidence'])


def test_retest_on_invalidation_day_cannot_issue_for_the_lost_basis():
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, (96.5, 96.7, 90, 95, 90)), (known_support(),))
    row = timeline['2022-01-08']
    first, = signals(timeline['2022-01-06'], 'first_brake_long')
    invalidated, = signals(row, 'candidate_invalidated')
    assert invalidated['previous_candidate_ids'] == [first['id']]
    assert not longs(row)
    assert signals(row, 'retest_watch')
    assert not row['maintained_candidates']
    assert first in row['history']


def test_wick_undercut_requires_its_close_recovery_even_inside_band():
    first = (97, 99, 96.8, 97, 300)
    unrecovered = (97.2, 97.3, 90, 96.5, 90)
    row = svc.build_timeline(synthetic_frame(first, BOUNCE, unrecovered), (known_support(),))['2022-01-08']
    assert not longs(row)
    assert signals(row, 'retest_watch')
    assert not signals(row, 'candidate_invalidated')


def test_same_bar_bounce_does_not_issue_a_retest_candidate():
    row = svc.build_timeline(synthetic_frame(DOJI, (97, 104, 93, 103, 100)), (known_support(),))['2022-01-07']
    assert not signals(row, 'retest_long')


def test_expiry_links_only_issued_candidates_and_does_not_issue_untracked_new_reaction():
    cfg = replace(svc.config(), context_bars=2, max_age=1)
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, DOJI), (known_support(),), cfg)
    first, = signals(timeline['2022-01-06'], 'first_brake_long')
    expired, = signals(timeline['2022-01-08'], 'candidate_expired')
    assert expired['previous_candidate_ids'] == [first['id']]
    assert expired['direction'] == 'reference'
    assert not longs(timeline['2022-01-08'])
    assert not timeline['2022-01-08']['maintained_candidates']


def test_no_candidate_means_no_fake_candidate_invalidation():
    timeline = svc.build_timeline(synthetic_frame(RED, (91, 92, 79, 80, 100)))
    assert not any(signals(row, 'candidate_invalidated') or signals(row, 'candidate_expired') for row in timeline.values())


def test_same_day_old_loss_and_new_reaction_keep_old_record_and_link_real_previous_candidate():
    new_support = known_support(key='lower:v1', support_id='lower', bottom=90, top=92,
                                known_from=START + timedelta(days=6))
    timeline = svc.build_timeline(synthetic_frame(DOJI, (91, 93, 88, 91, 1000)), (known_support(), new_support))
    old, = signals(timeline['2022-01-06'], 'first_brake_long')
    row = timeline['2022-01-07']
    invalidated, = signals(row, 'candidate_invalidated')
    new, = signals(row, 'first_brake_long')
    assert invalidated['previous_candidate_ids'] == [old['id']]
    assert new['previous_candidate_ids'] == [old['id']]
    assert old['anchor_id'] == invalidated['anchor_id'] != new['anchor_id']
    assert new['reference']['support_version_id'] == 'lower:v1'
    assert old in row['history']
    assert old['occurred_on'] == '2022-01-06'


def test_acceleration_and_observation_window_are_separate_and_candidates_do_not_clear_warning():
    core, cfg = svc.engine(), svc.config()
    frame = synthetic_frame(DOJI, DOJI)
    shaped = svc.dashboard.candle_patterns.compute_candle_shape(frame)
    bars = [core.Bar(r.open_time.date(), r.open, r.high, r.low, r.close, r.volume, r.shape) for r in shaped.itertuples()]
    rows = core.analyze(bars, (known_support(),), cfg)
    rows[5] = replace(rows[5], accelerating_down=True)
    rows[6] = replace(rows[6], accelerating_down=False)
    timeline = svc.project_observations(rows, cfg)
    assert signals(timeline['2022-01-06'], 'first_brake_long')
    assert signals(timeline['2022-01-06'], 'acceleration_warning')
    assert timeline['2022-01-06']['market']['accelerating_down'] is True
    assert timeline['2022-01-07']['market']['accelerating_down'] is False
    assert timeline['2022-01-07']['market']['observation_window'] is True


def test_confirmed_trap_and_unproven_recovery_are_reference_only():
    confirmed = svc.build_timeline(synthetic_frame(DOJI, BOUNCE), (known_support(bottom=100, top=101),))
    trapped, = signals(confirmed['2022-01-07'], 'support_recovery_trap')
    assert trapped['direction'] == 'reference'
    assert trapped['reference']['source'] == 'manual_support'
    assert len(trapped['event_ids']) == 2  # 회복과 같은 버전의 실제 이탈 사건을 구조화해 연결
    assert not longs(confirmed['2022-01-07'])
    assert any('없음' not in e and '연결 이탈 사건' in e for e in trapped['evidence'])
    unproven = svc.build_timeline(synthetic_frame((97, 113, 96, 112, 400)), (known_support(bottom=110, top=111),))
    reclaimed, = signals(unproven['2022-01-06'], 'recovery_observed')
    assert reclaimed['direction'] == 'reference'
    assert len(reclaimed['event_ids']) == 1
    assert not signals(unproven['2022-01-06'], 'support_recovery_trap')
    assert not longs(unproven['2022-01-06'])


def test_future_candles_and_future_support_do_not_change_history_or_asof_state():
    frame = synthetic_frame(DOJI, BOUNCE, HAMMER, HAMMER)
    level = known_support()
    full = svc.build_timeline(frame, (level,))
    for k in range(1, len(frame) + 1):
        prefix = svc.build_timeline(frame.iloc[:k], (level,))
        assert prefix == {key: full[key] for key in list(full)[:k]}
    extra = frame.iloc[[-1] * 4].copy().reset_index(drop=True)
    extra['open_time'] = pd.date_range(frame.open_time.iloc[-1] + pd.Timedelta(days=1), periods=4, tz='UTC')
    extra['close_time'] = extra['open_time'] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    future = known_support(key='future', support_id='future', known_from=extra.open_time.iloc[0].date(), bottom=1, top=2)
    extended = svc.build_timeline(pd.concat([frame, extra], ignore_index=True), (future, level))
    assert {key: extended[key] for key in full} == full


def test_closed_frame_excludes_in_progress_candle_and_requires_timezone():
    frame = synthetic_frame(DOJI)
    closed = svc.closed_frame(frame, datetime_utc('2022-01-06T12:00:00+00:00'))
    assert len(closed) == 5
    assert closed.open_time.iloc[-1].date() == date(2022, 1, 5)
    with pytest.raises(ValueError):
        svc.closed_frame(frame, pd.Timestamp('2022-01-07'))


def datetime_utc(value):
    return pd.Timestamp(value)


def test_full_fixed_daily_data_issues_one_retest_and_keeps_repeated_contacts_as_maintenance(frozen_daily_data):
    timeline = svc.build_timeline(frozen_daily_data)
    new = [item for row in timeline.values() for item in longs(row)]
    assert [(s['occurred_on'], s['type']) for s in new] == [('2023-06-11', 'retest_long')]
    candidate = new[0]
    assert candidate in timeline['2023-06-12']['maintained_candidates']
    assert candidate in timeline['2023-06-13']['maintained_candidates']
    ended, = signals(timeline['2023-06-14'], 'candidate_expired')
    assert ended['previous_candidate_ids'] == [candidate['id']]
    assert not any(s['reference']['source'] == 'manual_support' for s in new)
