"""검토에서 추가한 재현 검사. 현행 동작의 통과가 전략 타당성을 뜻하지 않는다."""
import sys
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend/app/services'))
from candle_patterns import compute_candle_shape
from rapid_drop import Level, analyze
from test_rapid_drop import C, Z, START, DOJI, BOUNCE, RED, series


def existing_shapes(bars):
    """모양을 새로 정의하지 않고 운영 쪽 기존 모듈을 읽기 전용으로 사용한다."""
    frame = pd.DataFrame([{
        'open_time': pd.Timestamp(b.day, tz='UTC'), 'open': b.open,
        'high': b.high, 'low': b.low, 'close': b.close, 'volume': b.volume,
    } for b in bars])
    shapes = compute_candle_shape(frame)['shape'].tolist()
    return [replace(b, shape=s) for b, s in zip(bars, shapes)]


class TestReview(unittest.TestCase):
    def test_synthetic_support_path_with_existing_shapes(self):
        bars = existing_shapes(series(DOJI, BOUNCE, (98, 98.2, 93, 97.5, 90, None)))
        rows = analyze(bars, (Z,), C)
        self.assertEqual(bars[5].shape, 'doji')
        self.assertEqual(bars[7].shape, 'hammer')
        self.assertEqual(rows[5].events, ('direct_doji_candidate',))
        self.assertEqual(rows[6].events, ('bounce_observed',))
        self.assertEqual(rows[7].events, ('retest_preferred', 'first_wick_undercut_recovered'))

    def test_empty_levels_cannot_validate_direct_doji(self):
        rows = analyze(existing_shapes(series(DOJI, BOUNCE)), (), C)
        self.assertFalse(any('direct_doji_candidate' in r.events for r in rows))
        self.assertFalse(any(r.reaction_levels for r in rows))

    def test_far_above_reference_close_still_preferred_current_behavior(self):
        # README의 '허용 폭 이내의 마감'보다 넓은 현행 조건을 재현한다.
        bars = existing_shapes(series(DOJI, BOUNCE, (115, 120.5, 96, 120, 90, None)))
        rows = analyze(bars, (Z,), C)
        self.assertEqual(bars[-1].shape, 'hammer')
        self.assertGreater(bars[-1].close, bars[5].close * (1 + C.tolerance))
        self.assertIn('retest_preferred', rows[-1].events)

    def test_red_priority_over_support_doji_current_behavior(self):
        bars = existing_shapes(series((102, 110, 73, 97, 350, None)))
        row = analyze(bars, (Z,), C)[-1]
        self.assertEqual(bars[-1].shape, 'doji')
        self.assertTrue(row.reaction_levels)
        self.assertGreaterEqual((102 - 97) / 102, C.large_red_body)
        self.assertEqual(row.events, ('volume_red_watch_only',))

    def test_live_red_anchor_suppresses_new_doji_current_behavior(self):
        level = replace(Z, bottom=90, top=92)
        bars = existing_shapes(series(RED, (91, 93, 87, 91, 1000, None)))
        rows = analyze(bars, (level,), C)
        self.assertEqual(rows[-2].events, ('volume_red_watch_only',))
        self.assertEqual(bars[-1].shape, 'doji')
        self.assertTrue(rows[-1].reaction_levels)
        self.assertGreaterEqual(rows[-1].volume_ratio, C.volume_multiple)
        self.assertEqual(rows[-1].events, ())
        self.assertEqual(rows[-1].anchor_day, bars[-2].day)

    def test_old_and_new_anchor_share_one_day_field_current_behavior(self):
        lower = Level('new_lower', 90, 92, START + timedelta(days=6), START + timedelta(days=20))
        bars = existing_shapes(series(DOJI, (91, 93, 88, 91, 1000, None)))
        rows = analyze(bars, (Z, lower), C)
        self.assertEqual(rows[-1].events, ('anchor_lost_on_close', 'direct_doji_candidate'))
        self.assertEqual(rows[-1].anchor_day, bars[-1].day)
        self.assertNotEqual(rows[-1].anchor_day, bars[-2].day)

    def test_future_levels_do_not_change_past(self):
        bars = existing_shapes(series(DOJI, BOUNCE, (98, 98.2, 93, 97.5, 90, None)))
        future = replace(Z, key='future', known_from=START + timedelta(days=8))
        self.assertEqual(analyze(bars, (Z,), C), analyze(bars, (Z, future), C))

    def test_support_known_and_through_are_inclusive(self):
        bars = existing_shapes(series(DOJI))
        level = replace(Z, known_from=bars[-1].day, through=bars[-1].day)
        self.assertIn('direct_doji_candidate', analyze(bars, (level,), C)[-1].events)

    def test_expired_broken_level_disappears(self):
        bars = series()
        level = replace(Z, bottom=110, top=111, through=START + timedelta(days=3))
        rows = analyze(bars, (level,), C)
        self.assertEqual(rows[3].unrecovered_levels, ('lower',))
        self.assertEqual(rows[4].unrecovered_levels, ())

    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            analyze(series(DOJI), (Z, Z), C)


if __name__ == '__main__':
    unittest.main()
