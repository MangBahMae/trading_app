"""지속 급락 구간과 추가 가속·완화 조건을 합성 마감 일봉으로 검사한다."""
import math
import unittest
from dataclasses import replace
from datetime import date, timedelta

from rapid_drop import Bar, Config, Level, analyze
from test_rapid_drop import C, Z, DOJI, series

START = date(2022, 1, 1)


def close_series(closes, shapes=None):
    shapes = shapes or {}
    return [Bar(START + timedelta(days=i), p, p + 0.5, p - 0.5, p, 100, shapes.get(i))
            for i, p in enumerate(closes)]


class TestRegime(unittest.TestCase):
    def test_recent_speed_is_available_before_previous_speed(self):
        rows = analyze(close_series([100, 100, 95]), (), C)
        self.assertEqual([r.regime_phase for r in rows[:2]], ['insufficient', 'insufficient'])
        self.assertIsNone(rows[1].recent_speed)
        self.assertAlmostEqual(rows[2].recent_speed, math.log(95 / 100) / 2)
        self.assertIsNone(rows[2].previous_speed)
        self.assertIsNone(rows[2].accelerating_down)
        self.assertTrue(rows[2].strong_down)
        self.assertEqual(rows[2].regime_phase, 'active')
        self.assertTrue(rows[2].regime_started_today)
        self.assertEqual(rows[2].regime_started_on, rows[2].day)

    def test_recent_available_but_not_strong_is_normal(self):
        row = analyze(close_series([100, 100, 99]), (), C)[-1]
        self.assertEqual(row.regime_phase, 'normal')
        self.assertFalse(row.strong_down)
        self.assertIsNone(row.regime_id)

    def test_strong_decline_stays_active_without_additional_acceleration(self):
        bars = close_series([100 * .94**i for i in range(10)], {7: 'doji'})
        rows = analyze(bars, (), replace(C, context_bars=1))
        identity = rows[2].regime_id
        self.assertTrue(identity)
        for row in rows[2:]:
            self.assertEqual(row.regime_phase, 'active')
            self.assertEqual(row.regime_id, identity)
        self.assertTrue(all(r.accelerating_down is False for r in rows[4:]))
        self.assertIn('reversal_observed', rows[7].event_kinds)
        self.assertFalse(rows[7].regime_eased_today)
        self.assertEqual(sum(r.regime_started_today for r in rows), 1)

    def test_three_recovery_bars_ease_from_the_confirmation_day(self):
        rows = analyze(close_series([120, 115, 110, 100, 100, 100, 100, 100, 101]), (), C)
        self.assertEqual([r.regime_recovery_streak for r in rows[5:8]], [1, 2, 3])
        self.assertEqual([r.regime_phase for r in rows[5:8]], ['active', 'active', 'eased'])
        self.assertTrue(rows[7].regime_eased_today)
        self.assertEqual(rows[7].regime_eased_on, rows[7].day)
        self.assertEqual(rows[8].regime_phase, 'eased')
        self.assertFalse(rows[8].regime_eased_today)
        self.assertEqual(rows[8].regime_id, rows[2].regime_id)

    def test_new_closing_low_resets_streak_before_the_low_is_updated(self):
        rows = analyze(close_series([120, 115, 110, 100, 100, 100, 100, 99.9, 99.9, 99.9, 99.9]), (), C)
        before, new_low = rows[6], rows[7]
        self.assertEqual(before.regime_recovery_streak, 2)
        self.assertGreater(new_low.recent_speed, -C.regime_ease_drop_per_bar)
        self.assertEqual(new_low.regime_previous_lowest_close, 100)
        self.assertFalse(new_low.regime_no_new_closing_low)
        self.assertEqual(new_low.regime_lowest_close, 99.9)
        self.assertEqual(new_low.regime_recovery_streak, 0)
        self.assertEqual(new_low.regime_phase, 'active')
        self.assertEqual([r.regime_recovery_streak for r in rows[8:]], [1, 2, 3])
        self.assertEqual(rows[-1].regime_phase, 'eased')

    def test_speed_condition_failure_resets_streak_without_a_new_low(self):
        rows = analyze(close_series([120, 115, 110, 100, 110, 110, 105, 110, 110, 110]), (), C)
        self.assertEqual(rows[5].regime_recovery_streak, 2)
        self.assertTrue(rows[6].regime_no_new_closing_low)
        self.assertLess(rows[6].recent_speed, -C.regime_ease_drop_per_bar)
        self.assertEqual(rows[6].regime_recovery_streak, 0)
        self.assertEqual(rows[6].regime_lowest_close, 100)
        self.assertEqual(rows[6].regime_id, rows[2].regime_id)
        self.assertEqual(rows[-1].regime_phase, 'eased')

    def test_easing_speed_comparison_is_strict(self):
        threshold = -math.log(108 / 110) / 2
        cfg = replace(C, regime_ease_drop_per_bar=threshold)
        rows = analyze(close_series([120, 115, 110, 100, 110, 110, 108]), (), cfg)
        self.assertEqual(rows[5].regime_recovery_streak, 2)
        self.assertEqual(rows[6].recent_speed, -threshold)
        self.assertTrue(rows[6].regime_no_new_closing_low)
        self.assertEqual(rows[6].regime_recovery_streak, 0)
        self.assertEqual(rows[6].regime_phase, 'active')

    def test_wick_low_does_not_replace_the_lowest_close(self):
        bars = close_series([120, 115, 110, 100, 100, 100, 100, 100])
        bars[6] = replace(bars[6], low=70, shape='hammer')
        rows = analyze(bars, (), C)
        self.assertEqual(rows[6].regime_previous_lowest_close, 100)
        self.assertTrue(rows[6].regime_no_new_closing_low)
        self.assertEqual(rows[6].regime_lowest_close, 100)
        self.assertEqual(rows[6].regime_recovery_streak, 2)
        self.assertEqual(rows[7].regime_phase, 'eased')

    def test_strong_decline_after_easing_starts_a_new_regime(self):
        rows = analyze(close_series([120, 115, 110, 100, 100, 100, 100, 100, 101, 90]), (), C)
        first, second = rows[2], rows[-1]
        self.assertEqual(rows[-2].regime_phase, 'eased')
        self.assertEqual(second.regime_phase, 'active')
        self.assertTrue(second.regime_started_today)
        self.assertNotEqual(first.regime_id, second.regime_id)
        self.assertEqual(second.regime_started_on, second.day)
        self.assertIsNone(second.regime_eased_on)
        self.assertEqual(second.regime_recovery_streak, 0)
        self.assertEqual(second.regime_lowest_close, 90)

    def test_supported_reversal_can_start_tracking_before_previous_speed_is_available(self):
        bars = close_series([100, 100, 95], {2: 'doji'})
        level = Level('early', 94, 96, START, START + timedelta(days=10))
        row = analyze(bars, (level,), C)[-1]
        self.assertIsNone(row.previous_speed)
        self.assertTrue(row.regime_started_today)
        self.assertIn('first_support_reaction', row.event_kinds)
        self.assertIsNotNone(row.active_anchor_id)

    def test_reversal_with_unknown_support_and_known_no_reaction_remain_distinct(self):
        bars = close_series([100 * .94**i for i in range(8)], {7: 'hammer'})
        far = Level('far', 10, 11, START, START + timedelta(days=20))
        unknown = analyze(bars, (), C)[-1]
        known = analyze(bars, (far,), C)[-1]
        self.assertEqual(unknown.regime_phase, 'active')
        self.assertEqual(known.regime_phase, 'active')
        self.assertEqual(unknown.manual_support_status, 'unconfirmed')
        self.assertEqual(known.manual_support_status, 'known')
        self.assertEqual(known.support_evaluations[0].status, 'known_no_reaction')
        self.assertEqual(unknown.events[0].support_source, 'unconfirmed')
        self.assertEqual(known.events[0].support_source, 'known_no_reaction')
        self.assertFalse(any(kind.startswith('first_support') for kind in unknown.event_kinds + known.event_kinds))

    def test_first_reversal_observation_stops_when_regime_eases_even_if_anchor_lives(self):
        bars = series(DOJI, (97, 101, 96, 100, 80, None),
                      (100, 101, 99, 100, 90, None), (100, 101, 99, 100, 90, 'doji'))
        upper = Level('upper', 99, 101, START + timedelta(days=8), START + timedelta(days=20))
        rows = analyze(bars, (Z, upper), C)
        self.assertEqual(rows[-1].regime_phase, 'eased')
        self.assertEqual(rows[-1].active_anchor_id, rows[5].active_anchor_id)
        self.assertIn('upper', rows[-1].reaction_levels)
        self.assertNotIn('reversal_observed', rows[-1].event_kinds)
        self.assertNotIn('support_reaction_while_tracking', rows[-1].event_kinds)

    def test_anchor_retest_still_runs_after_easing(self):
        bars = series(DOJI, (97, 101, 96, 100, 80, None),
                      (100, 101, 99, 100, 90, None), (100, 101, 99, 100, 90, None),
                      (98, 98.2, 93, 97.5, 90, 'hammer'))
        rows = analyze(bars, (Z,), C)
        self.assertEqual(rows[-1].regime_phase, 'eased')
        self.assertEqual(rows[-1].active_anchor_id, rows[5].active_anchor_id)
        self.assertIn('retest_observed', rows[-1].event_kinds)
        self.assertNotIn('support_reaction_while_tracking', rows[-1].event_kinds)

    def test_future_data_and_future_support_do_not_change_regime_or_reversal_history(self):
        bars = close_series([120, 115, 110, 100, 110, 110, 105, 110, 110, 110, 90], {6: 'doji'})
        future = Level('future', 1, 2, START + timedelta(days=len(bars)), START + timedelta(days=30))
        full = analyze(bars, (), C)
        self.assertEqual(full, analyze(bars, (future,), C))
        for k in range(1, len(bars) + 1):
            self.assertEqual(full[:k], analyze(bars[:k], (), C))

    def test_recovery_config_rejects_invalid_values(self):
        for change in ({'regime_ease_bars': 0}, {'regime_ease_bars': True},
                       {'regime_ease_drop_per_bar': 0}, {'regime_ease_drop_per_bar': float('nan')},
                       {'regime_ease_drop_per_bar': C.min_drop_per_bar}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(C, **change)

    def test_historical_comparison_projects_only_legacy_config_fields(self):
        # 구버전 소스는 Git에서 읽기만 한다. 엔진 사본이나 DB를 만들지 않는다.
        from run_audit import load_v01
        old, source_hash = load_v01(close_series([100, 100, 95]), C)
        self.assertEqual(len(old), 3)
        self.assertEqual(len(source_hash), 64)
        self.assertIsNone(old[-1].recent_speed)


if __name__ == '__main__':
    unittest.main()
