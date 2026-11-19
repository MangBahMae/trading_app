"""v0.2 전체 실행·이전 커밋 비교·시간 불변성·보존 검사. 연구 폴더만 기록한다."""
import csv
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from types import ModuleType

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / 'results_v02'
BASE = '38d3f59685e577da2991323d97b448e72b66dd54'
FIXTURE = REPO / 'backend/tests/fixtures/BTCUSDT_1d_2022-01-01_2026-10-28.csv'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_value(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False, allow_nan=False))


def write_json(name, value):
    (RESULTS / name).write_text(json.dumps(json_value(value), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def git(*args):
    return subprocess.run(['git', *args], cwd=REPO, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout


def logged(name, args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', *args], cwd=HERE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (RESULTS / name).write_bytes(result.stdout + result.stderr)
    print(f'{name}: exit={result.returncode}', flush=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result


def load_v01(bars, cfg):
    # Git의 과거 버전은 비교할 때만 메모리에 읽는다. 중복 엔진 파일은 만들지 않는다.
    source = git('show', f'{BASE}:research/ccx_rapid_drop/rapid_drop.py')
    module = ModuleType('_comparison_v01')
    sys.modules[module.__name__] = module
    exec(compile(source, f'git:{BASE}:rapid_drop.py', 'exec'), module.__dict__)
    old_bars = [module.Bar(**asdict(b)) for b in bars]
    return module.analyze(old_bars, (), module.Config(**asdict(cfg))), hashlib.sha256(source).hexdigest()


def compare_events(old, current):
    facts = [e for row in current for e in row.events]
    matched = set()
    changes = []
    category_map = {'shape_observed_only': 'reversal_observed', 'retest_preferred': 'retest_observed',
                    'first_wick_undercut_recovered': 'retest_observed', 'wick_not_recovered': 'retest_observed'}
    for row in old:
        for kind in row.events:
            target = category_map.get(kind, kind)
            choices = [e for e in facts if e.day == row.day and e.kind == target
                       and (kind == 'shape_observed_only' or e.anchor_day == row.anchor_day)]
            if kind == 'first_wick_undercut_recovered':
                choices = [e for e in choices if e.first_wick_undercut and e.wick_recovered_on_close]
            elif kind == 'wick_not_recovered':
                choices = [e for e in choices if e.first_wick_undercut and not e.wick_recovered_on_close]
            new = choices[0] if choices else None
            status = 'removed' if new is None else 'reclassified' if target != kind else 'preserved'
            if new:
                matched.add(new.id)
            reasons = {
                'shape_observed_only': '지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경',
                'retest_preferred': '선호 진입 의미를 제거하고 모양·종가 위치·진입 미평가를 분리',
                'first_wick_undercut_recovered': '별도 사건을 같은 재시험 사건의 꼬리 하회·회복 속성으로 통합',
                'wick_not_recovered': '미회복도 재시험 사건의 속성으로 보존',
            }
            changes.append(dict(status=status, day=str(row.day), old_kind=kind,
                old_anchor_day=str(row.anchor_day) if row.anchor_day else None,
                new_kind=new.kind if new else None, new_id=new.id if new else None,
                new_anchor_day=str(new.anchor_day) if new else None,
                reason=reasons.get(kind, '기존 사실을 사건별 참조와 함께 유지') if new else '기준 수명과 사건 분리 변경에 따른 비교 대상 부재'))
    for e in facts:
        if e.id in matched:
            continue
        if e.kind == 'retest_observed':
            reason = ('종가 이탈일에도 재시험 접촉 사실을 보존' if e.close_location == 'below_reference_band'
                      else '반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음')
        elif e.kind in ('anchor_expired', 'anchor_lost_on_close'):
            reason = '반전 모양 재시험 이후에도 기준을 유지하여 수명 종료 기록'
        elif e.kind == 'reversal_observed':
            reason = '기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록'
        elif e.kind == 'volume_red_watch_only':
            reason = '기존 기준 추적 중에도 새 장대음봉 사실 기록'
        else:
            reason = 'v0.2의 독립적인 사실·상태 구분'
        changes.append(dict(status='added', day=str(e.day), old_kind=None, old_anchor_day=None,
                            new_kind=e.kind, new_id=e.id, new_anchor_day=str(e.anchor_day), reason=reason))
    statuses = Counter(x['status'] for x in changes)
    return dict(v01_occurrences=sum(len(r.events) for r in old), v02_occurrences=len(facts),
                counts={name: statuses[name] for name in ('preserved', 'reclassified', 'added', 'removed')},
                matched_v02_facts=len(matched),
                old_facts_merged_into_attributes=statuses['preserved'] + statuses['reclassified'] - len(matched),
                changes=changes)


def synthetic_cases():
    from test_rapid_drop import C, Z, START, DOJI, BOUNCE, RED, series
    samples = {'doji': DOJI, 'hammer': (97, 97.2, 93, 96.8, 300, None),
               'inverted_hammer': (97, 103, 96.8, 97.5, 300, None)}
    retests = {'doji': (97, 99, 94, 97, 90, None), 'hammer': (98, 98.2, 93, 97.5, 90, None),
               'inverted_hammer': (97, 103, 96.8, 97.5, 90, None)}
    cases = [(f'first_{name}', series(sample), (Z,)) for name, sample in samples.items()]
    cases += [(f'retest_{name}', series(DOJI, BOUNCE, sample), (Z,)) for name, sample in retests.items()]
    cases += [
        ('far_close', series(DOJI, BOUNCE, (115, 120.5, 96, 120, 90, None)), (Z,)),
        ('overlap', series((102, 110, 73, 97, 350, None)), (Z,)),
        ('while_tracking', series(RED, (91, 93, 87, 91, 1000, None)), (replace(Z, bottom=90, top=92),)),
        ('new_after_loss', series(DOJI, (91, 93, 88, 91, 1000, None)),
         (Z, replace(Z, key='lower2', bottom=90, top=92, known_from=START+timedelta(days=6)))),
        ('break_and_recovery', series(DOJI, BOUNCE), (replace(Z, bottom=100, top=101),)),
        ('initial_below', series((97, 113, 96, 112, 400, None)), (replace(Z, bottom=110, top=111),)),
        ('known_no_reaction', series(DOJI), (replace(Z, bottom=10, top=11),)),
    ]
    return C, cases


def main():
    RESULTS.mkdir(exist_ok=True)
    tracked = git('-c', 'core.quotePath=false', 'ls-files').decode('utf-8').splitlines()
    protected_paths = {p for p in tracked if not p.startswith('research/')}
    protected_paths.update(('.vscode/settings.json', 'data/trades.db',
                           'research/ccx_rapid_drop/example_config.json', 'research/ccx_rapid_drop/levels.example.json'))
    protected = {p: digest(REPO/p) for p in sorted(protected_paths) if (REPO/p).is_file()}
    missing_local = [p for p in sorted(protected_paths) if not (REPO/p).is_file()]
    tests = logged('tests.log', ['-m', 'unittest', 'discover', '-v'])
    test_count = int(re.search(rb'Ran (\d+) tests?', tests.stderr).group(1))
    replay = logged('replay.log', ['replay.py', '--repo', str(REPO), '--config', 'example_config.json',
                                  '--levels', 'levels.example.json', '--output', 'results_v02/observations.jsonl'])

    import pandas as pd
    from rapid_drop import Bar, Config, Level, EVENT_KINDS, analyze
    sys.path.insert(0, str(REPO/'backend/app/services'))
    from candle_patterns import compute_candle_shape, default_shape_params
    from test_review import existing_shapes

    cfg = Config(**json.loads((HERE/'example_config.json').read_text(encoding='utf-8')))
    assert asdict(cfg) == json.loads(git('show', f'{BASE}:research/ccx_rapid_drop/example_config.json'))
    assert json.loads((HERE/'levels.example.json').read_text(encoding='utf-8')) == []
    frame = pd.read_csv(FIXTURE)
    frame['open_time'] = pd.to_datetime(frame['open_time'], utc=True)
    close_times = pd.to_datetime(frame['close_time'], utc=True)
    assert len(frame) == 1762 and not frame['open_time'].duplicated().any()
    assert frame['open_time'].diff().dropna().eq(pd.Timedelta(days=1)).all()
    assert close_times.ge(frame['open_time']).all()
    assert close_times.lt(frame['open_time'] + pd.Timedelta(days=1)).all()
    assert close_times.lt(pd.Timestamp('2026-10-29', tz='UTC')).all()
    shaped = compute_candle_shape(frame)
    bars = [Bar(r.open_time.date(), r.open, r.high, r.low, r.close, r.volume, r.shape) for r in shaped.itertuples()]
    full = analyze(bars, (), cfg)
    output = (RESULTS/'observations.jsonl').read_text(encoding='utf-8')
    assert [json.loads(line) for line in output.splitlines()] == json_value([asdict(r) for r in full])
    facts = [e for row in full for e in row.events]
    assert len({e.id for e in facts}) == len(facts)
    assert all(e.anchor_day <= e.day and e.entry_status == 'not_evaluated' for e in facts)
    assert all(e.bounce_confirmed_on < e.day for e in facts if e.kind == 'retest_observed')
    assert all(r.manual_support_status == 'unconfirmed' for r in full)
    with (RESULTS/'events.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(facts[0])))
        writer.writeheader()
        for e in facts:
            writer.writerow(asdict(e))

    old, old_source_hash = load_v01(bars, cfg)
    historical = json.loads((HERE/'results/summary.json').read_text(encoding='utf-8'))
    for name, expected in historical['events'].items():
        assert [str(r.day) for r in old if name in r.events] == expected['dates'], name
    diff = compare_events(old, full)
    assert diff['v02_occurrences'] == diff['matched_v02_facts'] + diff['counts']['added']
    assert diff['v01_occurrences'] == sum(diff['counts'][k] for k in ('preserved', 'reclassified', 'removed'))
    write_json('v01_diff.json', diff)
    with (RESULTS/'v01_diff.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(diff['changes'][0]))
        writer.writeheader()
        writer.writerows(diff['changes'])
    print(f'고정 전체 {len(bars)}봉, v0.1 {diff["v01_occurrences"]} → v0.2 {len(facts)}개 사실', flush=True)

    prefix_started = perf_counter()
    comparisons = 0
    for k in range(1, len(bars)+1):
        prefix_shapes = compute_candle_shape(frame.iloc[:k].copy())['shape'].tolist()
        assert prefix_shapes == shaped['shape'].tolist()[:k]
        prefix_bars = [replace(b, shape=s) for b, s in zip(bars[:k], prefix_shapes)]
        assert analyze(prefix_bars, (), cfg) == full[:k], k
        comparisons += k
        if k % 200 == 0 or k == len(bars):
            print(f'접두 구간 {k}/{len(bars)} 통과 ({perf_counter()-prefix_started:.1f}s)', flush=True)
    future_frame = frame.iloc[[-1]*32].copy().reset_index(drop=True)
    future_frame['open_time'] = pd.date_range(frame['open_time'].iloc[-1]+pd.Timedelta(days=1), periods=32, tz='UTC')
    future_frame['close_time'] = future_frame['open_time']+pd.Timedelta(days=1)-pd.Timedelta(milliseconds=1)
    extended = compute_candle_shape(pd.concat([frame, future_frame], ignore_index=True))
    extra = [Bar(r.open_time.date(), r.open, r.high, r.low, r.close, r.volume, r.shape)
             for r in extended.iloc[len(bars):].itertuples()]
    assert extended['shape'].tolist()[:len(bars)] == shaped['shape'].tolist()
    future_level = Level('future_only', bars[-1].close, bars[-1].close,
                         extra[0].day, extra[-1].day)
    assert analyze(bars+extra, (future_level,), cfg)[:len(bars)] == full

    synth_cfg, cases = synthetic_cases()
    synthetic_results = []
    synthetic_prefixes = 0
    for name, raw, levels in cases:
        sample = existing_shapes(raw)
        observations = analyze(sample, levels, synth_cfg)
        for k in range(1, len(sample)+1):
            assert analyze(existing_shapes(raw[:k]), levels, synth_cfg) == observations[:k], (name, k)
            synthetic_prefixes += 1
        future_bars = [replace(sample[-1], day=sample[-1].day+timedelta(days=j)) for j in range(1, 33)]
        all_sample = existing_shapes(sample+future_bars)
        new_version = Level('future_synthetic', 1, 2, future_bars[0].day, future_bars[-1].day)
        assert analyze(all_sample, (*levels, new_version), synth_cfg)[:len(sample)] == observations, name
        sample_ids = [e.id for row in observations for e in row.events]
        assert len(sample_ids) == len(set(sample_ids))
        synthetic_results.append(dict(name=name, source='synthetic_only', bars=[asdict(b) for b in sample],
            levels=[asdict(s) for s in levels], events=[asdict(e) for row in observations for e in row.events],
            prefixes=len(sample), extension_days=32, mismatches=0))
    write_json('synthetic_support.json', dict(purpose='실제 지지 데이터와 분리한 합성 OHLCV·지지 기능 검사', cases=synthetic_results))

    changed = [p for p, before in protected.items() if not (REPO/p).is_file() or digest(REPO/p) != before]
    assert not changed, changed
    preservation = dict(protected_files_checked=len(protected), changed=changed,
                        absent_on_this_device=missing_local, hashes=protected)
    write_json('preservation.json', preservation)
    counts = Counter(e.kind for e in facts)
    retests = [e for e in facts if e.kind == 'retest_observed']
    summary = dict(schema_version='0.2', base_commit=BASE,
        branch=git('branch', '--show-current').decode().strip(),
        python=dict(executable=sys.executable, version=sys.version,
                    packages={p: importlib.metadata.version(p) for p in ('numpy', 'pandas')}),
        tests=dict(passed=test_count, failed=0), replay=dict(exit_code=0, rows=len(full),
            stderr_bytes=len(replay.stderr), cli_matches_engine=True),
        fixture=dict(path=FIXTURE.relative_to(REPO).as_posix(), sha256=digest(FIXTURE),
                     bars=len(bars), first_day=str(bars[0].day), last_day=str(bars[-1].day)),
        config=asdict(cfg), config_unchanged_from_v01=True, config_status='검증되지 않은 비교용 실험값; 최적화 없음',
        shape_function=dict(path='backend/app/services/candle_patterns.py', sha256=digest(REPO/'backend/app/services/candle_patterns.py'),
                            parameters=asdict(default_shape_params())),
        actual_support_count=0, manual_support_unconfirmed_rows=len(full),
        event_occurrences=len(facts), event_days=sum(bool(r.events) for r in full),
        events={kind: dict(count=counts[kind], dates=[str(e.day) for e in facts if e.kind == kind]) for kind in EVENT_KINDS},
        retest_classification=dict(by_shape=dict(Counter(e.shape or 'none' for e in retests)),
            by_close_location=dict(Counter(e.close_location for e in retests)),
            far_rebounded=sum(e.close_far_rebounded for e in retests),
            lower_wick_contact=sum(e.lower_wick_tests_reference for e in retests)),
        invariance=dict(real_prefixes=len(bars), historical_observation_comparisons=comparisons,
            recompute_existing_shape_for_every_prefix=True, future_days=32, future_level_injected=True,
            synthetic_cases=len(cases), synthetic_prefixes=synthetic_prefixes,
            synthetic_extension_days_each=32, mismatches=0),
        comparison=dict(v01_source_commit=BASE, v01_source_sha256=old_source_hash, v01_reexecuted=True,
            v01_matches_previous_record=True, counts=diff['counts'], old_occurrences=diff['v01_occurrences'],
            new_occurrences=diff['v02_occurrences'], matched_new_facts=diff['matched_v02_facts'],
            old_facts_merged_into_attributes=diff['old_facts_merged_into_attributes']),
        preservation=dict(protected_files_checked=len(protected), changed=changed),
        not_verified=['실제 지지에서의 첫 반응·이탈 회복: 실제 지지 입력 없음',
                      '과거 수동 도형 좌표 버전의 사용 가능 시점', '진입 가능성·성과·체결'],
        not_implemented=['분할 비중', '손절', '체결·손익', '웹 통합', 'RSI', '실제 주문'],
        not_run=['운영 앱 회귀 검사: 연구 폴더 밖 변경 없음', 'main 병합', '운영 배포'])
    write_json('summary.json', summary)
    write_report(summary, diff)
    print(json.dumps(dict(counts), ensure_ascii=False), flush=True)
    print(f'검사 {test_count}개, 불변성 불일치 0, 보호 파일 {len(protected)}개 변경 없음', flush=True)


def write_report(summary, diff):
    statuses = diff['counts']
    added = Counter(c['new_kind'] for c in diff['changes'] if c['status'] == 'added')
    lines = ['# 급락 대응 v0.2 구현·전체 실행 결과', '',
        '실제 지지는 0개다. 사건 수는 거래 수나 수익성이 아니다. 모든 사건의 진입 상태는 `not_evaluated`다.', '',
        f'기준 커밋: `{BASE}`. 작업 브랜치: `{summary["branch"]}`.', '',
        f'프로젝트 Python {summary["python"]["version"].split()[0]}에서 테스트 {summary["tests"]["passed"]}개 통과. '
        '고정 2022-01-01~2026-10-28 일봉 1,762개를 원본 캔들 모양 함수로 재실행했다.', '',
        '| 사건 | 건수 | UTC 봉 날짜 |', '|---|---:|---|']
    for name, row in summary['events'].items():
        lines.append(f'| `{name}` | {row["count"]} | {", ".join(row["dates"]) or "없음"} |')
    lines += ['', '## v0.1 대비 차이', '',
        f'기준 커밋의 엔진을 Git에서 읽어 메모리에서 다시 실행했다. v0.1 {diff["v01_occurrences"]}개 사건, '
        f'v0.2 {diff["v02_occurrences"]}개 사실이다. 이전 결과의 모든 사건별 날짜도 다시 일치했다.', '',
        f'비교 상태: `{diff["counts"]}`. 여러 이전 사건이 한 새 사건의 속성으로 합쳐질 수 있으므로 단순 건수 차이를 추가 사건 수로 해석하지 않는다.', '',
        f'{diff["v01_occurrences"]}개 이전 사건 중 {statuses["preserved"]}개는 분류 유지, '
        f'{statuses["reclassified"]}개는 분류·속성 변경, 삭제 {statuses["removed"]}개다. '
        f'새 사실 {statuses["added"]}개의 종류별 건수는 `{dict(added)}`다. '
        f'이전 별도 사건 {diff["old_facts_merged_into_attributes"]}개를 재시험 속성으로 합쳤다. '
        f'{diff["v01_occurrences"]} + {statuses["added"]} - {statuses["removed"]} - '
        f'{diff["old_facts_merged_into_attributes"]} = {diff["v02_occurrences"]}개 사실이다.', '',
        '| 상태 | UTC 봉 날짜 | 이전 분류 / 기준 | 새 분류 / 기준 | 이유 |', '|---|---|---|---|---|']
    for change in diff['changes']:
        if change['status'] != 'preserved':
            lines.append(f'| {change["status"]} | {change["day"]} | {change["old_kind"] or "—"} / {change["old_anchor_day"] or "—"} | '
                         f'{change["new_kind"] or "—"} / {change["new_anchor_day"] or "—"} | {change["reason"]} |')
    lines += ['', '## 검사 범위와 미검증', '',
        f'기존 모양 함수를 매 접두 구간에서 다시 실행한 1,762개 구간, '
        f'{summary["invariance"]["historical_observation_comparisons"]:,}개 과거 관찰 비교에서 불일치가 없었다. '
        '합성 미래 32일과 미래에 처음 알려지는 지지를 추가해도 과거의 사건 ID와 모든 필드가 같았다.', '',
        f'실제 지지 경로와 분리한 합성 {summary["invariance"]["synthetic_cases"]}개 시나리오에서 '
        f'{summary["invariance"]["synthetic_prefixes"]}개 접두 구간과 각 32일 확장도 일치했다. '
        '세 반전 모양, 기존 기준 중 새 반응, 겹친 장대음봉, 새 하단 반응, 지지 이탈 후 회복을 포함한다.', '',
        f'보호 파일 {summary["preservation"]["protected_files_checked"]}개는 실행 전후 해시가 같다. '
        '기존 앱 코드·사용자 DB·Streamlit·골든값과 기존 실험 설정을 수정하지 않았다. 운영 앱 회귀 검사는 실행하지 않았다.', '',
        '실제 지지에서의 반응과 트랩 후보는 지지 이력이 없어서 검증 불가다. 현재 도형이나 스냅샷을 과거에 소급 적용하지 않았다. '
        '합성 지지의 성공은 실제 시장 경로나 성과 검증을 뜻하지 않는다.', '',
        f'재시험 세부 분류: `{summary["retest_classification"]}`. '
        '높게 마감한 접촉과 가격대 안 마감은 분리되며, 가격대 아래 마감한 접촉도 무효화 사건과 함께 남긴다.', '',
        '`results_v02/events.csv`는 사건별 모든 참조와 가격·모양·거래량을, `v01_diff.csv`는 유지 항목까지 포함한 비교를 제공한다. '
        '전체 봉 JSONL은 로컬 생성물이며 Git에 넣지 않는다. 새 사건 스키마와 재현·기기 인계는 README 및 HANDOFF_V02.md를 참고한다.', '']
    (HERE/'REPORT_V02.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
