"""시장 3상태와 서로 독립인 두 종료 규칙을 합성 마감 일봉으로 검사한다."""
import math
import unittest
from dataclasses import replace
from datetime import date, timedelta

from rapid_drop import Bar, Level, analyze
from test_rapid_drop import C

START = date(2022, 1, 1)


def close_series(closes, shapes=None):
    shapes = shapes or {}
    return [Bar(START+timedelta(days=i), p, p+.5, p-.5, p, 100, shapes.get(i))
            for i, p in enumerate(closes)]


class TestRegime(unittest.TestCase):
    def test_recent_speed_is_available_before_previous_speed(self):
        rows = analyze(close_series([100, 100, 95]), (), C)
        self.assertEqual([r.regime_phase for r in rows[:2]], ['insufficient', 'insufficient'])
        self.assertAlmostEqual(rows[2].recent_speed, math.log(95/100)/2)
        self.assertIsNone(rows[2].previous_speed)
        self.assertIsNone(rows[2].accelerating_down)
        self.assertEqual(rows[2].regime_phase, 'sharp_drop')
        self.assertTrue(rows[2].regime_started_today)
        self.assertEqual(rows[2].regime_recovery_anchor, 100)

    def test_up_then_down_to_the_same_two_bar_close_is_not_a_drop(self):
        row = analyze(close_series([100, 107, 100]), (), C)[-1]
        self.assertEqual(row.recent_speed, 0)
        self.assertEqual(row.regime_phase, 'normal')
        self.assertFalse(row.strong_down)

    def test_steady_strong_decline_needs_no_additional_acceleration(self):
        rows = analyze(close_series([100*.94**i for i in range(9)], {7:'doji'}), (), C)
        episode = rows[2].regime_id
        for row in rows[2:]:
            self.assertEqual(row.regime_phase, 'sharp_drop')
            self.assertEqual(row.regime_id, episode)
            self.assertEqual(row.regime_last_sharp_on, row.day)
            self.assertEqual(row.regime_bars_since_last_sharp, 0)
            self.assertEqual(row.regime_speed_votes, 0)
            self.assertEqual(row.regime_price_recovery_streak, 0)
        self.assertTrue(all(row.accelerating_down is False for row in rows[4:]))
        self.assertIn('reversal_observed', rows[7].event_kinds)

    def test_post_drop_starts_on_first_non_strong_day(self):
        rows = analyze(close_series([100, 99, 94, 96]), (), C)
        self.assertEqual(rows[2].regime_phase, 'sharp_drop')
        self.assertEqual(rows[3].regime_phase, 'post_drop')
        self.assertEqual(rows[3].regime_id, rows[2].regime_id)
        self.assertEqual(rows[3].regime_bars_since_last_sharp, 1)
        self.assertFalse(rows[3].regime_ended_today)

    def test_price_recovery_can_end_before_the_speed_minimum_duration(self):
        rows = analyze(close_series([100, 99, 94, 100, 101]), (), C)
        self.assertEqual(rows[3].regime_price_recovery_streak, 1)
        self.assertEqual(rows[3].regime_phase, 'post_drop')
        self.assertEqual(rows[4].regime_phase, 'normal')
        self.assertEqual(rows[4].regime_end_reason, 'price_recovered')
        self.assertEqual(rows[4].regime_bars_since_last_sharp, 2)
        self.assertTrue(rows[4].regime_ended_today)

    def test_price_recovery_streak_resets_below_its_anchor(self):
        cfg = replace(C, regime_min_post_drop_bars=100)
        rows = analyze(close_series([100, 99, 94, 100, 99, 100, 100]), (), cfg)
        self.assertEqual([r.regime_price_recovery_streak for r in rows[3:]], [1,0,1,2])
        self.assertEqual(rows[-1].regime_end_reason, 'price_recovered')

    def test_each_strong_day_updates_h_and_a_and_clears_recovery(self):
        rows = analyze(close_series([100, 99, 94, 94, 94, 94, 94]), (), C)
        self.assertEqual(rows[3].regime_last_sharp_on, rows[3].day)
        self.assertEqual(rows[3].regime_recovery_anchor, 99)
        self.assertEqual([r.regime_bars_since_last_sharp for r in rows[4:]], [1,2,3])
        self.assertEqual([r.regime_speed_votes for r in rows[4:]], [1,2,3])
        self.assertEqual([r.regime_phase for r in rows[4:]], ['post_drop','post_drop','normal'])
        self.assertEqual(rows[-1].regime_end_reason, 'speed_normalized')

    def test_closing_new_lows_do_not_prevent_speed_normalization(self):
        rows = analyze(close_series([100,99,94,94,93.7,93.4,93.1]), (), C)
        self.assertEqual(rows[-1].regime_phase, 'normal')
        self.assertEqual(rows[-1].regime_end_reason, 'speed_normalized')
        self.assertFalse(rows[-1].regime_no_new_closing_low)
        self.assertEqual(rows[-1].regime_lowest_close, 93.1)

    def test_two_of_three_speed_votes_also_requires_today_to_be_good(self):
        closes = [100,99,94]
        for speed in (-.006,-.007,-.01281,-.005):
            closes.append(closes[-2]*math.exp(2*speed))
        rows = analyze(close_series(closes), (), C)
        self.assertEqual(rows[5].regime_speed_votes, 2)
        self.assertLess(rows[5].recent_speed, -.01)
        self.assertEqual(rows[5].regime_phase, 'post_drop')
        self.assertEqual(rows[6].regime_speed_votes, 2)
        self.assertEqual(rows[6].regime_phase, 'normal')
        self.assertEqual(rows[6].regime_end_reason, 'speed_normalized')

    def test_post_drop_reaggravation_keeps_episode_but_resets_recovery(self):
        rows = analyze(close_series([100,99,94,100,90]), (), C)
        self.assertEqual(rows[3].regime_price_recovery_streak, 1)
        self.assertEqual(rows[3].regime_speed_votes, 1)
        row = rows[4]
        self.assertEqual(row.regime_phase, 'sharp_drop')
        self.assertEqual(row.regime_id, rows[2].regime_id)
        self.assertTrue(row.regime_reaggravated_today)
        self.assertFalse(row.regime_started_today)
        self.assertEqual(row.regime_recovery_anchor, 94)
        self.assertEqual(row.regime_price_recovery_streak, 0)
        self.assertEqual(row.regime_speed_votes, 0)

    def test_new_strong_drop_after_normal_starts_a_new_episode(self):
        rows = analyze(close_series([100,99,94,100,101,80]), (), C)
        self.assertTrue(rows[4].regime_ended_today)
        self.assertTrue(rows[5].regime_started_today)
        self.assertFalse(rows[5].regime_reaggravated_today)
        self.assertNotEqual(rows[5].regime_id, rows[2].regime_id)

    def test_normal_days_do_not_keep_growing_recovery_counters(self):
        rows = analyze(close_series([100,99,94,100,101,102]), (), C)
        self.assertEqual(rows[-1].regime_phase, 'normal')
        self.assertIsNone(rows[-1].regime_bars_since_last_sharp)
        self.assertEqual(rows[-1].regime_speed_votes, 0)
        self.assertEqual(rows[-1].regime_price_recovery_streak, 0)
        self.assertFalse(rows[-1].regime_ended_today)

    def test_wick_low_does_not_affect_either_market_exit(self):
        bars = close_series([100,99,94,94,94,94,94])
        bars[-1] = replace(bars[-1], low=40, shape='hammer')
        row = analyze(bars, (), C)[-1]
        self.assertEqual(row.regime_phase, 'normal')
        self.assertEqual(row.regime_end_reason, 'speed_normalized')
        self.assertEqual(row.regime_lowest_close, 94)

    def test_pattern_observation_requires_market_warning_or_post_drop(self):
        normal = analyze(close_series([100,100,100], {2:'doji'}), (), C)[-1]
        sharp = analyze(close_series([100,99,94], {2:'doji'}), (), C)[-1]
        post = analyze(close_series([100,99,94,96], {3:'hammer'}), (), C)[-1]
        self.assertNotIn('reversal_observed', normal.event_kinds)
        self.assertIn('reversal_observed', sharp.event_kinds)
        self.assertIn('reversal_observed', post.event_kinds)

    def test_unknown_support_and_known_no_reaction_are_distinct(self):
        bars = close_series([100,99,94], {2:'doji'})
        far = Level('far', 10, 11, START, START+timedelta(days=20))
        unknown = next(e for e in analyze(bars, (), C)[-1].events if e.kind == 'reversal_observed')
        known = next(e for e in analyze(bars, (far,), C)[-1].events if e.kind == 'reversal_observed')
        self.assertEqual(unknown.support_source, 'unconfirmed')
        self.assertEqual(known.support_source, 'known_no_reaction')
        self.assertEqual(known.evaluated_support_ids, ('far',))

    def test_future_candles_and_future_support_leave_past_state_unchanged(self):
        bars = close_series([100,99,94,96,90,95,96,97], {3:'doji'})
        future = Level('future', 1, 2, START+timedelta(days=len(bars)), START+timedelta(days=30))
        full = analyze(bars, (), C)
        self.assertEqual(full, analyze(bars, (future,), C))
        for k in range(1,len(bars)+1):
            self.assertEqual(full[:k], analyze(bars[:k], (), C))

    def test_invalid_market_config_is_rejected(self):
        for kwargs in ({'regime_ease_bars':0}, {'regime_speed_votes':4},
                       {'regime_price_recovery_bars':True}, {'regime_min_post_drop_bars':0},
                       {'regime_ease_drop_per_bar':float('nan')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(C, **kwargs)

    def test_historical_comparison_filters_current_config_fields(self):
        from run_audit import load_v01
        old, source_hash = load_v01(close_series([100,100,95]), C)
        self.assertEqual(len(old), 3)
        self.assertEqual(len(source_hash),64)
        self.assertIsNone(old[-1].recent_speed)


if __name__ == '__main__':
    unittest.main()
