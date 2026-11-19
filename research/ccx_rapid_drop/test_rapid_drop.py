"""합성 일봉으로 판정 분기를 검사한다. 실제 사용자의 캡처나 수익률 표본이 아니다."""
import csv
import unittest
from pathlib import Path
from dataclasses import replace
from datetime import date, timedelta
from rapid_drop import Bar, Config, Level, analyze

START = date(2022, 1, 1)
# 모든 수치는 이 테스트를 재현하기 위한 값. 운용 추천값이 아니다.
C = Config(2, .02, .01, 3, 3, 2, .04, .03, .01, 8)
Z = Level('lower', 96, 98, START, START + timedelta(days=30))


def series(*extra):
    data = [(108,109,107,108,100,None), (108,109,106,107,100,None),
            (107,108,105,106,100,None), (106,107,101,102,100,None),
            (102,103,96,97,100,None), *extra]
    return [Bar(START+timedelta(days=i),*row) for i,row in enumerate(data)]


DOJI = (97,99,94,97,300,'doji')
BOUNCE = (97,103,96,102,80,None)
RETEST = (99,100,93,97.5,90,'hammer')
RED = (97,98,89,91,350,None)


class TestRapidDrop(unittest.TestCase):
    def obs(self,*rows,levels=(Z,),cfg=C):
        return analyze(series(*rows),levels,cfg)

    def test_accel_and_warmup(self):
        rows=self.obs(); self.assertIsNone(rows[3].accelerating_down)
        self.assertTrue(rows[4].accelerating_down)
        self.assertLess(rows[4].recent_speed, rows[4].previous_speed)

    def test_steady_steep_is_not_acceleration(self):
        raw=series(); rows=[]
        for i,b in enumerate(raw):
            price=100*.94**i
            rows.append(replace(b,open=price,close=price,high=price,low=price))
        self.assertFalse(analyze(rows,(),C)[-1].accelerating_down)

    def test_direct_doji(self):
        x=self.obs(DOJI)[-1]; self.assertEqual(x.events,('direct_doji_candidate',)); self.assertEqual(x.volume_ratio,3)

    def test_broken_old_support_not_buy(self):
        old=replace(Z,bottom=100,top=101)
        x=self.obs((97,101,95,97,400,'inverted_hammer'),levels=(old,))[-1]
        self.assertEqual(x.events,('shape_observed_only',)); self.assertEqual(x.unrecovered_levels,('lower',))

    def test_lower_new_zone_not_double_bottom(self):
        old=replace(Z,key='old',bottom=100,top=101)
        x=self.obs(DOJI,levels=(old,Z))[-1]; self.assertEqual(x.events,('direct_doji_candidate',))
        self.assertEqual(x.reaction_levels,('lower',)); self.assertIn('old',x.unrecovered_levels)

    def test_big_red_not_bottom_foresight(self):
        res=self.obs(RED,(91,96,90,95,100,None),(93,94,88,91.5,100,'doji'),levels=())
        self.assertEqual(res[-3].events,('volume_red_watch_only',))
        self.assertEqual(res[-2].events,('bounce_observed',))
        self.assertIn('retest_preferred',res[-1].events)

    def test_wick_and_close_recovery(self):
        res=self.obs(DOJI,BOUNCE,RETEST); self.assertEqual(res[-1].events,('retest_preferred','first_wick_undercut_recovered'))
        self.assertEqual(res[-1].anchor_day,res[-3].day)

    def test_retest_without_shape_not_erased(self):
        res=self.obs(DOJI,BOUNCE,(99,100,96,97,100,None)); self.assertEqual(res[-1].events,('retest_observed',))

    def test_close_break_cancels(self):
        x=self.obs(DOJI,BOUNCE,(99,100,90,92,90,None))[-1]; self.assertIn('anchor_lost_on_close',x.events)
        self.assertNotIn('retest_preferred',x.events)

    def test_no_same_bar_bounce_and_retest(self):
        x=self.obs(DOJI,(97,104,93,103,100,'hammer'))[-1]; self.assertEqual(x.events,('bounce_observed',))

    def test_no_retest_without_bounce(self):
        x=self.obs(DOJI,(97,99,94,97,100,'doji'))[-1]; self.assertFalse(x.events)

    def test_later_drawn_or_expired_zone(self):
        for z in [replace(Z,known_from=START+timedelta(days=6)),replace(Z,through=START+timedelta(days=4))]:
            x=self.obs(DOJI,levels=(z,))[-1]; self.assertNotIn('direct_doji_candidate',x.events)

    def test_anchor_expires(self):
        x=self.obs(DOJI,BOUNCE,RETEST,cfg=replace(C,max_age=1))[-1]; self.assertIn('anchor_expired',x.events)

    def test_future_bars_do_not_change_history(self):
        bars=series(DOJI,BOUNCE,RETEST); full=analyze(bars,(Z,),C)
        for k in range(1,len(bars)+1): self.assertEqual(full[:k],analyze(bars[:k],(Z,),C))

    def test_no_zero_volume_division(self):
        bars=[replace(b,volume=0) for b in series(DOJI)]
        obs=analyze(bars,(Z,),C)[-1]; self.assertIsNone(obs.volume_ratio); self.assertNotIn('direct_doji_candidate',obs.events)

    def test_reclaim_from_below_is_not_support_test(self):
        old = replace(Z, bottom=100, top=100)
        res = self.obs((97,103,96,101,400,'doji'),levels=(old,))[-1]
        self.assertEqual(res.reaction_levels,()); self.assertNotIn('direct_doji_candidate',res.events)

    def test_unshaped_retest_can_later_show_preferred_shape(self):
        x=self.obs(DOJI,BOUNCE,(99,100,96,97,100,None),RETEST)
        self.assertIn('retest_observed',x[-2].events); self.assertIn('retest_preferred',x[-1].events)

    def test_fixture_excerpt_speed_only(self):
        # 실데이터 일부의 수치 스모크 테스트. 지지선·캔들 라벨은 추측하지 않는다.
        with Path(__file__).with_name('fixture_excerpt.csv').open() as f:
            bars=[Bar(date.fromisoformat(r['date']), *(float(r[k]) for k in ('open','high','low','close','volume'))) for r in csv.DictReader(f)]
        x=analyze(bars,(),C)
        self.assertEqual(len(x),8); self.assertTrue(x[4].accelerating_down)
        self.assertLess(x[4].recent_speed,x[4].previous_speed)
        self.assertFalse(any('direct_doji_candidate' in o.events for o in x))

    def test_bad_bars_and_config(self):
        for bars in (series()[::-1],series()[:2]+series()[3:],[replace(series()[0],low=float('nan'))]):
            with self.assertRaises(ValueError): analyze(bars,(),C)
        with self.assertRaises(ValueError): replace(C,tolerance=C.rebound)


if __name__ == '__main__': unittest.main()
