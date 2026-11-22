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


def test_summary_priority_is_independent_of_event_order_and_keeps_every_event():
    kinds = ('manual_retest_long', 'manual_first_long', 'auto_retest_long', 'candidate_invalidated', 'brake_watch')
    for index, expected in enumerate(kinds):
        events = [dict(type=kind, title=kind) for kind in reversed(kinds[index:])]
        assert svc._summary(events, [object()]) == dict(title=expected, badge='new', caution=None)
        assert len(events) == len(kinds) - index
    assert svc._summary([], [object()])['title'] == '기준 추적 중'
    assert svc._summary([], [])['title'] == '신호 없음'


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
    candidate, = signals(row, 'manual_first_long')
    assert candidate['direction'] == 'long'
    assert any(svc.SHAPES[shape] in item for item in candidate['evidence'])
    assert any('고거래량 미해당' in item for item in candidate['evidence'])
    assert candidate['reference']['source'] == 'manual_support'
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
    candidate, = signals(timeline['2022-01-08'], 'manual_retest_long')
    first, = signals(timeline['2022-01-06'], 'manual_first_long')
    assert candidate['previous_candidate_ids'] == [first['id']]
    assert any(svc.SHAPES[shape] in item for item in candidate['evidence'])
    assert any('이전 봉까지 반등 확인 2022-01-07' in item for item in candidate['evidence'])
    assert candidate['reference']['source'] == 'manual_support'


def test_unknown_support_and_heavy_red_alone_never_issue_first_long():
    timeline = svc.build_timeline(synthetic_frame(RED), ())
    assert not any(longs(row) for row in timeline.values())
    assert timeline['2022-01-06']['manual_support_status'] == 'unconfirmed'


def test_overlapping_heavy_red_and_manual_reversal_issue_one_first_candidate():
    timeline = svc.build_timeline(synthetic_frame((102, 110, 73, 97, 350)), (known_support(),))
    row = timeline['2022-01-06']
    candidate, = longs(row)
    assert candidate['type'] == 'manual_first_long'
    assert candidate['reference']['price'] == 97
    assert any('고거래량 해당' in item for item in candidate['evidence'])


def test_live_auto_basis_allows_new_manual_basis_after_support_recovery():
    support = known_support(known_from=START + timedelta(days=6))
    recovery = (94, 99, 93, 97, 150)
    fresh = (97, 99, 94, 97, 100)
    timeline = svc.build_timeline(synthetic_frame(RED, recovery, fresh), (support,))
    assert not longs(timeline['2022-01-07'])
    issued, = longs(timeline['2022-01-08'])
    assert issued['type'] == 'manual_first_long'
    assert issued['reference'] == dict(price=97, bottom=96, top=98, source='manual_support',
                                      support_id='zone', support_version_id='zone:v1')
    assert issued['reaction_low'] == 94
    assert any('0.286배' in line for line in issued['evidence'])
    assert len(timeline['2022-01-08']['active_anchors']) == 2


def test_repeated_first_reactions_are_maintained_not_reissued():
    repeated = (97, 99, 94, 97, 100)
    timeline = svc.build_timeline(synthetic_frame(DOJI, repeated, repeated), (known_support(),))
    first, = signals(timeline['2022-01-06'], 'manual_first_long')
    for day in ('2022-01-07', '2022-01-08'):
        assert not signals(timeline[day], 'manual_first_long')
        assert timeline[day]['maintained_candidates'] == [first]
        assert first in timeline[day]['history']
    assert first['occurred_on'] == '2022-01-06'


def test_repeated_retests_are_maintained_and_same_day_first_is_suppressed():
    repeat = (97, 99, 94, 97, 100)
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, repeat, repeat, repeat), (known_support(),))
    issued, = signals(timeline['2022-01-08'], 'manual_retest_long')
    assert len(longs(timeline['2022-01-08'])) == 1
    for day in ('2022-01-09', '2022-01-10'):
        assert not longs(timeline[day])
        assert issued in timeline[day]['maintained_candidates']
    all_retests = [s for row in timeline.values() for s in signals(row, 'manual_retest_long')]
    assert all_retests == [issued]


def test_contact_without_reversal_is_watch_only():
    row = svc.build_timeline(synthetic_frame(RED, (91, 96, 90, 95, 100), (92, 92.1, 90.8, 91, 100)))['2022-01-08']
    assert not longs(row)
    watch, = signals(row, 'retest_watch')
    assert any('없음' in text for text in watch['evidence'])


def test_high_close_is_allowed_for_manual_and_is_strong_recovery_for_auto():
    far = (115, 120.5, 96, 120, 90)
    manual = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, far), (known_support(),))
    assert signals(manual['2022-01-08'], 'manual_retest_long')
    auto = svc.build_timeline(synthetic_frame(RED, (91, 96, 90, 95, 100), (99, 100, 90.5, 99, 90)))
    assert not longs(auto['2022-01-08'])
    assert signals(auto['2022-01-08'], 'strong_recovery_observed')


def test_retest_on_invalidation_day_cannot_issue_for_the_lost_basis():
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, (96.5, 96.7, 90, 95, 90)), (known_support(),))
    row = timeline['2022-01-08']
    first, = signals(timeline['2022-01-06'], 'manual_first_long')
    invalidated, = signals(row, 'candidate_invalidated')
    assert invalidated['previous_candidate_ids'] == [first['id']]
    assert not longs(row)
    assert not row['maintained_candidates']
    assert first in row['history']


