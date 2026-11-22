"""분모·검열·평가용 미래 범위의 작은 수작업 예제를 검사한다. 실제 DB를 사용하지 않는다."""
import unittest
from unittest.mock import patch

import compare_stage_revision as stage

from compare_stage_revision import (INSUFFICIENT, NORMAL, POST, SHARP, distribution,
    episodes, evaluate_candidates, old_state_views, transition_recurrence, warning_runs)


def days(*phases):
    return [dict(day=f'2026-01-{index+1:02}', phase=phase) for index,phase in enumerate(phases)]


class TestStageMetrics(unittest.TestCase):
    def test_legacy_baseline_global_is_restored_after_success_and_error(self):
        original = stage.shared.BASE
        def success(_frame):
            self.assertEqual(stage.shared.BASE, stage.BASE)
            return 'frozen'
        with patch.object(stage.shared, 'baseline', success):
            self.assertEqual(stage.historical_baseline(None), 'frozen')
        self.assertEqual(stage.shared.BASE, original)
        with patch.object(stage.shared, 'baseline', side_effect=RuntimeError('expected')):
            with self.assertRaises(RuntimeError):
                stage.historical_baseline(None)
        self.assertEqual(stage.shared.BASE, original)

    def test_empty_and_nearest_rank_distribution(self):
        self.assertIsNone(distribution([])['p90'])
        self.assertEqual(distribution(list(range(1,11)))['p90'],9)
        self.assertEqual(distribution(list(range(1,11)))['median'],5.5)

    def test_warning_runs_and_episode_warning_days_differ(self):
        rows=days(NORMAL,SHARP,SHARP,POST,SHARP,POST,POST,NORMAL)
        runs,summary=warning_runs(rows)
        self.assertEqual([row['warning_bars'] for row in runs],[2,1])
        records,metrics=episodes(rows)
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['warning_bars'],3)
        self.assertEqual(records[0]['bars_to_observation'],2)
        self.assertEqual(records[0]['bars_to_normal'],6)
        self.assertEqual(metrics['bars_to_normal']['median'],6)

    def test_native_old_view_does_not_invent_an_observation_stage(self):
        timeline={'2026-01-01':dict(market=dict(phase='active',strong_drop=True,accelerating_now=False)),
                  '2026-01-02':dict(market=dict(phase='active',strong_drop=False,accelerating_now=False)),
                  '2026-01-03':dict(market=dict(phase='eased',strong_drop=False,accelerating_now=False))}
        native,mapped=old_state_views(timeline)
        self.assertEqual([row['phase'] for row in native],[SHARP,SHARP,NORMAL])
        self.assertEqual([row['phase'] for row in mapped],[SHARP,POST,NORMAL])
        _,metrics=episodes(native,observation_modelled=False)
        self.assertIsNone(metrics['bars_to_observation'])

    def test_post_recurrence_uses_transitions_not_every_post_day(self):
        rows=days(NORMAL,SHARP,POST,POST,SHARP,POST,NORMAL,NORMAL,NORMAL)
        records,metrics=transition_recurrence(rows,POST)
        self.assertEqual(len(records),2)
        self.assertEqual(metrics['complete_denominator'],2)
        self.assertEqual(metrics['numerator'],1)
        self.assertEqual(metrics['rate'],.5)

    def test_incomplete_horizon_is_excluded_even_when_early_hit_exists(self):
        records,metrics=transition_recurrence(days(NORMAL,SHARP,POST,SHARP),POST)
        self.assertEqual(metrics['complete_denominator'],0)
        self.assertEqual(metrics['censored'],1)
        self.assertEqual(metrics['censored_early_hits'],1)
        self.assertIsNone(metrics['rate'])

    def test_initial_normal_is_not_a_return_event(self):
        records,metrics=transition_recurrence(days(NORMAL,NORMAL,SHARP,POST,NORMAL,NORMAL,NORMAL,NORMAL),NORMAL)
        self.assertEqual([row['day'] for row in records],['2026-01-05'])
        self.assertEqual(metrics['complete_denominator'],1)

    def test_post_recurrence_stops_when_normal_returns(self):
        rows=days(NORMAL,SHARP,POST,NORMAL,SHARP,NORMAL,NORMAL,NORMAL,NORMAL)
        records,metrics=transition_recurrence(rows,POST)
        self.assertEqual(metrics['complete_denominator'],1)
        self.assertEqual(metrics['numerator'],0)
        self.assertEqual(records[0]['normal_return_after_bars'],1)
        _,after_normal=transition_recurrence(rows,NORMAL)
        self.assertEqual(after_normal['numerator'],1)

    def test_candidate_future_window_excludes_issue_bar(self):
        signal=dict(id='one',type='auto_retest_long',direction='long',occurred_on='2026-01-01',anchor_id='a',reference={})
        candles=[dict(day=f'2026-01-{index+1:02}',close=10,high=999 if index==0 else 10+index,low=0 if index==0 else 9-index) for index in range(6)]
        rows,metrics=evaluate_candidates([signal],candles)
        self.assertEqual(rows[0]['future_max_high'],15)
        self.assertEqual(rows[0]['future_min_low'],4)
        self.assertEqual(metrics['max_high_distance_pct']['median'],50)
        self.assertEqual(metrics['complete_denominator'],1)

    def test_candidate_censor_and_duplicate_id_are_explicit(self):
        signal=dict(id='one',type='auto_retest_long',direction='long',occurred_on='2026-01-01',anchor_id='a',reference={})
        candles=[dict(day='2026-01-01',close=10,high=11,low=9),dict(day='2026-01-02',close=10,high=12,low=8)]
        rows,metrics=evaluate_candidates([signal,signal],candles)
        self.assertEqual(metrics['duplicate_ids'],1)
        self.assertEqual(metrics['censored'],1)
        self.assertEqual(metrics['complete_denominator'],0)
        self.assertIsNone(metrics['min_low_distance_pct']['median'])

    def test_candidate_families_keep_unsampled_manual_paths_explicit(self):
        signal=dict(id='one',type='retest_long',direction='long',occurred_on='2026-01-01',anchor_id='a',reference={})
        candles=[dict(day=f'2026-01-{index+1:02}',close=10,high=11,low=9) for index in range(6)]
        grouped=stage.candidate_metrics_by_family([signal],candles)
        self.assertEqual(grouped['auto_retest_long']['unique_ids'],1)
        for family in ('manual_first_long','manual_retest_long'):
            self.assertEqual(grouped[family]['unique_ids'],0)
            self.assertEqual(grouped[family]['complete_denominator'],0)
            self.assertIsNone(grouped[family]['max_high_distance_pct']['median'])

    def test_candidate_type_split_is_reclassification_not_two_new_records(self):
        old=dict(id='old',type='retest_long',direction='long',occurred_on='2026-01-01',anchor_day='2025-12-30',reference=dict(price=10))
        new=dict(old,id='new',type='auto_retest_long')
        result=stage.semantic_diff([old],[new],'api')
        self.assertEqual(result['counts']['reclassified'],1)
        self.assertEqual(result['counts']['added'],0)
        self.assertEqual(result['counts']['removed'],0)

    def test_raw_id_namespace_change_does_not_invent_event_deletion(self):
        old=dict(id='old',kind='retest_observed',day='2026-01-01',anchor_day='2025-12-30',reference_price=10)
        new=dict(old,id='new')
        result=stage.semantic_diff([old],[new],'engine')
        self.assertEqual(result['counts']['retained'],1)
        self.assertEqual(result['matched_id_changes'],1)
        self.assertEqual(result['counts']['removed'],0)


if __name__=='__main__':
    unittest.main()
