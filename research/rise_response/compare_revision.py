"""PR #2 최초 커밋과 현재 엔진을 각각 실행해 동일한 고정 일봉의 판정을 비교한다."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from validation import ROOT, golden_support, isolated, rise_response

BASE = '8d0ee31ff011a605c3297bb2d15ec517cb151373'


def old_timeline():
    # 당시 구현과 입력만 새 디렉터리에 풀어 독립 프로세스에서 실행한다.
    # 현재 모듈 캐시, 개인 저장 경로, 작업 트리에 영향을 주지 않는다.
    paths = ['backend/app', 'backend/tests/fixtures', 'backend/tests/golden_support.py',
             'research/rise_response/validation.py']
    with TemporaryDirectory(prefix='ccx-old-rise-') as name:
        work = Path(name)
        archive = work / 'baseline.zip'
        subprocess.run(['git', 'archive', '--format=zip', '-o', str(archive), BASE, *paths],
                       cwd=ROOT, check=True)
        with ZipFile(archive) as reader:
            reader.extractall(work)
        code = """
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path('research/rise_response').resolve()))
from validation import isolated, rise_response
with isolated('fixed') as frame:
    rows = rise_response.build_timeline(frame)
    Path('old.json').write_text(json.dumps(rows), encoding='utf-8')
"""
        subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=work, check=True)
        fixture = golden_support.DAILY_FIXTURE.relative_to(ROOT)
        # Windows 체크아웃과 Git 객체의 줄바꿈만 정규화해 입력 전체가 같은지 확인한다.
        assert (work / fixture).read_text(encoding='utf-8') == golden_support.DAILY_FIXTURE.read_text(encoding='utf-8')
        return json.loads((work / 'old.json').read_text(encoding='utf-8'))


def durations(rows):
    """확정일을 1일째로 계산한다. 표본 마지막 날 열린 관찰은 따로 집계한다."""
    periods = {}
    for row in rows:
        for e in row['events']:
            if e['kind'] in rise_response.ISSUED:
                periods[e['id']] = dict(kind=e['kind'], source=e.get('source', '고점 재시도'),
                                         start=e['date'], end=None)
                continue
            ref = e.get('related') or e.get('related_id')
            if ref in periods and (e['kind'] == 'high_watch_released'
                                   or e.get('lifecycle') in ('released', 'invalidated')):
                periods[ref]['end'] = e['date']
    groups = defaultdict(list)
    for record in periods.values():
        last = date.fromisoformat(record['end'] or rows[-1]['date'])
        record['days'] = (last - date.fromisoformat(record['start'])).days + 1
        groups[record['kind']].append(record)
    out = {}
    for kind, records in groups.items():
        closed = [r for r in records if r['end']]
        opened = [r for r in records if not r['end']]
        out[kind] = dict(closed=len(closed), open=len(opened),
                         median_closed_days=median(r['days'] for r in closed) if closed else None,
                         longest_closed=max(closed, key=lambda r: r['days'], default=None),
                         longest_open=max(opened, key=lambda r: r['days'], default=None))
    return out


def counts(rows):
    return dict(sorted(Counter(e['kind'] for row in rows for e in row['events']).items()))


def high_references(events):
    return sorted((e['first_peak_day'], e['retry_day']) for e in events if e['kind'] == 'high_retry_failed')


def compare(before, after, frame):
    assert [r['date'] for r in before] == [r['date'] for r in after]
    groups = defaultdict(list)
    event_changes = defaultdict(lambda: dict(added=[], removed=[]))
    high_comparison = defaultdict(list)
    dates = [r['date'] for r in after]
    indices = {day: i for i, day in enumerate(dates)}
    latest_surge = -1
    for i, (old, row) in enumerate(zip(before, after, strict=True)):
        day = dates[i]
        details = row['details']['market']
        old_events = {e['id']: e for e in old['events']}
        events = {e['id']: e for e in row['events']}
        former, current = high_references(old_events.values()), high_references(events.values())
        if former and current:
            key = 'same_dates_and_references' if former == current else 'same_day_changed_reference'
            high_comparison[key].append(dict(date=day, old=former, new=current))
        elif former or current:
            high_comparison['new_day' if current else 'removed_day'].append(day)
        for eid in sorted(events.keys() - old_events.keys()):
            event_changes[events[eid]['kind']]['added'].append(day)
        for eid in sorted(old_events.keys() - events.keys()):
            event_changes[old_events[eid]['kind']]['removed'].append(day)
        if details['surge_sources']:
            latest_surge = i
        flags = []
        for e in events.values():
            if e['kind'] == 'high_retry_failed' and e['id'] not in old_events:
                # 첫 고점 직전의 최장 급등 창도 포함한다. 단순히 발행일에 급등이 없다는 뜻이 아니다.
                if latest_surge < max(0, indices[e['first_peak_day']] - 4):
                    flags.append('new_high_failure_without_surge')
            if e['kind'] == 'support_retest_short':
                flags.append('new_short_candidate')
        if (details['ema_regime'], details['price_direction']) in (('bearish', 'up'), ('bullish', 'down')):
            flags.append('opposed_ema_structure')
        if row['long_exit'] != '해당 없음':
            if row['short_signal'] == '해당 없음':
                flags.append('long_exit_only')
            if not any(e['kind'] in rise_response.ISSUED for e in events.values()):
                flags.append('long_exit_without_new_short')
        for flag in sorted(set(flags)):
            groups[flag].append(day)

    examples = {}
    for flag, found in groups.items():
        day = found[0]
        i = indices[day]
        row = after[i]
        m = row['details']['market']
        examples[flag] = dict(date=day, close=float(frame.close.iloc[i]), market=row['market'],
                              before_market=before[i]['market'], before_short=before[i]['short_signal'],
                              long_exit=row['long_exit'], short_signal=row['short_signal'],
                              ema_regime=m['ema_regime'], price_direction=m['price_direction'],
                              highs=m['swing_highs'], lows=m['swing_lows'], events=row['events'])
    return dict(base_commit=BASE, bars=len(after), first=dates[0], last=dates[-1],
                fixture_lf_sha256=sha256(golden_support.DAILY_FIXTURE.read_text(encoding='utf-8').encode()).hexdigest(),
                old_event_counts=counts(before), new_event_counts=counts(after), event_changes=dict(event_changes),
                old_duration=durations(before), new_duration=durations(after),
                high_watch_comparison=dict(high_comparison), category_dates=dict(groups), examples=examples)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = old_timeline()
    with isolated('fixed') as frame:
        report = compare(baseline, rise_response.build_timeline(frame), frame)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
