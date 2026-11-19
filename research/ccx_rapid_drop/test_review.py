"""v0.2의 사건 구분·참조 무결성·기존 캔들 함수 연동을 검사한다. 합성 데이터다."""
import sys
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend/app/services'))
from candle_patterns import compute_candle_shape
from rapid_drop import Level, REVERSALS, analyze, stable_id
from test_rapid_drop import C, Z, START, DOJI, BOUNCE, RED, RETEST, series


def existing_shapes(bars):
    frame = pd.DataFrame([{
        'open_time': pd.Timestamp(b.day, tz='UTC'), 'open': b.open,
        'high': b.high, 'low': b.low, 'close': b.close, 'volume': b.volume,
    } for b in bars])
    shapes = compute_candle_shape(frame)['shape'].tolist()
    return [replace(b, shape=s) for b, s in zip(bars, shapes)]


def event(row, kind):
    return next(e for e in row.events if e.kind == kind)


class TestReview(unittest.TestCase):
    def test_three_existing_shapes_at_first_support(self):
        samples = {'doji': DOJI, 'hammer': (97, 97.2, 93, 96.8, 300, None),
                   'inverted_hammer': (97, 103, 96.8, 97.5, 300, None)}
        for shape, sample in samples.items():
            with self.subTest(shape=shape):
                bars = existing_shapes(series(sample))
                self.assertEqual(bars[-1].shape, shape)
                fact = event(analyze(bars, (Z,), C)[-1], 'first_support_reaction')
                self.assertEqual(fact.shape, shape)
                self.assertEqual(fact.support_source, 'manual')
                self.assertEqual(fact.entry_status, 'not_evaluated')

    def test_three_existing_shapes_at_retest(self):
        samples = {'doji': (97, 99, 94, 97, 90, None),
                   'hammer': (98, 98.2, 93, 97.5, 90, None),
                   'inverted_hammer': (97, 103, 96.8, 97.5, 90, None)}
        for shape, sample in samples.items():
            with self.subTest(shape=shape):
                bars = existing_shapes(series(DOJI, BOUNCE, sample))
                fact = event(analyze(bars, (Z,), C)[-1], 'retest_observed')
                self.assertEqual(fact.shape, shape)
                self.assertLess(fact.bounce_confirmed_on, fact.day)
                self.assertEqual(fact.entry_status, 'not_evaluated')

    def test_empty_levels_are_unconfirmed_not_known_negative(self):
        row = analyze(series(DOJI), (), C)[-1]
        self.assertEqual(row.manual_support_status, 'unconfirmed')
        self.assertEqual(row.support_evaluations, ())
        fact = event(row, 'reversal_observed')
        self.assertIsNone(fact.support_id)
        self.assertEqual(fact.support_source, 'unconfirmed')
        self.assertNotIn('first_support_reaction', row.event_kinds)

    def test_known_support_without_reaction_is_explicit(self):
        far = replace(Z, bottom=10, top=11)
        row = analyze(series(DOJI), (far,), C)[-1]
        self.assertEqual(row.manual_support_status, 'known')
        self.assertEqual(row.support_evaluations[0].status, 'known_no_reaction')
        self.assertEqual(event(row, 'reversal_observed').support_source, 'known_no_reaction')
        self.assertEqual(event(row, 'reversal_observed').evaluated_support_ids, (far.identity,))

    def test_far_close_records_wick_contact_and_no_entry(self):
        bars = existing_shapes(series(DOJI, BOUNCE, (115, 120.5, 96, 120, 90, None)))
        fact = event(analyze(bars, (Z,), C)[-1], 'retest_observed')
        self.assertEqual(fact.shape, 'hammer')
        self.assertTrue(fact.range_tests_reference and fact.lower_wick_tests_reference)
        self.assertEqual(fact.close_location, 'above_reference_band')
        self.assertTrue(fact.close_far_rebounded)
        self.assertEqual(fact.entry_status, 'not_evaluated')

    def test_close_in_band_and_above_band_are_different(self):
        row = analyze(series(DOJI, BOUNCE, RETEST), (Z,), C)[-1]
        fact = event(row, 'retest_observed')
        self.assertEqual(fact.close_location, 'within_reference_band')
        self.assertFalse(fact.close_far_rebounded)

    def test_red_and_reversal_are_both_preserved(self):
        bars = existing_shapes(series((102, 110, 73, 97, 350, None)))
        row = analyze(bars, (Z,), C)[-1]
        red, reaction = event(row, 'volume_red_watch_only'), event(row, 'first_support_reaction')
        self.assertEqual(bars[-1].shape, 'doji')
        self.assertNotEqual(red.id, reaction.id)
        self.assertEqual(red.anchor_id, reaction.anchor_id)
        self.assertTrue(all(e.entry_status == 'not_evaluated' for e in row.events))

    def test_live_red_anchor_does_not_hide_support_reversal(self):
        level = replace(Z, bottom=90, top=92)
        rows = analyze(existing_shapes(series(RED, (91, 93, 87, 91, 1000, None))), (level,), C)
        reaction = event(rows[-1], 'support_reaction_while_tracking')
        self.assertEqual(reaction.anchor_id, rows[-2].active_anchor_id)
        self.assertEqual(reaction.support_id, level.key)
        self.assertAlmostEqual(reaction.volume_ratio_anchor_red, 1000/350)
        self.assertNotEqual(reaction.volume_ratio_anchor_red, reaction.volume_ratio_recent)

    def test_new_red_fact_does_not_replace_tracked_anchor(self):
        rows = analyze(series(RED, (100, 101, 90, 92, 1000, None)), (), C)
        red = event(rows[-1], 'volume_red_watch_only')
        self.assertNotEqual(red.anchor_id, rows[-1].active_anchor_id)
        self.assertFalse(red.tracking_anchor)
        self.assertEqual(rows[-2].active_anchor_id, rows[-1].active_anchor_id)

    def test_old_invalidation_and_new_reaction_keep_their_own_refs(self):
        lower = Level('new_v1', 90, 92, START + timedelta(days=6), START + timedelta(days=20), 'lower_zone')
        rows = analyze(existing_shapes(series(DOJI, (91, 93, 88, 91, 1000, None))), (Z, lower), C)
        lost = event(rows[-1], 'anchor_lost_on_close')
        new = event(rows[-1], 'support_reaction_after_invalidation')
        self.assertEqual(lost.anchor_id, rows[-2].active_anchor_id)
        self.assertEqual(lost.anchor_day, rows[-2].day)
        self.assertEqual(new.anchor_day, rows[-1].day)
        self.assertNotEqual(lost.anchor_id, new.anchor_id)
        self.assertEqual(new.previous_anchor_id, lost.anchor_id)
        self.assertEqual((new.support_id, new.support_version_id), ('lower_zone', 'new_v1'))

    def test_retest_and_loss_are_both_facts(self):
        rows = analyze(series(DOJI, BOUNCE, (99, 100, 90, 92, 90, 'hammer')), (Z,), C)
        retest, lost = event(rows[-1], 'retest_observed'), event(rows[-1], 'anchor_lost_on_close')
        self.assertEqual(retest.anchor_id, lost.anchor_id)
        self.assertEqual(retest.close_location, 'below_reference_band')
        self.assertFalse(retest.wick_recovered_on_close)

    def test_shaped_retest_does_not_consume_reference_as_an_entry(self):
        rows = analyze(series(DOJI, BOUNCE, RETEST, RETEST), (Z,), C)
        self.assertEqual(rows[-2].active_anchor_id, rows[-1].active_anchor_id)
        self.assertNotEqual(event(rows[-2], 'retest_observed').id, event(rows[-1], 'retest_observed').id)

    def test_confirmed_break_and_recovery_trap_are_linked(self):
        level = replace(Z, bottom=100, top=101)
        rows = analyze(series(DOJI, BOUNCE), (level,), C)
        broken = event(rows[4], 'support_break_observed')
        recovery = event(rows[-1], 'support_recovery_trap_watch')
        self.assertEqual(recovery.related_event_id, broken.id)
        self.assertEqual(recovery.anchor_id, broken.anchor_id)
        self.assertEqual(recovery.support_id, level.key)
        self.assertNotIn('first_support_reaction', rows[-1].event_kinds)
        self.assertEqual(recovery.entry_status, 'not_evaluated')

    def test_initial_below_support_does_not_fabricate_a_break(self):
        level = replace(Z, bottom=110, top=111)
        rows = analyze(series((97, 113, 96, 112, 400, 'doji')), (level,), C)
        self.assertEqual(rows[0].support_evaluations[0].status, 'below_without_observed_break')
        self.assertFalse(any('support_break_observed' in r.event_kinds for r in rows))
        self.assertIn('support_reclaim_without_observed_break', rows[-1].event_kinds)
        self.assertNotIn('support_recovery_trap_watch', rows[-1].event_kinds)

    def test_partial_zone_recovery_is_not_full_recovery(self):
        level = replace(Z, top=100)
        rows = analyze(series(RED, (91, 99, 90, 98, 100, None), (98, 102, 97, 101, 100, None)), (level,), C)
        self.assertIn(level.key, rows[-2].unrecovered_levels)
        self.assertNotIn('support_recovery_trap_watch', rows[-2].event_kinds)
        self.assertIn('support_recovery_trap_watch', rows[-1].event_kinds)

    def test_support_known_and_through_are_inclusive(self):
        bars = existing_shapes(series(DOJI))
        level = replace(Z, known_from=bars[-1].day, through=bars[-1].day)
        self.assertIn('first_support_reaction', analyze(bars, (level,), C)[-1].event_kinds)

    def test_future_level_and_future_coordinate_version_do_not_change_past(self):
        bars = existing_shapes(series(DOJI, BOUNCE, (98, 98.2, 93, 97.5, 90, None)))
        old = replace(Z, through=bars[-1].day, support_id='zone')
        future = replace(Z, key='future', known_from=bars[-1].day + timedelta(days=1), support_id='zone', bottom=10, top=11)
        self.assertEqual(analyze(bars, (old,), C), analyze(bars, (future, old), C))

    def test_overlapping_versions_and_duplicate_keys_are_rejected(self):
        for levels in ((Z, Z), (replace(Z, support_id='zone'), replace(Z, key='v2', support_id='zone'))):
            with self.assertRaises(ValueError):
                analyze(series(DOJI), levels, C)

    def test_version_change_does_not_inherit_unknown_old_break(self):
        a = replace(Z, key='a', support_id='zone', bottom=110, top=111, through=START + timedelta(days=4))
        b = replace(Z, key='b', support_id='zone', known_from=START + timedelta(days=5))
        row = analyze(series(DOJI), (a, b), C)[-1]
        self.assertEqual(row.support_evaluations[0].version_id, 'b')
        self.assertNotIn('support_recovery_trap_watch', row.event_kinds)
        self.assertIn('first_support_reaction', row.event_kinds)

    def test_expired_broken_level_disappears(self):
        level = replace(Z, bottom=110, top=111, through=START + timedelta(days=3))
        rows = analyze(series(), (level,), C)
        self.assertEqual(rows[3].unrecovered_levels, ('lower',))
        self.assertEqual(rows[4].unrecovered_levels, ())

    def test_ids_are_unique_and_independent_of_level_input_order(self):
        other = replace(Z, key='other')
        bars = series(DOJI, BOUNCE, RETEST, RETEST)
        rows = analyze(bars, (Z, other), C)
        self.assertEqual(rows, analyze(bars, (other, Z), C))
        ids = [e.id for r in rows for e in r.events]
        self.assertEqual(len(ids), len(set(ids)))
        for k in range(1, len(bars)+1):
            self.assertEqual(rows[:k], analyze(bars[:k], (Z, other), C))

    def test_auto_reference_never_claims_manual_support(self):
        rows = analyze(series(RED, (91, 96, 90, 95, 100, None), (93, 94, 88, 91.5, 100, 'doji')), (), C)
        retest = event(rows[-1], 'retest_observed')
        self.assertEqual(retest.support_source, 'automatic_reference')
        self.assertEqual(retest.support_id, retest.anchor_id)
        self.assertEqual(retest.manual_support_status, 'unconfirmed')
        self.assertEqual(retest.volume_red_anchor_day, rows[-3].day)
        self.assertAlmostEqual(retest.volume_ratio_anchor_red, 100/350)

    def test_low_volume_is_metadata_not_a_new_required_gate(self):
        bars = series((97, 99, 94, 97, 1, 'hammer'))
        fact = event(analyze(bars, (Z,), C)[-1], 'first_support_reaction')
        self.assertFalse(fact.volume_high_recent)
        self.assertIsNone(fact.volume_ratio_anchor_red)
        self.assertIsNone(fact.volume_red_anchor_id)

    def test_zero_volume_ratios_are_unavailable(self):
        bars = [replace(b, volume=0) for b in series(DOJI, BOUNCE, RETEST)]
        for row in analyze(bars, (Z,), C):
            self.assertIsNone(row.volume_ratio_recent)
            self.assertIsNone(row.volume_ratio_anchor_red)

    def test_no_same_bar_retest_even_when_the_wick_touches(self):
        row = analyze(series(DOJI, (97, 104, 93, 103, 100, 'hammer')), (Z,), C)[-1]
        self.assertIn('bounce_observed', row.event_kinds)
        self.assertNotIn('retest_observed', row.event_kinds)

    def test_expired_anchor_cannot_generate_a_retest(self):
        row = analyze(series(DOJI, BOUNCE, RETEST), (Z,), replace(C, max_age=1))[-1]
        self.assertIn('anchor_expired', row.event_kinds)
        self.assertNotIn('retest_observed', row.event_kinds)

    def test_stable_id_has_unambiguous_part_boundaries(self):
        self.assertNotEqual(stable_id('a:b', 'c'), stable_id('a', 'b:c'))


if __name__ == '__main__':
    unittest.main()
