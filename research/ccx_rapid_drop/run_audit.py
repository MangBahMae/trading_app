"""고정 전체 replay, 모든 접두 구간, 합성 지지 분기와 파일 보존을 재현하는 연구 전용 도구."""
import csv
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / 'results'
FIXTURE = REPO / 'backend/tests/fixtures/BTCUSDT_1d_2022-01-01_2026-10-28.csv'
EVENTS = (
    'direct_doji_candidate', 'doji_anchor_watch', 'volume_red_watch_only',
    'bounce_observed', 'retest_observed', 'retest_preferred',
    'first_wick_undercut_recovered', 'wick_not_recovered',
    'anchor_lost_on_close', 'anchor_expired', 'shape_observed_only',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name, value):
    (RESULTS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def normalized(rows):
    return json.loads(json.dumps([asdict(r) for r in rows], default=str))


def run_logged(name, arguments):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', *arguments], cwd=HERE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (RESULTS / name).write_bytes(result.stdout + result.stderr)
    print(f'{name}: exit={result.returncode}', flush=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result


def main():
    RESULTS.mkdir(exist_ok=True)
    baseline = json.loads((RESULTS / 'baseline.json').read_text(encoding='utf-8-sig'))
    # 최초 원문 해시와 사용자 데이터 해시를 먼저 검사한다. DB 연결은 하지 않는다.
    protected = {r['path']: digest(REPO / r['path']) for r in baseline['protected_files']}
    assert all(protected[r['path']] == r['sha256'] for r in baseline['protected_files'])
    supplied = {r['path']: digest(REPO / r['path']) for r in baseline['supplied_research']}
    assert all(supplied[r['path']] == r['sha256'] for r in baseline['supplied_research'])

    run_logged('supplied_tests.log', ['-m', 'unittest', '-v', 'test_rapid_drop'])
    run_logged('review_tests.log', ['-m', 'unittest', '-v', 'test_review'])
    replay = run_logged('replay.combined.log', ['replay.py', '--repo', str(REPO),
                        '--config', 'example_config.json', '--levels', 'levels.example.json'])
    (RESULTS / 'observations.jsonl').write_bytes(replay.stdout)
    (RESULTS / 'replay.stderr.log').write_bytes(replay.stderr)
    # combined 파일은 대용량 stdout 중복 저장을 피한다.
    (RESULTS / 'replay.combined.log').write_text(
        f'exit=0\nstdout_rows={len(replay.stdout.splitlines())}\nstderr_bytes={len(replay.stderr)}\n', encoding='utf-8')

    import pandas as pd
    from rapid_drop import Bar, Config, analyze
    sys.path.insert(0, str(REPO / 'backend/app/services'))
    from candle_patterns import compute_candle_shape, default_shape_params

    cfg = Config(**json.loads((HERE / 'example_config.json').read_text(encoding='utf-8')))
    assert json.loads((HERE / 'levels.example.json').read_text(encoding='utf-8')) == []
    frame = pd.read_csv(FIXTURE)
    frame['open_time'] = pd.to_datetime(frame['open_time'], utc=True)
    close_times = pd.to_datetime(frame['close_time'], utc=True)
    assert not frame['open_time'].duplicated().any()
    assert frame['open_time'].is_monotonic_increasing
    assert frame['open_time'].diff().dropna().eq(pd.Timedelta(days=1)).all()
    assert close_times.lt(pd.Timestamp('2026-11-19', tz='UTC')).all()
    assert close_times.ge(frame['open_time']).all()
    assert close_times.lt(frame['open_time'] + pd.Timedelta(days=1)).all()
    shaped = compute_candle_shape(frame)
    bars = [Bar(r.open_time.date(), r.open, r.high, r.low, r.close, r.volume, r.shape)
            for r in shaped.itertuples()]
    full = analyze(bars, (), cfg)
    replay_rows = [json.loads(line) for line in replay.stdout.decode('utf-8').splitlines()]
    assert replay_rows == normalized(full)
    print(f'전체 고정 일봉 {len(bars)}개: CLI와 직접 호출 동일', flush=True)

    # 8일 원문 발췌도 실제 전체 CSV의 같은 구간과 일치해야 한다.
    with (HERE / 'fixture_excerpt.csv').open(encoding='utf-8', newline='') as f:
        excerpt = list(csv.DictReader(f))
    for row, b in zip(excerpt, bars):
        assert row['date'] == str(b.day)
        assert all(float(row[k]) == getattr(b, k) for k in ('open', 'high', 'low', 'close', 'volume'))
    assert len(excerpt) == 8

    dates = {event: [str(r.day) for r in full if event in r.events] for event in EVENTS}
    accelerating = [str(r.day) for r in full if r.accelerating_down is True]
    # 이 CSV는 발생 사건만 포함한다. 같은 봉의 여러 사건은 여러 행으로 기록한다.
    by_day = {b.day: b for b in bars}
    far_closes = []
    with (RESULTS / 'events.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['day', 'event', 'anchor_day', 'anchor_close',
                    'open', 'high', 'low', 'close', 'shape', 'volume_ratio', 'close_above_reference_band'])
        writer.writeheader()
        for b, row in zip(bars, full):
            anchor = by_day.get(row.anchor_day)
            above = bool(anchor and b.close > anchor.close * (1 + cfg.tolerance))
            for event in row.events:
                writer.writerow(dict(day=row.day, event=event, anchor_day=row.anchor_day,
                    anchor_close=anchor.close if anchor else None, open=b.open, high=b.high, low=b.low,
                    close=b.close, shape=b.shape, volume_ratio=row.volume_ratio,
                    close_above_reference_band=above if event.startswith('retest_') else ''))
                if event.startswith('retest_') and above:
                    far_closes.append(dict(day=str(row.day), event=event, anchor_day=str(row.anchor_day),
                                           close=b.close, reference=anchor.close))

    # 매 봉에서 기존 모양 함수까지 새로 호출한다. 전체 봉에서 구한 모양을 과거에 재사용하지 않는다.
    prefix_started = perf_counter()
    shape_names = shaped['shape'].tolist()
    comparisons = 0
    for k in range(1, len(bars) + 1):
        prefix_shaped = compute_candle_shape(frame.iloc[:k].copy())
        prefix_shapes = prefix_shaped['shape'].tolist()
        assert prefix_shapes == shape_names[:k], f'모양 변경: prefix={k}'
        prefix_bars = [replace(b, shape=s) for b, s in zip(bars[:k], prefix_shapes)]
        assert analyze(prefix_bars, (), cfg) == full[:k], f'과거 관찰 변경: prefix={k}'
        comparisons += k
        if k % 100 == 0 or k == len(bars):
            print(f'접두 구간 {k}/{len(bars)} 통과 ({perf_counter() - prefix_started:.1f}s)', flush=True)

    # 고정 구간 뒤 가상의 32일을 추가해도 과거 모든 필드가 동일한지 별도로 검사한다.
    future_frame = frame.iloc[[-1] * 32].copy().reset_index(drop=True)
    future_frame['open_time'] = pd.date_range(frame['open_time'].iloc[-1] + pd.Timedelta(days=1), periods=32, tz='UTC')
    future_frame['close_time'] = future_frame['open_time'] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    extended = compute_candle_shape(pd.concat([frame, future_frame], ignore_index=True))
    assert extended['shape'].tolist()[:len(bars)] == shape_names
    extra = [Bar(r.open_time.date(), r.open, r.high, r.low, r.close, r.volume, r.shape)
             for r in extended.iloc[len(bars):].itertuples()]
    assert analyze(bars + extra, (), cfg)[:len(bars)] == full

    # 합성 OHLCV + 합성 지지의 별도 기능 검사. 실제 지지 데이터 결과로 합치지 않는다.
    from test_rapid_drop import C, Z, DOJI, BOUNCE, series
    from test_review import existing_shapes
    synthetic_bars = existing_shapes(series(DOJI, BOUNCE, (98, 98.2, 93, 97.5, 90, None)))
    synthetic = analyze(synthetic_bars, (Z,), C)
    assert synthetic[5].events == ('direct_doji_candidate',)
    assert synthetic[6].events == ('bounce_observed',)
    assert synthetic[7].events == ('retest_preferred', 'first_wick_undercut_recovered')
    for k in range(1, len(synthetic_bars) + 1):
        assert analyze(existing_shapes(synthetic_bars[:k]), (Z,), C) == synthetic[:k]
    write_json('synthetic_support.json', dict(
        purpose='합성 OHLCV와 합성 지지로 분기만 시험. 실제 시장 지지·수익률 검증이 아니다.',
        level=json.loads(json.dumps(asdict(Z), default=str)), observations=normalized(synthetic),
        prefix_checks=len(synthetic_bars)))

    after = {p: digest(REPO / p) for p in protected}
    original_after = {p: digest(REPO / p) for p in supplied}
    changed = [p for p in protected if protected[p] != after[p]]
    supplied_changed = [p for p in supplied if supplied[p] != original_after[p]]
    assert not changed, changed
    assert not supplied_changed, supplied_changed
    preservation = dict(protected_files_checked=len(protected), changed=changed,
                        supplied_research_changed=supplied_changed,
                        user_files={p: after[p] for p in ('.vscode/settings.json', 'data/trades.db', 'data/merged/manual_lines.db')})
    write_json('preservation.json', preservation)
    summary = dict(
        base_commit=baseline['base_commit'], branch=baseline['branch'],
        python=dict(executable=sys.executable, version=sys.version, prefix=sys.prefix,
                    packages={p: importlib.metadata.version(p) for p in ('numpy', 'pandas')}),
        fixture=dict(path=FIXTURE.relative_to(REPO).as_posix(), sha256=digest(FIXTURE),
                     bars=len(bars), first_day=str(bars[0].day), last_day=str(bars[-1].day),
                     complete_daily_sequence=True, closed_before='2026-11-19T00:00:00Z', excerpt_matches=True),
        config=asdict(cfg), config_status='검증되지 않은 원본 실험값; 최적화하지 않음',
        config_sha256=digest(HERE / 'example_config.json'), level_count=0,
        shape_function=dict(module='backend/app/services/candle_patterns.py',
                            sha256=digest(REPO / 'backend/app/services/candle_patterns.py'),
                            parameters=asdict(default_shape_params())),
        tests=dict(supplied=19, review=10, failures=0), cli_matches_engine=True,
        event_rows=sum(bool(r.events) for r in full), event_occurrences=sum(len(r.events) for r in full),
        events={e: dict(count=len(dates[e]), dates=dates[e]) for e in EVENTS},
        accelerating_down=dict(count=len(accelerating), dates=accelerating),
        warmup=dict(slope_unavailable=sum(r.accelerating_down is None for r in full),
                    volume_ratio_unavailable=sum(r.volume_ratio is None for r in full)),
        retest_closes_above_reference_band=far_closes,
        invariance=dict(real_prefixes=len(bars), historical_observation_comparisons=comparisons,
                        recompute_existing_shape_for_every_prefix=True, mismatches=0,
                        synthetic_future_days=32, extension_history_unchanged=True,
                        synthetic_support_prefixes=len(synthetic_bars)),
        preservation=preservation,
        not_verifiable=['실제 지지에서의 첫 도지 후보: 지지 입력 없음',
                        '과거 수동 도형의 당시 좌표/버전 사용 가능 시점: 수정 이력 없음',
                        '스크린샷 거래 재현과 성과: 대응 데이터/체결 모델 없음'],
        not_run=['전체 운영 앱/프런트 테스트', '수익률·수수료·슬리피지·체결 검증',
                 'main 병합', '운영 배포', '실제 주문', '임계값 최적화'])
    write_json('summary.json', summary)
    print(json.dumps({e: len(dates[e]) for e in EVENTS}, ensure_ascii=False), flush=True)
    print(f'보존 확인 {len(protected)}개, 원본 연구 {len(supplied)}개 변경 없음', flush=True)


if __name__ == '__main__':
    main()
