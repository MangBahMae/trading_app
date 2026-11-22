"""수동/자동 기준과 각 후보 수명은 시장 상태와 독립이라는 최신 규칙을 검사한다."""
import unittest
from dataclasses import replace
from datetime import date, timedelta

from rapid_drop import Bar, Level, LONG_KINDS, analyze
from test_rapid_drop import C

START = date(2022, 1, 1)
FLAT = (100,101,99,100,100,None)
AUTO_RED = (107,108,98,100,300,None)
BOUNCE = (100,105,99,104,80,None)
AUTO_RETEST = (100.2,101,100,100.2,90,'doji')


def bars(*rows):
    return [Bar(START+timedelta(days=i), *row) for i, row in enumerate(rows)]


def level(**changes):
    return replace(Level('manual:v1',99,101,START,START+timedelta(days=60),'manual'), **changes)


def events(row, kind):
    return [e for e in row.events if e.kind == kind]


class TestSourceLifecycle(unittest.TestCase):
    def test_manual_first_candidate_does_not_require_market_warning(self):
        rows = analyze(bars(FLAT, FLAT, (100,101,99.4,100,1,'doji')), (level(),), C)
        row = rows[-1]
        self.assertEqual(row.regime_phase, 'normal')
        candidate, = events(row, 'manual_first_long')
        self.assertEqual(candidate.anchor_source, 'manual')
        self.assertEqual((candidate.reference_bottom,candidate.reference_top), (99,101))
        self.assertFalse(candidate.volume_high_recent)
        self.assertNotIn('reversal_observed', row.event_kinds)

    def test_requested_rapid_drop_and_manual_first_can_occur_on_the_same_day(self):
        path = bars((100,101,99,100,100,None), (99,100,98,99,100,None),
                    (94,95,93.5,94,100,None), (94,95,93,94,100,'doji'),
                    (90,91,89,90,100,None))
        support = level(bottom=94,top=94)
        rows = analyze(path, (support,), C)
        first, = events(rows[3], 'manual_first_long')
        self.assertEqual(rows[3].regime_phase, 'sharp_drop')
        self.assertEqual(first.reference_price, 94)
        self.assertEqual(first.anchor_initial_low, 93)
        invalid, = events(rows[4], 'candidate_invalidated')
        self.assertEqual(invalid.candidate_id, first.candidate_id)
        self.assertEqual(invalid.previous_candidate_ids, (first.candidate_id,))
        without = analyze(path, (), C)
        self.assertIn('reversal_observed', without[3].event_kinds)
        self.assertFalse(any(e.kind in LONG_KINDS for row in without for e in row.events))

    def test_auto_anchor_creation_does_not_require_market_warning(self):
        row = analyze(bars(FLAT,FLAT,FLAT,AUTO_RED), (), C)[-1]
        self.assertEqual(row.regime_phase, 'normal')
        self.assertEqual([a.source for a in row.active_anchors], ['auto'])
        self.assertIn('volume_red_watch_only', row.event_kinds)
        self.assertFalse(any(e.kind in LONG_KINDS for e in row.events))

    def test_large_red_without_required_average_volume_is_not_an_auto_anchor(self):
        row = analyze(bars(FLAT,FLAT,FLAT,(107,108,98,100,100,None)), (), C)[-1]
        self.assertEqual(row.volume_ratio_recent, 1)
        self.assertEqual(row.active_anchors, ())

    def test_manual_first_is_not_blocked_by_an_existing_auto_anchor(self):
        rows = analyze(bars(FLAT,FLAT,FLAT,AUTO_RED,(100,101,99.4,100,1,'doji')), (level(),), C)
        first, = events(rows[-1], 'manual_first_long')
        old_auto = rows[-2].active_anchors[0]
        self.assertEqual(first.anchor_source, 'manual')
        self.assertNotEqual(first.anchor_id, old_auto.id)
        self.assertEqual({a.source for a in rows[-1].active_anchors}, {'manual','auto'})
        self.assertEqual(rows[-1].active_anchor_source, 'manual')

    def test_large_red_and_manual_shape_create_independent_sources(self):
        path = bars(FLAT,FLAT,FLAT,(100,115,94.8,95,300,'inverted_hammer'),
                    (94.5,95,94.2,94.5,100,None))
        rows = analyze(path, (level(bottom=94,top=96),), C)
        row = rows[3]
        self.assertEqual({a.source for a in row.active_anchors}, {'manual','auto'})
        self.assertEqual(len(events(row,'manual_first_long')), 1)
        self.assertNotIn('auto_retest_long', row.event_kinds)
        self.assertEqual([a.source for a in rows[4].active_anchors], ['auto'])
        self.assertEqual(len(events(rows[4],'candidate_invalidated')),1)

    def test_previous_close_not_current_open_controls_manual_reaction(self):
        row = analyze(bars(FLAT,FLAT,(93.8,98,93,94.1,100,'doji')),
                      (level(bottom=94,top=96),), C)[-1]
        self.assertLess(row.day, START+timedelta(days=3))
        self.assertIn('manual_first_long', row.event_kinds)

    def test_recovery_day_is_observation_and_only_next_day_can_be_first(self):
        path = bars(FLAT,FLAT,(93,94,92,93,100,None),
                    (94,95,93,94,100,'doji'),(94,95,93,94,100,'doji'))
        rows = analyze(path, (level(bottom=94,top=96),), C)
        self.assertIn('support_recovery_trap_watch', rows[3].event_kinds)
        self.assertNotIn('manual_first_long', rows[3].event_kinds)
        self.assertIn('manual_first_long', rows[4].event_kinds)

    def test_unobserved_prior_break_is_not_a_trap(self):
        support = level(bottom=94,top=96,known_from=START+timedelta(days=3))
        path = bars(FLAT,FLAT,(93,94,92,93,100,None),(94,95,93,94,100,'doji'))
        row = analyze(path, (support,), C)[-1]
        self.assertIn('support_reclaim_without_observed_break', row.event_kinds)
        self.assertNotIn('support_recovery_trap_watch', row.event_kinds)
        self.assertNotIn('manual_first_long', row.event_kinds)

    def test_volume_uses_the_latest_preceding_large_red_even_if_not_high_volume(self):
        path = bars(FLAT,FLAT,(107,108,98,100,100,None),
                    (105,105.5,85,100,50,'hammer'),(100,101,99,100,100,'doji'))
        rows = analyze(path, (level(),), C)
        first, = events(rows[3], 'manual_first_long')
        self.assertAlmostEqual(first.volume_ratio_anchor_red, .5)
        self.assertEqual(first.volume_red_anchor_day, rows[2].day)
        self.assertNotIn('volume_red_watch_only', rows[2].event_kinds)
        next_reaction, = events(rows[4], 'support_reaction_while_tracking')
        self.assertAlmostEqual(next_reaction.volume_ratio_anchor_red, 2)
        self.assertEqual(next_reaction.volume_red_anchor_day, rows[3].day)

    def test_no_preceding_red_keeps_the_second_volume_ratio_unavailable(self):
        first, = events(analyze(bars(FLAT,FLAT,(100,101,99.4,100,100,'doji')), (level(),), C)[-1],
                         'manual_first_long')
        self.assertIsNone(first.volume_ratio_anchor_red)
        self.assertIsNone(first.volume_red_anchor_day)

    def test_manual_reference_is_invalid_below_first_low_even_inside_manual_zone(self):
        rows = analyze(bars(FLAT,FLAT,(100,101,99.4,100,100,'doji'),
                            (99.2,100,99,99.2,100,None)), (level(),), C)
        first, = events(rows[2], 'manual_first_long')
        invalid, = events(rows[3], 'candidate_invalidated')
        self.assertGreaterEqual(99.2, level().bottom)
        self.assertLess(99.2, first.candidate_reaction_low)
        self.assertEqual(invalid.candidate_id, first.candidate_id)
        self.assertEqual(invalid.terminal_reason, 'manual_zone_or_first_low_broken')

    def test_auto_reference_uses_zone_bottom_not_initial_red_low_as_its_loss_rule(self):
        row = analyze(bars(FLAT,FLAT,FLAT,(107,108,99.5,100,300,None),
                           (99.2,100,99,99.2,100,None)), (), C)[-1]
        self.assertEqual(len(row.active_anchors),1)
        self.assertEqual(row.active_anchors[0].source,'auto')
        lost = analyze(bars(FLAT,FLAT,FLAT,AUTO_RED,(98.5,100,98,98.5,100,None)), (), C)[-1]
        self.assertIn('anchor_lost_on_close', lost.event_kinds)
        self.assertNotIn('candidate_invalidated', lost.event_kinds)

    def test_rebound_requires_a_later_close_above_both_thresholds(self):
        support = level(top=104)
        rows = analyze(bars(FLAT,FLAT,(100,101,99.4,100,100,'doji'),
                            (100,104,99,103,90,None),(103,106,102,105,90,None)), (support,), C)
        self.assertNotIn('bounce_observed', rows[2].event_kinds)
        self.assertNotIn('bounce_observed', rows[3].event_kinds)
        self.assertIn('bounce_observed', rows[4].event_kinds)

    def test_manual_and_auto_retest_use_different_close_rules(self):
        high_retest = (110,112,100,111,90,'hammer')
        manual = analyze(bars(FLAT,FLAT,(100,101,99.4,100,100,'doji'),BOUNCE,high_retest), (level(),), C)[-1]
        self.assertIn('manual_retest_long', manual.event_kinds)
        self.assertEqual(events(manual,'manual_retest_long')[0].close_location,'above_reference_band')
        auto = analyze(bars(FLAT,FLAT,FLAT,AUTO_RED,BOUNCE,high_retest), (), C)[-1]
        self.assertIn('retest_observed',auto.event_kinds)
        self.assertIn('strong_recovery_observed',auto.event_kinds)
        self.assertNotIn('auto_retest_long',auto.event_kinds)

    def test_auto_retest_requires_inside_close_and_first_wick_close_recovery(self):
        good = analyze(bars(FLAT,FLAT,FLAT,AUTO_RED,BOUNCE,AUTO_RETEST), (), C)[-1]
        self.assertIn('auto_retest_long',good.event_kinds)
        missing = analyze(bars(FLAT,FLAT,FLAT,(107,108,99.5,100,300,None),BOUNCE,
                               (99.2,101,98,99.2,90,'hammer')), (), C)[-1]
        self.assertEqual(missing.active_anchors[0].source,'auto')
        self.assertNotIn('auto_retest_long',missing.event_kinds)

    def test_candidate_wick_recovery_is_not_an_invalidation_or_another_long(self):
        rows = analyze(bars(FLAT,FLAT,FLAT,AUTO_RED,BOUNCE,AUTO_RETEST,
                            (100.2,101,99.7,100.2,90,'doji')), (), C)
        born, = events(rows[5],'auto_retest_long')
        recovered, = events(rows[6],'candidate_wick_recovered')
        self.assertEqual(recovered.candidate_id,born.candidate_id)
        self.assertNotIn('candidate_invalidated',rows[6].event_kinds)
        self.assertNotIn('auto_retest_long',rows[6].event_kinds)
        self.assertEqual(rows[6].active_candidates[0].id,born.candidate_id)

    def test_candidate_own_low_failure_does_not_reissue_on_same_surviving_anchor(self):
        rows = analyze(bars(FLAT,FLAT,FLAT,AUTO_RED,BOUNCE,AUTO_RETEST,
                            (99.8,100.5,99.6,99.8,90,'doji'),AUTO_RETEST), (), C)
        born, = events(rows[5],'auto_retest_long')
        invalid, = events(rows[6],'candidate_invalidated')
        self.assertEqual(invalid.candidate_id,born.candidate_id)
        self.assertEqual(invalid.terminal_reason,'candidate_reaction_low_broken')
        self.assertEqual(rows[6].active_anchors[0].id,born.anchor_id)
        self.assertFalse(any(events(row,'auto_retest_long') for row in rows[6:]))

    def test_d_plus_eight_is_valid_and_d_plus_nine_expires_each_issued_candidate(self):
        first = (100,101,99.4,100,100,'doji')
        high = (104,105,103,104,90,None)
        day8 = (100.5,101,99.5,100.5,90,'doji')
        path = bars(FLAT,FLAT,first,BOUNCE,*([high]*6),day8,(101,101.2,99.8,100,90,None))
        rows = analyze(path,(level(),),C)
        first_event, = events(rows[2],'manual_first_long')
        retest, = events(rows[10],'manual_retest_long')
        self.assertEqual((rows[10].day-rows[2].day).days,8)
        ended = events(rows[11],'candidate_expired')
        self.assertEqual({e.candidate_id for e in ended},{first_event.candidate_id,retest.candidate_id})
        self.assertTrue(all(e.terminal_reason=='max_age' for e in ended))
        self.assertFalse(any(c.id in {first_event.candidate_id,retest.candidate_id} for c in rows[11].active_candidates))

    def test_version_replacement_has_its_own_terminal_event_and_new_lifecycle(self):
        old = level(through=START+timedelta(days=3))
        new = level(key='manual:v2',known_from=START+timedelta(days=4))
        path = bars(FLAT,FLAT,FLAT,(100,101,99.4,100,100,'doji'),(100,101,99.4,100,100,'doji'))
        rows = analyze(path,(old,new),C)
        first, = events(rows[3],'manual_first_long')
        replaced, = events(rows[4],'candidate_replaced')
        fresh, = events(rows[4],'manual_first_long')
        self.assertEqual(replaced.candidate_id,first.candidate_id)
        self.assertEqual(replaced.terminal_reason,'support_version_replaced')
        self.assertNotEqual(fresh.candidate_id,first.candidate_id)
        self.assertEqual(fresh.previous_candidate_ids,(first.candidate_id,))
        self.assertEqual(fresh.support_version_id,'manual:v2')

    def test_first_candidate_and_retest_have_different_reaction_lows_and_lifecycles(self):
        path = bars(FLAT,FLAT,(100,101,99.4,100,100,'doji'),BOUNCE,
                    (100.2,101,100,100.2,90,'doji'),(99.8,100.5,99.6,99.8,90,None))
        rows = analyze(path,(level(),),C)
        first, = events(rows[2],'manual_first_long')
        second, = events(rows[4],'manual_retest_long')
        self.assertNotEqual(first.lifecycle_id,second.lifecycle_id)
        self.assertEqual((first.candidate_reaction_low,second.candidate_reaction_low),(99.4,100))
        ended, = events(rows[5],'candidate_invalidated')
        self.assertEqual(ended.candidate_id,second.candidate_id)
        self.assertEqual([c.id for c in rows[5].active_candidates],[first.candidate_id])

    def test_future_inputs_do_not_rewrite_multi_anchor_or_candidate_state(self):
        path = bars(FLAT,FLAT,FLAT,AUTO_RED,(100,101,99.4,100,1,'doji'),BOUNCE,AUTO_RETEST)
        support = level()
        full = analyze(path,(support,),C)
        for k in range(1,len(path)+1):
            self.assertEqual(full[:k],analyze(path[:k],(support,),C))
        future = level(key='future',support_id='future',known_from=path[-1].day+timedelta(days=1),bottom=1,top=2)
        self.assertEqual(full,analyze(path,(future,support),C))
        ids = [event.id for row in full for event in row.events]
        self.assertEqual(len(ids),len(set(ids)))


if __name__ == '__main__':
    unittest.main()
