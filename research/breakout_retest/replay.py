"""고정 일봉과 합성 도형의 날짜별 판정·중복·미래 입력 불변성을 검사한다."""
from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

import pandas as pd

from validation import CASES, isolated, journal
from app.services import breakout_signals, rise_response


def _event(days, day, kind):
    matches = [e for e in days[day - 1]['events'] if e['type'] == kind]
    assert len(matches) == 1, (days[day - 1]['date'], kind, matches, days[day - 1]['events'])
    return matches[0]


def _long_days(rows):
    return [i for i, row in enumerate(rows, 1) if any(e['type'] == 'long_candidate' for e in row['events'])]


def _check_case(case, rows, rise):
    if case == 'fixed':
        assert len(rows) == 1762 and not any(r['active'] or r['events'] for r in rows)
    elif case == 'zone_hold':
        _event(rows, 2, 'breakout_up')
        candidate = _event(rows, 3, 'long_candidate')
        assert _long_days(rows) == [3] and candidate['id'] in [e['id'] for e in rows[3]['active']]
        assert candidate['id'] in _event(rows, 5, 'invalidated')['linked_ids']
    elif case == 'wick':
        _event(rows, 2, 'wick_sweep')
        assert not any(e['type'] in ('breakout_up', 'long_candidate', 'short_candidate') for r in rows for e in r['events'])
    elif case == 'zone_failure':
        _event(rows, 2, 'breakout_up')
        _event(rows, 3, 'breakout_caution')
        _event(rows, 4, 'breakout_failed')
        short = _event(rows, 5, 'short_candidate')
        original = [e for e in rise[4]['events'] if e['kind'] == 'support_retest_short']
        assert len(original) == 1 and short['id'] == original[0]['id']
        assert not _long_days(rows)
    elif case == 'support_recover':
        _event(rows, 3, 'breakdown_failed')
        assert _long_days(rows) == [4]
    elif case == 'slope_down':
        assert _event(rows, 3, 'breakout_up')['top'] == 102
        assert _event(rows, 4, 'long_candidate')['top'] == 100
    elif case == 'slope_up':
        exit_id = _event(rows, 3, 'long_exit')['id']
        assert exit_id in [e['id'] for e in rise[2]['events'] if e['kind'] == 'trendline_exit_long']
        assert _event(rows, 4, 'breakdown_failed')['top'] == 101
        assert _event(rows, 5, 'long_candidate')['top'] == 102
    elif case == 'slope_short':
        _event(rows, 3, 'long_exit')
        candidate = _event(rows, 4, 'short_candidate')
        assert candidate['top'] == 101 and candidate['id'] in [e['id'] for e in rows[4]['active']]
        assert not _long_days(rows)
    elif case == 'version_lifecycle':
        _event(rows, 3, 'version_replaced')
        _event(rows, 6, 'version_ended')
        assert _long_days(rows) == [5, 9]
        first, second = [_event(rows, i, 'long_candidate') for i in (5, 9)]
        assert first['version_id'] != second['version_id'] and first['attempt_id'] != second['attempt_id']
    elif case == 'expiry':
        for day in (11, 23):
            _event(rows, day, 'expired')
        assert _long_days(rows) == [14]
    elif case in ('gentle', 'bear_rebound'):
        assert not any(r['details']['market']['surge_sources'] for r in rise)
        [index] = _long_days(rows)
        row = rows[index - 1]
        expected = 'bullish' if case == 'gentle' else 'bearish'
        assert row['market_regime'] == expected
        assert ('정배열' if case == 'gentle' else '역배열 속 반등') in row['market_context']


def _prefixes(frame, full, lengths):
    for length in lengths:
        truncated = frame.iloc[:length]
        versions = journal.load_drawing_versions(as_of=full[length - 1]['date'])['versions']
        assert breakout_signals.build_timeline(truncated, versions) == full[:length], length
    return len(lengths)


def _fixed_prefix_worker(args):
    start, workers = args
    # 프로세스별로 매매·도형 DB, 이력과 lock도 별도 임시 경로에 둔다.
    with isolated('fixed') as frame:
        full = breakout_signals.build_timeline(frame)
        return _prefixes(frame, full, range(start, len(frame) + 1, workers))


def _future_check(frame, full):
    # 나중에 처음 기록한 옛 좌표와 큰 가격 변화가 있는 미래 4봉을 함께 추가한다.
    prices = ('open', 'high', 'low', 'close')
    future = frame.iloc[[-1] * 4].reset_index(drop=True).astype({field: float for field in prices})
    for i, factor in enumerate((1.1, .9, 1.04, 1.02)):
        for field in ('open_time', 'close_time'):
            future.loc[i, field] += pd.Timedelta(days=i + 1)
        for field in prices:
            future.loc[i, field] *= factor
    late = dict(id=888, line_type='trend', time1=full[0]['date'], price1=100,
                time2=full[1]['date'], price2=102)
    journal.record_snapshot([late], observed_at=future.open_time.iloc[0].to_pydatetime())
    versions = journal.load_drawing_versions(as_of=future.open_time.iloc[-1].date())['versions']
    expanded = pd.concat([frame, future], ignore_index=True)
    assert breakout_signals.build_timeline(expanded, versions)[:len(full)] == full
    return len(future)


def run_case(case, *, workers=1):
    with isolated(case) as frame:
        end = frame.open_time.iloc[-1].date()
        history = journal.load_drawing_versions(as_of=end)
        versions = history['versions']
        rows = breakout_signals.build_timeline(frame, versions)
        rise = rise_response.build_timeline(frame, versions)
        assert [r['date'] for r in rows] == [t.date().isoformat() for t in frame.open_time]
        assert [r['market_label'] for r in rows] == [r['market'] for r in rise]
        _check_case(case, rows, rise)
        events = [e for r in rows for e in r['events']]
        duplicates = len(events) - len({e['id'] for e in events})
        candidates = [e for e in events if e['type'] in ('long_candidate', 'short_candidate')]
        repeated = len(candidates) - len({(e['attempt_id'], e['type']) for e in candidates})
        assert duplicates == repeated == 0
        for r in rows:
            assert all(e['confirmed_date'] == r['date'] for e in r['events'])
        if case == 'fixed' and workers > 1:
            with ProcessPoolExecutor(workers) as pool:
                prefixes = sum(pool.map(_fixed_prefix_worker, ((i + 1, workers) for i in range(workers))))
        else:
            prefixes = _prefixes(frame, rows, range(1, len(rows) + 1))
        future = _future_check(frame, rows)
        summaries = []
        for row, bar in zip(rows, frame.itertuples(index=False), strict=True):
            if row['events']:
                summaries.append(dict(date=row['date'], close=bar.close,
                    events=[dict(type=e['type'], label=e['label'], bottom=e['bottom'], top=e['top'])
                            for e in row['events']]))
        return dict(source='고정 BTCUSDT · 당시 도형 이력 없음' if case == 'fixed' else '합성 데이터 · 검증용',
                    bars=len(rows), first=rows[0]['date'], last=rows[-1]['date'],
                    history_status=history['status'], versions=len(versions), prefix_checks=prefixes,
                    future_bars=future, future_drawing_count=1, duplicate_ids=duplicates,
                    repeated_candidates=repeated, events=dict(Counter(e['type'] for e in events)),
                    days_with_events=summaries)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--workers', default=1, type=int, help='고정 데이터 접두 검사에 쓸 독립 프로세스 수')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers는 양수여야 합니다.')
    results = {}
    for case in args.case or CASES:
        results[case] = run_case(case, workers=args.workers)
        print(case, results[case]['prefix_checks'], flush=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
