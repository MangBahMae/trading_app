"""고정 일봉과 당시 도형이 명시된 합성 일봉을 독립적으로 재생한다."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import timedelta
import json
from pathlib import Path

import pandas as pd

from validation import CASES, dashboard, isolated, journal, rise_response


def run_case(case):
    with isolated(case) as frame:
        days = [stamp.date().isoformat() for stamp in frame.open_time]
        versions = journal.load_drawing_versions(as_of=days[-1])['versions']
        timeline = rise_response.build_timeline(frame, versions)
        assert [row['date'] for row in timeline] == days
        legacy = dashboard.get_dashboard_data()['signals']
        events = defaultdict(list)
        identifiers = []
        comparisons = []
        contrasts = Counter()
        surge_days = Counter()
        watch_attempts = []
        for row in timeline:
            day = row['date']
            kinds = {e['kind'] for e in row['events']}
            surge_days.update(row['details']['market']['surge_sources'])
            for event in row['events']:
                assert event['date'] == day
                events[event['kind']].append(day)
                identifiers.append(event['id'])
                if event['kind'] == 'high_retry_failed':
                    watch_attempts.append((event['first_peak_day'], event['retry_day']))
            shorts = [s['text'] for s in legacy.get(day, []) if s['direction'] == 'short']
            issued = bool(kinds & {'high_retry_failed', 'support_retest_short'})
            if shorts:
                contrasts['legacy_short_days'] += 1
                if not issued:
                    contrasts['legacy_short_without_new_watch_or_candidate'] += 1
            if issued and not shorts:
                contrasts['new_watch_or_candidate_without_legacy_short'] += 1
            if (row['long_exit'] != '해당 없음' or 'high_retry_failed' in kinds
                    or (shorts and row['market'] == '상승 추세 유지' and row['short_signal'] == '해당 없음')):
                comparisons.append(dict(date=day, existing_shorts=shorts, market=row['market'],
                                        long_exit=row['long_exit'], short_signal=row['short_signal']))
        duplicate_ids = len(identifiers) - len(set(identifiers))
        assert duplicate_ids == 0
        repeat_watches = len(watch_attempts) - len(set(watch_attempts))
        assert repeat_watches == 0

        # 마지막 봉에서부터 과거로 자른 값과, 그날까지의 일봉·도형만 읽은 재생을 모두 대조한다.
        lengths = range(1, len(frame) + 1)
        for n in lengths:
            then = journal.load_drawing_versions(as_of=days[n - 1])['versions']
            assert rise_response.build_timeline(frame.iloc[:n], then) == timeline[:n], (case, n)

        # 다른 가격 경로 및 뒤늦게 등록한 옛 좌표가 과거의 어떤 날짜도 바꾸지 않아야 한다.
        future = frame.iloc[[-1] * 12].reset_index(drop=True).astype(
            {col: float for col in ('open', 'high', 'low', 'close')})
        for i in range(len(future)):
            for col in ('open_time', 'close_time'):
                if col in future:
                    future.loc[i, col] += timedelta(days=i + 1)
            for col in ('open', 'high', 'low', 'close'):
                future.loc[i, col] *= (1.04 if i % 2 else 0.93)
        after = frame.open_time.iloc[-1] + pd.Timedelta(days=1)
        late = dict(id=9999, line_type='trend', time1=days[0], time2=days[1],
                    price1=100, price2=102)
        journal.record_snapshot([late], observed_at=after.to_pydatetime())
        expanded = pd.concat([frame, future], ignore_index=True)
        later_versions = journal.load_drawing_versions(as_of=future.open_time.iloc[-1].date())['versions']
        assert rise_response.build_timeline(expanded, later_versions)[:len(frame)] == timeline
        watch = next((r for r in comparisons if '고점 재시도 실패' in r['short_signal']), None)
        legacy_only = next((r for r in comparisons if r['existing_shorts'] and r['short_signal'] == '해당 없음'), None)
        return dict(bars=len(frame), first=days[0], last=days[-1], prefix_checks=len(lengths),
                    future_bars=len(future), duplicate_event_ids=duplicate_ids,
                    repeated_peak_attempts=repeat_watches, legacy_comparison=dict(contrasts),
                    surge_source_days=dict(surge_days),
                    markets=dict(Counter(row['market'] for row in timeline)),
                    events={kind: dict(count=len(dates), dates=dates) for kind, dates in sorted(events.items())},
                    legacy_examples=([r for r in (watch, legacy_only) if r] if case == 'fixed' else comparisons),
                    days=None if case == 'fixed' else [
                        {key: row[key] for key in ('date', 'market', 'long_exit', 'short_signal')}
                        for row in timeline])


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {case: run_case(case) for case in CASES}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
