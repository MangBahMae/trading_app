"""869df61 대비 지속 급락 구간 정책을 고정 일봉으로 비교한다. DB·네트워크 사용 금지."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import math
import sqlite3
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = '869df6183c59cd81fc6236114cd4d9f0d637a6b9'
DEFAULT_RESULTS = HERE/'results_v03/regime_revision_20261121'
FIXTURE_PATH = 'backend/tests/fixtures/BTCUSDT_1d_2022-01-01_2026-10-28.csv'
ENGINE_PATH = 'research/ccx_rapid_drop/rapid_drop.py'
API_PATH = 'backend/app/services/rapid_drop_signals.py'
SHAPE_PATH = 'backend/app/services/candle_patterns.py'
CONFIG_PATH = 'research/ccx_rapid_drop/example_config.json'
EVIDENCE = ('results_v03/baseline.json', 'results_v03/preservation.json',
            'results_v03/backend_tests.log', 'results_v03/full_replay.json', 'results_v03/signals.csv')
sys.path.insert(0, str(REPO/'backend'))
sys.path.insert(0, str(REPO/'backend/app/services'))


def json_value(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str, allow_nan=False))


def write_json(folder, name, value):
    (folder/name).write_text(json.dumps(json_value(value), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def write_csv(folder, name, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else ['status'])
    with (folder/name).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(json_value(row.get(key)), ensure_ascii=False) if isinstance(row.get(key), (dict, list, tuple))
                             else row.get(key) for key in fields})


def git_bytes(path):
    return subprocess.run(['git', 'show', f'{BASE}:{path}'], cwd=REPO, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def historical_module(name, path, **injected):
    source = git_bytes(path)
    tree = ast.parse(source, filename=f'git:{BASE}:{path}')
    if 'dashboard' in injected:
        tree.body = [node for node in tree.body if not (isinstance(node, ast.ImportFrom)
                     and node.module == 'app.services' and any(alias.name == 'dashboard' for alias in node.names))]
    module = ModuleType(name)
    module.__file__ = str(REPO/path)
    module.__dict__.update(injected)
    sys.modules[name] = module
    exec(compile(tree, f'git:{BASE}:{path}', 'exec'), module.__dict__)
    return module


def baseline(frame):
    old_engine = historical_module('_regime_baseline_engine', ENGINE_PATH)
    old_shapes = historical_module('_regime_baseline_shapes', SHAPE_PATH)
    old_api = historical_module('_regime_baseline_api', API_PATH,
                                dashboard=SimpleNamespace(candle_patterns=old_shapes))
    old_cfg = old_engine.Config(**json.loads(git_bytes(CONFIG_PATH)))
    old_api.engine = lambda: old_engine
    old_api.config = lambda: old_cfg
    old_frame = old_shapes.compute_candle_shape(frame)
    bars = [old_engine.Bar(row.open_time.date(), row.open, row.high, row.low, row.close, row.volume, row.shape)
            for row in old_frame.itertuples()]
    observations = old_engine.analyze(bars, (), old_cfg)
    timeline = old_api.project_observations(observations, old_cfg, {bar.day: bar.close for bar in bars})
    return timeline, observations, old_frame


def check_duplicate_and_links(timeline):
    seen, issued_candidates = set(), set()
    candidate_keys = set()
    for day, state in timeline.items():
        current_ids = [signal['id'] for signal in state['signals']]
        assert len(current_ids) == len(set(current_ids)), ('same_day_duplicate', day)
        for signal in state['signals']:
            assert signal['id'] not in seen, ('history_duplicate', day, signal['id'])
            assert signal['occurred_on'] == day
            assert set(signal['previous_candidate_ids']) <= issued_candidates, ('future_candidate_link', day)
            if signal['direction'] == 'long':
                key = (signal['type'], signal['anchor_id'], signal['reference'].get('support_version_id'))
                assert key not in candidate_keys, ('reissued_candidate', day, key)
                candidate_keys.add(key)
                issued_candidates.add(signal['id'])
            seen.add(signal['id'])
        assert len(state['history']) == len(seen)
        assert {signal['id'] for signal in state['history']} == seen
        kept = [signal['id'] for signal in state['maintained_candidates']]
        assert len(kept) == len(set(kept))
        assert set(kept) <= issued_candidates
        assert not set(kept) & set(current_ids)
        assert all(signal['occurred_on'] < day for signal in state['maintained_candidates'])
    return dict(history_ids=len(seen), candidate_keys=len(candidate_keys), duplicate_ids=0,
                reissued_candidates=0, invalid_candidate_links=0)


def check_phase_oracle(frame, observations, cfg):
    # 과거 projection의 상태를 기대값으로 쓰지 않고 승인된 식을 별도로 계산한다.
    phase, lowest, started, eased, streak = 'insufficient', None, None, None, 0
    closes = frame.close.tolist()
    for index, row in enumerate(observations):
        close = closes[index]
        recent = math.log(close/closes[index-cfg.slope_bars])/cfg.slope_bars if index >= cfg.slope_bars else None
        previous = (math.log(closes[index-cfg.slope_bars]/closes[index-2*cfg.slope_bars])/cfg.slope_bars
                    if index >= 2*cfg.slope_bars else None)
        strong = recent <= -cfg.min_drop_per_bar if recent is not None else None
        accelerated = bool(strong and recent <= previous-cfg.min_acceleration) if previous is not None else None
        prior_low, no_new = None, None
        if strong and phase != 'active':
            phase, lowest, started, eased, streak = 'active', close, row.day, None, 0
        elif phase == 'active':
            prior_low, no_new = lowest, close >= lowest
            streak = streak+1 if recent > -cfg.regime_ease_drop_per_bar and no_new else 0
            if streak >= cfg.regime_ease_bars:
                phase, eased = 'eased', row.day
            lowest = min(lowest, close)
        elif phase == 'insufficient' and recent is not None:
            phase = 'normal'
        assert row.regime_phase == phase, ('phase', row.day, phase)
        assert row.strong_down == strong and row.accelerating_down == accelerated, ('speed', row.day)
        assert row.regime_started_on == started and row.regime_eased_on == eased
        assert row.regime_recovery_streak == streak
        assert row.regime_previous_lowest_close == prior_low and row.regime_no_new_closing_low == no_new
        assert row.regime_lowest_close == lowest
    return dict(rows=len(observations), mismatches=0, close_low_compared_before_update=True,
                recovery_uses_strict_speed_comparison=True, recovery_requires_both_conditions=True)


def diff_records(old_items, new_items, kind_field, day_field):
    old = {item['id']: item for item in old_items}
    new = {item['id']: item for item in new_items}
    assert len(old) == len(old_items) and len(new) == len(new_items)
    rows, paired_new = [], set()
    ignored = {'evidence', 'cautions', 'title'} if kind_field == 'type' else set()
    for identity, previous in old.items():
        current = new.get(identity)
        if current is None and kind_field == 'type':
            prior_events = set(previous.get('event_ids', []))
            current = next((item for item in new_items if item['id'] not in paired_new
                and item[day_field] == previous[day_field] and prior_events & set(item.get('event_ids', []))), None)
        if current:
            paired_new.add(current['id'])
            old_core = {key: value for key, value in previous.items() if key not in ignored | {'id'}}
            new_core = {key: value for key, value in current.items() if key not in ignored | {'id'}}
            status = 'retained' if json_value(old_core) == json_value(new_core) else 'reclassified'
            if status == 'retained' and previous.get('title') != current.get('title'):
                status = 'relabeled'
            reason = ('동일 발생 사실·기준·후보 연결 유지' if status == 'retained' else
                      '표시명만 변경; ID·유형·발생일·판정은 동일' if status == 'relabeled' else
                      '지속 active/eased 문맥과 후보 참조에 맞춰 분류·근거 갱신')
        else:
            status, reason = 'removed', '이전 고정 관찰창을 active/eased로 바꾸며 관찰 범위 또는 추적 기준 선택이 달라짐'
        rows.append(dict(status=status, day=str(previous[day_field]), old_kind=previous[kind_field],
            new_kind=current[kind_field] if current else None, old_id=identity, new_id=current['id'] if current else None,
            old_title=previous.get('title'), new_title=current.get('title') if current else None,
            old_anchor_day=str(previous.get('anchor_day')) if previous.get('anchor_day') else None,
            new_anchor_day=str(current.get('anchor_day')) if current and current.get('anchor_day') else None, reason=reason))
    for current in new_items:
        if current['id'] in paired_new:
            continue
        kind = current[kind_field]
        reason = ('active 구간의 지지 미확인 반전 모양을 첫 제동 관찰로 표시' if kind == 'brake_watch' else
                  '속도 가속 여부와 별개로 지속 active 구간에서 새 반응·기준과 후속 사건을 평가')
        rows.append(dict(status='added', day=str(current[day_field]), old_kind=None, new_kind=kind,
            old_id=None, new_id=current['id'], old_anchor_day=None,
            old_title=None, new_title=current.get('title'),
            new_anchor_day=str(current.get('anchor_day')) if current.get('anchor_day') else None, reason=reason))
    counts = Counter(row['status'] for row in rows)
    return dict(old_count=len(old_items), new_count=len(new_items),
                counts={name: counts[name] for name in ('retained', 'added', 'removed', 'reclassified', 'relabeled')}, changes=rows)


def daily_rows(frame, old, new, old_obs, new_obs):
    rows = []
    for candle, before, after in zip(frame.itertuples(), old_obs, new_obs):
        day = str(candle.open_time.date())
        prior, current = old[day], new[day]
        market = current['market']
        if market['phase'] == 'active' and not market['accelerating_now']:
            reason = '가속 없음과 별개로 급락 구간 유지'
        elif after.regime_eased_today:
            reason = '속도 회복+종가 저점 갱신 없음 3봉 연속으로 완화'
        elif after.regime_started_today:
            reason = '강한 하락 속도로 새 급락 구간 시작'
        elif market['phase'] == 'active' and market['new_closing_low']:
            reason = '구간 종가 저점 갱신으로 완화 연속 횟수 초기화'
        else:
            reason = '구간 상태 유지'
        rows.append(dict(day=day, close=candle.close, previous_speed=after.previous_speed, recent_speed=after.recent_speed,
            old_accelerating=prior['market']['accelerating_down'], old_observation_window=prior['market']['observation_window'],
            new_phase=market['phase'], strong_drop=market['strong_drop'], accelerating_now=market['accelerating_now'],
            stable_bars=market['stable_bars'], episode_start=market['episode_start'], episode_low_close=market['episode_low_close'],
            previous_low_close=market['previous_low_close'], new_closing_low=market['new_closing_low'],
            old_raw_kinds=[event.kind for event in before.events], new_raw_kinds=[event.kind for event in after.events],
            old_signals=[signal['type'] for signal in prior['signals']], new_signals=[signal['type'] for signal in current['signals']],
            old_maintained=[signal['id'] for signal in prior['maintained_candidates']],
            new_maintained=[signal['id'] for signal in current['maintained_candidates']],
            summary=current['summary'], context_changed=prior['market']['observation_window'] != (market['phase'] == 'active'), reason=reason))
    return rows


def annotate_diff(diff, daily):
    by_day = {row['day']: row for row in daily}
    for change in diff['changes']:
        state = by_day[change['day']]
        change['old_observation_window'] = state['old_observation_window']
        change['new_phase'] = state['new_phase']
        if change['status'] == 'removed' and change['old_kind'] == 'reversal_observed':
            change['reason'] = ('새 구간이 eased로 완화되어 반전 모양 관찰은 중단; 기존 기준의 재시험·무효·만료 처리는 유지'
                                if state['new_phase'] == 'eased' else '새 구간이 active가 아니어서 반전 모양 관찰 제외')
        elif change['status'] == 'added' and change['new_kind'] == 'reversal_observed':
            change['reason'] = ('이전 3봉 관찰창은 끝났지만 active가 유지되어 반전 모양 관찰 추가'
                                if not state['old_observation_window'] else '지속 active 문맥에서 반전 모양 관찰 추가')
        elif change['status'] == 'relabeled':
            change['reason'] += f': {change["old_title"]} → {change["new_title"]}'
    return diff


def save_report(folder, summary, focused, signal_diff):
    lines = ['# 지속 급락 구간 정책 · 고정 일봉 전후 비교', '',
        f'기준 `{BASE}`와 새 단일 엔진/API projection을 비교했다. 실제 지지 입력은 0개이며 후보 수는 거래 수·수익성이 아니다.', '',
        f'고정 일봉 {summary["bars"]}개, UTC 2022-01-01~2026-10-28. 새 phase 분포: `{summary["phase_counts"]}`.', '',
        f'이전 API 신호: `{summary["old_signal_counts"]}`. 새 API 신호: `{summary["new_signal_counts"]}`.', '',
        f'신호 추가/삭제/판정·참조 변경/표시명 변경: `{signal_diff["counts"]}`. 원시 관찰 사건: `{summary["raw_event_diff_counts"]}`.', '',
        '`relabeled`는 제목만 바뀌고 ID·유형·발생일·판정이 같은 경우다. 이번 가속 경고의 '
        '“현재 하락 가속 경고”→“추가 가속 경고”를 판정 변화와 구별한다. `reclassified`는 판정·참조가 바뀐 경우다.', '',
        'active는 recent≤-2%/봉에서 시작한다. 추가 가속은 그 중 recent≤previous-1%p/봉일 때만 참이다. '
        '완화는 recent>-1%/봉과 이전까지 구간 종가 저점 갱신 없음이 동시에 3봉 연속인 날 확정한다. '
        '종가 저점은 비교 후 갱신하며, 한 조건이 깨지면 연속 횟수는 0이다.', '',
        '## 요청 구간의 일별 상태', '',
        '| UTC 날짜 | 종가 | recent/봉 | 이전 관찰창 | 새 phase | 추가 가속 | 안정 봉 | 새 신호 | 요약 |',
        '|---|---:|---:|---|---|---|---:|---|---|']
    for row in focused:
        speed = '-' if row['recent_speed'] is None else f'{row["recent_speed"]*100:.3f}%'
        lines.append(f'| {row["day"]} | {row["close"]:,.2f} | {speed} | {row["old_observation_window"]} | '
                     f'{row["new_phase"]} | {row["accelerating_now"]} | {row["stable_bars"]} | '
                     f'{", ".join(row["new_signals"]) or "없음"} | {row["summary"]["title"]} |')
    lines += ['', '전체 날짜·추가/삭제/분류변경과 이유는 `daily_comparison.csv`, `signal_diff.csv`, `raw_event_diff.csv`에 있다. '
        '신규/유지 후보는 `new_signals.csv`의 발행 기록과 daily CSV의 maintained 목록을 따로 본다.', '',
        '## 불변성·중복 및 제한', '',
        f'검사 결과: `{summary["invariance"]}`. 독립 상태식 검사: `{summary["phase_oracle"]}`. '
        f'중복·후보 연결 검사: `{summary["duplicates"]}`.', '',
        '접두 구간마다 기존 모양 함수부터 재계산했다. 미래 32봉과 미래에 처음 알려진 지지를 추가해도 '
        '과거 phase·summary·raw_events·신호 ID·발행 이력·유지 상태가 같았다.', '',
        '실제 수동 지지 이력이 없으므로 첫 지지 반응과 수동 지지 회복의 실제 시장 검증은 하지 않았다. '
        '합성 지지 검사는 따로 기록한다. 실제 후보의 진입 가능성·체결·수익성도 검증하지 않았다.', '',
        '이번 runner는 SQLite 연결과 외부 요청을 금지하며 실제 DB를 읽거나 기록하지 않는다. '
        '과거 D44→F046 DB 해시 불일치와 사고 증거를 복구·덮어쓰기하지 않았다. '
        '기존 baseline/사고 로그/과거 결과 파일의 바이트 해시가 실행 전후 동일함만 확인했다.', '']
    (folder/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    folder = args.output_dir.resolve()
    if folder in (HERE/'results_v03', HERE/'results', HERE/'results_v02'):
        parser.error('기존 결과 폴더를 덮어쓸 수 없습니다. 새 하위 폴더를 선택하세요.')
    folder.mkdir(parents=True, exist_ok=True)
    def blocked(*_args, **_kwargs):
        raise AssertionError('분석 runner는 실제 DB 연결과 외부 요청을 허용하지 않습니다.')
    sqlite3.connect = blocked
    import requests
    requests.sessions.Session.request = blocked
    import pandas as pd
    evidence_before = {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in EVIDENCE}
    frame = pd.read_csv(REPO/FIXTURE_PATH, parse_dates=['open_time', 'close_time'])
    frozen = pd.read_csv(io.BytesIO(git_bytes(FIXTURE_PATH)), parse_dates=['open_time', 'close_time'])
    pd.testing.assert_frame_equal(frame, frozen)
    assert len(frame) == 1762 and frame.open_time.diff().dropna().eq(pd.Timedelta(days=1)).all()
    old, old_observations, old_shaped = baseline(frame)
    old_history = list(old.values())[-1]['history']
    check_duplicate_and_links(old)
    source_hashes = {path: hashlib.sha256(git_bytes(path)).hexdigest() for path in (ENGINE_PATH, API_PATH, SHAPE_PATH, CONFIG_PATH)}
    write_json(folder, 'old_baseline.json', dict(commit=BASE, bars=len(frame), source_hashes=source_hashes,
        signal_counts=dict(Counter(signal['type'] for signal in old_history)),
        raw_event_counts=dict(Counter(event.kind for row in old_observations for event in row.events))))
    write_csv(folder, 'old_signals.csv', old_history)
    if args.baseline_only:
        print('고정 Git baseline 계산 완료: 1762봉', flush=True)
        return
    from app.services import rapid_drop_signals as svc
    from verify_v03 import verify_timeline_invariance
    new = svc.build_timeline(frame)
    assert 'phase' in next(iter(new.values()))['market'], '새 phase 계약을 기다리세요.'
    shaped = svc.dashboard.candle_patterns.compute_candle_shape(frame)
    assert shaped['shape'].tolist() == old_shaped['shape'].tolist()
    cfg = svc.config()
    old_config = json.loads(git_bytes(CONFIG_PATH))
    current_config = json.loads((REPO/CONFIG_PATH).read_text(encoding='utf-8'))
    assert all(current_config[name] == value for name, value in old_config.items())
    added_parameters = {name: value for name, value in current_config.items() if name not in old_config}
    assert added_parameters == dict(regime_ease_drop_per_bar=0.01, regime_ease_bars=3)
    bars = [svc.engine().Bar(row.open_time.date(), row.open, row.high, row.low, row.close, row.volume, row.shape)
            for row in shaped.itertuples()]
    observations = svc.engine().analyze(bars, (), cfg)
    oracle = check_phase_oracle(frame, observations, cfg)
    duplicate_check = check_duplicate_and_links(new)
    new_history = list(new.values())[-1]['history']
    signal_diff = diff_records(old_history, new_history, 'type', 'occurred_on')
    raw_diff = diff_records([asdict(event) for row in old_observations for event in row.events],
                           [asdict(event) for row in observations for event in row.events], 'kind', 'day')
    daily = daily_rows(frame, old, new, old_observations, observations)
    annotate_diff(signal_diff, daily)
    annotate_diff(raw_diff, daily)
    focused = [row for row in daily if '2026-01-25' <= row['day'] <= '2026-02-10' or '2026-06-01' <= row['day'] <= '2026-06-10']
    assert len(focused) == 27
    write_csv(folder, 'new_signals.csv', new_history)
    write_csv(folder, 'signal_diff.csv', signal_diff['changes'])
    write_csv(folder, 'raw_event_diff.csv', raw_diff['changes'])
    write_csv(folder, 'daily_comparison.csv', daily)
    write_csv(folder, 'focused_days.csv', focused)
    print(f'전후 전체 계산 완료: {len(old_history)} → {len(new_history)}개 API 신호', flush=True)
    invariance = verify_timeline_invariance(svc, frame, full=new, label='지속 구간')
    # 실제 지지와 분리한 합성 첫 반응→반등→재시험의 당시 상태도 검사한다.
    synthetic = pd.DataFrame([(108,109,107,108,100),(108,109,106,107,100),(107,108,105,106,100),
        (106,107,101,102,100),(102,103,96,97,100),(97,99,94,97,300),(97,103,96,102,80),(98,98.2,93,97.5,90)],
        columns=['open','high','low','close','volume'])
    synthetic['open_time'] = pd.date_range('2022-01-01', periods=len(synthetic), tz='UTC')
    synthetic['close_time'] = synthetic.open_time+pd.Timedelta(days=1)-pd.Timedelta(milliseconds=1)
    support = svc.engine().Level('synthetic_only', 96, 98, date(2022,1,1), date(2022,2,28))
    synthetic_timeline = svc.build_timeline(synthetic, (support,))
    synthetic_proof = verify_timeline_invariance(svc, synthetic, (support,), full=synthetic_timeline, label='합성 지지')
    check_duplicate_and_links(synthetic_timeline)
    write_json(folder, 'synthetic_support.json', dict(source='synthetic_only', levels=[asdict(support)],
        timeline=synthetic_timeline, invariance=synthetic_proof))
    evidence_after = {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in EVIDENCE}
    assert evidence_before == evidence_after, '기존 사고 증거 또는 결과가 바뀌었습니다.'
    summary = dict(base_commit=BASE, bars=len(frame), actual_support_count=0, data_source='fixed_fixture',
        fixture_sha256=hashlib.sha256((REPO/FIXTURE_PATH).read_bytes()).hexdigest(),
        old_source_hashes=source_hashes, current_source_hashes={path: hashlib.sha256((REPO/path).read_bytes()).hexdigest() for path in (ENGINE_PATH, API_PATH, SHAPE_PATH, CONFIG_PATH)},
        config=asdict(cfg), existing_example_parameters_unchanged=True,
        approved_added_parameters=added_parameters, shapes_unchanged=True,
        phase_counts=dict(Counter(row.regime_phase for row in observations)),
        active_without_acceleration_dates=[str(row.day) for row in observations if row.regime_phase == 'active' and not row.accelerating_down],
        started_dates=[str(row.day) for row in observations if row.regime_started_today],
        eased_dates=[str(row.day) for row in observations if row.regime_eased_today],
        old_signal_counts=dict(Counter(signal['type'] for signal in old_history)),
        new_signal_counts=dict(Counter(signal['type'] for signal in new_history)),
        signal_diff_counts=signal_diff['counts'], raw_event_diff_counts=raw_diff['counts'],
        context_changed_dates=[row['day'] for row in daily if row['context_changed']],
        new_candidates=[signal for signal in new_history if signal['direction']=='long'],
        phase_oracle=oracle, duplicates=duplicate_check, invariance=invariance,
        synthetic_invariance=synthetic_proof, preserved_historical_evidence=evidence_after,
        db_access='sqlite3.connect blocked; no user DB read/write',
        incident_status='과거 D44→F046 해시 불일치 증거 보존; 이번 검사는 사고 전 보존 성공을 주장하지 않음',
        unverified=['실제 수동 지지에서의 첫 반응·회복 경로', '진입 가능성·체결·수익성'])
    write_json(folder, 'summary.json', summary)
    write_json(folder, 'signal_diff.json', signal_diff)
    write_json(folder, 'raw_event_diff.json', raw_diff)
    save_report(folder, summary, focused, signal_diff)
    print(json.dumps(dict(new_counts=summary['new_signal_counts'], diff=signal_diff['counts'],
        phases=summary['phase_counts'], invariance=invariance), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