def test_wick_undercut_requires_its_close_recovery_even_inside_band():
    first = (97, 99, 96.8, 97, 300)
    unrecovered = (97.2, 97.3, 90, 96.5, 90)
    row = svc.build_timeline(synthetic_frame(first, BOUNCE, unrecovered), (known_support(),))['2022-01-08']
    invalid, = signals(row, 'candidate_invalidated')
    assert not signals(row, 'manual_retest_long')
    # 이전 기준은 F₀ 미회복으로 끝나지만 존 하단 이상인 새 반응은 별도 시도다.
    fresh, = signals(row, 'manual_first_long')
    assert fresh['anchor_id'] != invalid['anchor_id']
    assert fresh['previous_candidate_ids'] == invalid['previous_candidate_ids']


def test_same_bar_bounce_does_not_issue_a_retest_candidate():
    row = svc.build_timeline(synthetic_frame(DOJI, (97, 104, 93, 103, 100)), (known_support(),))['2022-01-07']
    assert not signals(row, 'manual_retest_long')


def test_expiry_ends_the_old_candidate_but_active_episode_allows_a_new_basis():
    cfg = replace(svc.config(), context_bars=2, max_age=1)
    timeline = svc.build_timeline(synthetic_frame(DOJI, BOUNCE, DOJI), (known_support(),), cfg)
    first, = signals(timeline['2022-01-06'], 'manual_first_long')
    expired, = signals(timeline['2022-01-08'], 'candidate_expired')
    assert expired['previous_candidate_ids'] == [first['id']]
    assert expired['direction'] == 'reference'
    replacement, = longs(timeline['2022-01-08'])
    assert replacement['type'] == 'manual_first_long'
    assert replacement['anchor_id'] != expired['anchor_id']
    assert expired['anchor_id'] == first['anchor_id']
    assert not timeline['2022-01-08']['maintained_candidates']


def test_no_candidate_means_no_fake_candidate_invalidation():
    timeline = svc.build_timeline(synthetic_frame(RED, (91, 92, 79, 80, 100)))
    assert not any(signals(row, 'candidate_invalidated') or signals(row, 'candidate_expired') for row in timeline.values())


def test_same_day_old_loss_and_new_reaction_keep_old_record_and_link_real_previous_candidate():
    new_support = known_support(key='lower:v1', support_id='lower', bottom=90, top=92,
                                known_from=START + timedelta(days=6))
    timeline = svc.build_timeline(synthetic_frame(DOJI, (91, 93, 88, 91, 1000)), (known_support(), new_support))
    old, = signals(timeline['2022-01-06'], 'manual_first_long')
    row = timeline['2022-01-07']
    invalidated, = signals(row, 'candidate_invalidated')
    new, = signals(row, 'manual_first_long')
    assert invalidated['previous_candidate_ids'] == [old['id']]
    assert old['anchor_id'] == invalidated['anchor_id'] != new['anchor_id']
    assert new['reference']['support_version_id'] == 'lower:v1'
    assert old in row['history']
    assert old['occurred_on'] == '2022-01-06'
    assert row['summary']['title'] == '롱 후보 · 수동 지지 첫 반응'
    assert row['market']['phase'] == 'sharp_drop'


def test_first_candidate_and_a_single_doji_do_not_end_the_market_episode():
    timeline = svc.build_timeline(synthetic_frame((95, 97, 92, 95, 300), DOJI), (known_support(bottom=94, top=96),))
    first = timeline['2022-01-06']
    assert signals(first, 'manual_first_long') and signals(first, 'acceleration_warning')
    assert first['market']['phase'] == 'sharp_drop' and first['market']['accelerating_now']
    later = timeline['2022-01-07']
    assert later['market']['phase'] == 'post_drop' and not later['market']['accelerating_now']
    assert later['maintained_candidates'] == longs(first)
    assert later['summary']['title'].startswith('도지 관찰')


@pytest.mark.parametrize(('levels', 'caution'), [(False, '지지 미확인'), (True, '확인된 지지 반응 없음')])
def test_reversal_without_valid_support_is_only_a_brake_observation(levels, caution):
    supports = (known_support(bottom=50, top=52),) if levels else ()
    frame = synthetic_frame(DOJI)
    row = svc.build_timeline(frame, supports)['2022-01-06']
    watch, = signals(row, 'brake_watch')
    assert watch['direction'] == 'reference' and not longs(row)
    assert watch['event_ids'][0] in [event['id'] for event in row['raw_events']]
    assert watch['reference']['price'] is None
    assert row['summary']['title'] == f'도지 관찰 · {caution}'


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


def test_full_fixed_daily_data_has_only_unique_auto_retests_without_manual_support(frozen_daily_data):
    timeline = svc.build_timeline(frozen_daily_data)
    new = [item for row in timeline.values() for item in longs(row)]
    assert all(s['type'] == 'auto_retest_long' for s in new)
    assert len(new) == len({s['anchor_id'] for s in new})
    candidate, = [s for s in new if s['occurred_on'] == '2023-06-11']
    assert candidate in timeline['2023-06-12']['maintained_candidates']
    assert candidate in timeline['2023-06-13']['maintained_candidates']
    ended, = signals(timeline['2023-06-14'], 'candidate_expired')
    assert ended['previous_candidate_ids'] == [candidate['id']]
    assert not any(s['reference']['source'] == 'manual_support' for s in new)
