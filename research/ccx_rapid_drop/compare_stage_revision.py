"""04e4ad9a 대비 급락/관찰/일반 상태와 후보를 평가한다. DB·네트워크는 사용하지 않는다."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
from statistics import median

import compare_regime_revision as shared

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = '04e4ad9a52e78e1de3c718925cf5525f49c99d00'
DEFAULT_RESULTS = HERE/'results_v03/stage_revision_20261122'
SHARP, POST, NORMAL, INSUFFICIENT = 'sharp_drop', 'post_drop', 'normal', 'insufficient'
CANDIDATE_FAMILIES = ('manual_first_long','manual_retest_long','auto_retest_long')


def historical_baseline(frame):
    """이전 도구의 기본 SHA는 호출 동안만 바꾸고 예외가 나도 복원한다."""
    previous = shared.BASE
    try:
        shared.BASE = BASE
        return shared.baseline(frame)
    finally:
        shared.BASE = previous


def historical_bytes(path):
    previous = shared.BASE
    try:
        shared.BASE = BASE
        return shared.git_bytes(path)
    finally:
        shared.BASE = previous


def distribution(values):
    values = sorted(values)
    return dict(n=len(values), minimum=values[0] if values else None, median=median(values) if values else None,
                p90=values[math.ceil(.9*len(values))-1] if values else None,
                maximum=values[-1] if values else None, p90_method='empirical_nearest_rank')


def old_state_views(timeline):
    """원래 UI 경고와 비교용 속도 분할을 함께 제공하며, 새 정책인 것처럼 표현하지 않는다."""
    native, speed_mapping = [], []
    for day, state in timeline.items():
        market = state['market']
        phase = market['phase']
        # eased는 실제 구안의 경보 해제 대응값이다. 진짜 normal 확정 규칙은 아니었다.
        native_phase = SHARP if phase == 'active' else NORMAL if phase in ('eased', 'normal') else INSUFFICIENT
        speed_phase = (SHARP if market['strong_drop'] else POST) if phase == 'active' else native_phase
        base = dict(day=day, original_phase=phase, strong_drop=market['strong_drop'],
                    accelerating_now=market['accelerating_now'])
        native.append(dict(base, phase=native_phase))
        speed_mapping.append(dict(base, phase=speed_phase))
    return native, speed_mapping


def warning_runs(rows):
    runs = []
    current = None
    for index, row in enumerate(rows):
        if row['phase'] == SHARP:
            if current is None:
                current = dict(start=row['day'], start_index=index, warning_bars=0, left_censored=index == 0)
            current['end'], current['end_index'] = row['day'], index
            current['warning_bars'] += 1
        elif current is not None:
            runs.append(dict(current, right_censored=False))
            current = None
    if current is not None:
        runs.append(dict(current, right_censored=True))
    completed = [row['warning_bars'] for row in runs if not row['left_censored'] and not row['right_censored']]
    return runs, dict(complete=distribution(completed), observed_lower_bound=distribution([row['warning_bars'] for row in runs]),
                      left_censored=sum(row['left_censored'] for row in runs),
                      right_censored=sum(row['right_censored'] for row in runs))


def episodes(rows, observation_modelled=True):
    """첫 경고부터 일반 복귀까지 한 구간. 경고↔관찰 재악화는 같은 구간 안에 남긴다."""
    result, current = [], None
    for index, row in enumerate(rows):
        phase = row['phase']
        if current is None and phase in (SHARP, POST):
            current = dict(start=row['day'], start_index=index, left_censored=index == 0 or phase == POST,
                           warning_bars=0, observation_bars=0, first_observation=None, first_observation_index=None)
        if current is None:
            continue
        if phase == NORMAL:
            result.append(dict(current, normal_return=row['day'], normal_return_index=index,
                bars_to_observation=(current['first_observation_index']-current['start_index']) if current['first_observation_index'] is not None else None,
                bars_to_normal=index-current['start_index'], right_censored=False))
            current = None
            continue
        current['warning_bars'] += phase == SHARP
        current['observation_bars'] += phase == POST
        if phase == POST and current['first_observation'] is None:
            current['first_observation'], current['first_observation_index'] = row['day'], index
    if current is not None:
        result.append(dict(current, normal_return=None, normal_return_index=None,
            bars_to_observation=(current['first_observation_index']-current['start_index']) if current['first_observation_index'] is not None else None,
            bars_to_normal=None, right_censored=True))
    valid = [row for row in result if not row['left_censored']]
    return result, dict(count=len(result), complete=sum(not row['right_censored'] for row in valid),
        right_censored=sum(row['right_censored'] for row in result), left_censored=sum(row['left_censored'] for row in result),
        warning_days_per_complete_episode=distribution([row['warning_bars'] for row in valid if not row['right_censored']]),
        bars_to_observation=distribution([row['bars_to_observation'] for row in valid if row['bars_to_observation'] is not None]) if observation_modelled else None,
        observation_not_reached=sum(row['first_observation'] is None for row in valid) if observation_modelled else None,
        observation_stage_not_modelled=not observation_modelled,
        bars_to_normal=distribution([row['bars_to_normal'] for row in valid if row['bars_to_normal'] is not None]))


def transition_recurrence(rows, target, horizon=3):
    """전환일은 제외하고 다음 horizon봉의 경고 재발만 평가한다. 끝부분 불완전 표본은 분모 제외."""
    records = []
    for index, row in enumerate(rows):
        previous = rows[index-1]['phase'] if index else None
        if row['phase'] != target or previous == target:
            continue
        if target == NORMAL and previous not in (SHARP, POST):
            continue
        future = rows[index+1:index+1+horizon]
        normal_return = next((offset+1 for offset, point in enumerate(future) if point['phase'] == NORMAL), None)
        risk_window = future[:normal_return-1] if target == POST and normal_return is not None else future
        hit = next((offset+1 for offset, point in enumerate(risk_window) if point['phase'] == SHARP), None)
        records.append(dict(day=row['day'], previous_phase=previous, phase=target,
            complete_horizon=len(future) == horizon, available_bars=len(future),
            recurrence_observed=hit is not None, first_recurrence_after_bars=hit,
            normal_return_after_bars=normal_return if target == POST else None))
    complete = [row for row in records if row['complete_horizon']]
    numerator = sum(row['recurrence_observed'] for row in complete)
    return records, dict(transitions=len(records), complete_denominator=len(complete), numerator=numerator,
        rate=numerator/len(complete) if complete else None,
        censored=len(records)-len(complete), censored_early_hits=sum(row['recurrence_observed'] for row in records if not row['complete_horizon']),
        horizon=horizon, issue_bar_excluded=True, observation_risk_stops_at_normal=target == POST)


def state_metrics(rows, observation_modelled=True):
    runs, run_summary = warning_runs(rows)
    episode_rows, episode_summary = episodes(rows, observation_modelled)
    post_rows, post_summary = transition_recurrence(rows, POST)
    normal_rows, normal_summary = transition_recurrence(rows, NORMAL)
    return dict(phase_days=dict(Counter(row['phase'] for row in rows)), warning_runs=run_summary,
                episodes=episode_summary, post_drop_recurrence_3=post_summary if observation_modelled else None,
                normal_return_recurrence_3=normal_summary), dict(warning_runs=runs, episodes=episode_rows,
                post_recurrence=post_rows, normal_recurrence=normal_rows)


def candidate_family(signal):
    kind = signal['type']
    if kind == 'first_brake_long':
        return 'manual_first_long'
    if kind == 'retest_long':
        source = signal.get('reference', {}).get('source')
        return 'manual_retest_long' if source == 'manual_support' else 'auto_retest_long'
    return kind


def evaluate_candidates(history, candles, horizon=5):
    """발행 당시 결정에는 미래를 넣지 않는다. 이 함수의 다음 5봉은 사후 가격범위 평가 전용이다."""
    candidates = [signal for signal in history if signal['direction'] == 'long']
    unique = {signal['id']: signal for signal in candidates}
    locations = {row['day']: index for index, row in enumerate(candles)}
    rows = []
    for signal in unique.values():
        index = locations[signal['occurred_on']]
        issue_close = candles[index]['close']
        future = candles[index+1:index+1+horizon]
        maximum = max((row['high'] for row in future), default=None)
        minimum = min((row['low'] for row in future), default=None)
        rows.append(dict(id=signal['id'], type=signal['type'], family=candidate_family(signal),
            day=signal['occurred_on'], anchor_id=signal.get('anchor_id'), reference=signal.get('reference'), issue_close=issue_close,
            future_available_bars=len(future), complete_horizon=len(future) == horizon,
            future_max_high=maximum, future_min_low=minimum,
            max_high_distance_pct=(maximum/issue_close-1)*100 if maximum is not None else None,
            min_low_distance_pct=(minimum/issue_close-1)*100 if minimum is not None else None))
    complete = [row for row in rows if row['complete_horizon']]
    semantic_keys = [(candidate_family(signal), signal.get('anchor_id'), signal.get('reference', {}).get('support_version_id')) for signal in candidates]
    return rows, dict(issued_records=len(candidates), unique_ids=len(unique), duplicate_ids=len(candidates)-len(unique),
        duplicate_semantic_keys=len(semantic_keys)-len(set(semantic_keys)),
        complete_denominator=len(complete), censored=len(rows)-len(complete), horizon=horizon,
        max_high_distance_pct=distribution([row['max_high_distance_pct'] for row in complete]),
        min_low_distance_pct=distribution([row['min_low_distance_pct'] for row in complete]),
        future_used_for='evaluation_only; no fills/returns/fees/position model')


def candidate_metrics_by_family(history,candles):
    return {family:evaluate_candidates([signal for signal in history if signal.get('direction')=='long'
        and candidate_family(signal)==family],candles)[1] for family in CANDIDATE_FAMILIES}


def load_frame():
    import pandas as pd
    frame = pd.read_csv(REPO/shared.FIXTURE_PATH, parse_dates=['open_time','close_time'])
    frozen = pd.read_csv(io.BytesIO(historical_bytes(shared.FIXTURE_PATH)), parse_dates=['open_time','close_time'])
    pd.testing.assert_frame_equal(frame,frozen)
    assert len(frame) == 1762
    assert frame.open_time.diff().dropna().eq(pd.Timedelta(days=1)).all()
    return frame


def phase_oracle(frame, timeline, cfg):
    """승인된 h/A와 두 종료식을 raw 종가에서 따로 계산한다. 저점 갱신 여부는 종료 요건이 아니다."""
    closes=frame.close.tolist()
    speeds=[math.log(close/closes[index-cfg.slope_bars])/cfg.slope_bars if index>=cfg.slope_bars else None
            for index,close in enumerate(closes)]
    phase,h,anchor,price_streak=INSUFFICIENT,None,None,0
    for index,candle in enumerate(frame.itertuples()):
        day=str(candle.open_time.date())
        speed=speeds[index]
        strong=speed<=-cfg.min_drop_per_bar if speed is not None else None
        previous=(math.log(closes[index-cfg.slope_bars]/closes[index-2*cfg.slope_bars])/cfg.slope_bars
                  if index>=2*cfg.slope_bars else None)
        accelerated=bool(strong and speed<=previous-cfg.min_acceleration) if previous is not None else None
        if strong:
            phase,h,anchor,price_streak=SHARP,index,closes[index-2],0
        elif phase in (SHARP,POST):
            phase=POST
            price_streak=price_streak+1 if candle.close>=anchor else 0
            votes=sum(value is not None and value>-.01 for value in speeds[max(0,index-2):index+1])
            if price_streak>=2 or (index-h>=3 and speed>-.01 and votes>=2):
                phase=NORMAL
        elif speed is not None:
            phase=NORMAL
        actual=timeline[day]['market']
        assert actual['phase']==phase,('phase',day,phase,actual['phase'])
        assert actual['strong_drop']==strong and actual['accelerating_now']==accelerated,('speed',day)
    return dict(rows=len(frame),mismatches=0,recovery_anchor='A=C[h-2]',strong_bar_cannot_end_warning=True,
                price_end='C>=A on two consecutive bars after h',
                speed_end='t-h>=3 and today v>-.01 and at least two of latest three v>-.01',
                new_closing_low_not_required=True)


def save_metric_tables(folder, views):
    for table in ('warning_runs','episodes','post_recurrence','normal_recurrence'):
        rows=[dict(model=model,**row) for model,details in views.items() for row in details[table]]
        shared.write_csv(folder,'metrics_'+table+'.csv',rows)


def semantic_diff(previous_items,current_items,stream):
    """ID 체계 교체와 판정 변화는 구분한다. 같은 유형/일자의 실질 기준을 우선 대응한다."""
    kind_key,day_key=('type','occurred_on') if stream=='api' else ('kind','day')
    def family(item):
        return candidate_family(item) if stream=='api' and item.get('direction')=='long' else item[kind_key]
    def reference(item):
        ref=item.get('reference') or {}
        return (str(item.get('anchor_day')) if item.get('anchor_day') else None,
                ref.get('price',item.get('reference_price')),
                ref.get('support_version_id',item.get('support_version_id')))
    groups={}
    for item in previous_items:
        groups.setdefault((family(item),str(item[day_key])),[]).append(item)
    changes=[]
    id_changes=0
    for current in current_items:
        group=groups.get((family(current),str(current[day_key])),[])
        index=next((index for index,item in enumerate(group) if reference(item)==reference(current)),0)
        previous=group.pop(index) if group else None
        if previous is None:
            status='added'
            reason='새 sharp_drop/post_drop 관찰 또는 후보별 생명주기를 구조화해 기록'
        elif previous[kind_key]!=current[kind_key]:
            status='reclassified'
            reason='통합 후보를 manual_first/manual_retest/auto_retest 출처별 유형으로 구분'
        elif reference(previous)!=reference(current):
            status='reference_updated'
            reason='같은 날 같은 관찰/발행의 기준 출처·가격 참조를 다중 기준 모델에 맞춰 명시'
        else:
            status='retained'
            reason='유형·날짜·실질 기준 유지; ID 및 부가 필드 교체는 삭제로 세지 않음'
        changed_id=previous is not None and previous['id']!=current['id']
        id_changes+=changed_id
        changes.append(dict(status=status,day=str(current[day_key]),
            old_type=previous[kind_key] if previous and stream=='api' else None,new_type=current[kind_key] if stream=='api' else None,
            old_kind=previous[kind_key] if previous and stream=='engine' else None,new_kind=current[kind_key] if stream=='engine' else None,
            old_id=previous['id'] if previous else None,new_id=current['id'],id_changed=changed_id,
            old_anchor_day=str(previous.get('anchor_day')) if previous and previous.get('anchor_day') else None,
            new_anchor_day=str(current.get('anchor_day')) if current.get('anchor_day') else None,reason=reason))
    for remaining in groups.values():
        for previous in remaining:
            changes.append(dict(status='removed',day=str(previous[day_key]),
                old_type=previous[kind_key] if stream=='api' else None,new_type=None,
                old_kind=previous[kind_key] if stream=='engine' else None,new_kind=None,
                old_id=previous['id'],new_id=None,id_changed=False,
                old_anchor_day=str(previous.get('anchor_day')) if previous.get('anchor_day') else None,new_anchor_day=None,
                reason='새 일반 복귀 또는 기준별 후보 요건에서 같은 날짜의 관찰/발행을 만들지 않음'))
    counts=Counter(row['status'] for row in changes)
    return dict(counts={name:counts[name] for name in ('retained','added','removed','reclassified','reference_updated')},
                matched_id_changes=id_changes,changes=changes)


def fmt(value):
    return 'NA' if value is None else f'{value:.4f}' if isinstance(value,float) else str(value)


def rate_text(value):
    return '—' if value is None else f'{value*100:.2f}%'


def distance_text(metrics,key,extreme):
    values=metrics[key]
    return '—' if not values['n'] else f'{values["median"]:.4f} / {values["p90"]:.4f} / {values[extreme]:.4f}'


def report(folder,summary,candidates):
    lines=['# 11/22 급락·관찰·일반 전후 평가','',f'기준 `{BASE}`의 Git 계산과 새 단일 엔진/API를 고정 마감 일봉 1,762개로 비교했다. 실제 지지 입력은 0개다.','',
        '## 정의와 분모','',
        '- old_native: 원래 active 전체가 경고였다. eased/normal을 경보 해제의 일반 복귀 **대응값**으로 묶었으며 실제 구안 관찰 단계는 없었다.',
        '- old_speed_mapping: 비교용 진단 분할이다. active+strong을 강한 경고, active+비strong을 관찰 대응, eased/normal을 일반 대응으로 묶었다. 구안에 이 3단계 UI가 있었다는 뜻이 아니다.',
        '- new_native: 실제 sharp_drop/post_drop/normal. 추가 가속은 strong과 별도이므로 독립 집계한다.',
        '- 연속 경고 run과 첫 경고부터 일반 복귀까지 episode를 구분한다. 한 episode 안의 관찰→재급락은 같은 episode에 포함한다.',
        '- 관찰/일반 복귀까지 봉수는 첫 경고 봉을 제외한 인덱스 차이다. 초기 상태가 이미 구간 안이면 left-censored, 데이터 끝까지 미복귀면 right-censored로 별도 표시한다.',
        '- 3봉 비율은 전환일을 제외한 **다음 3개 봉**을 모두 가진 전환만 분모에 넣는다. 관찰 재악화는 중간 NORMAL 전까지의 재급락만 세며 NORMAL 이후 새 급락은 일반 복귀 지표에만 넣는다. 불완전 표본의 조기 재발도 본 분자/분모에서 제외하고 별도 표시한다.',
        '- P90은 정렬된 표본의 ceil(0.9×N)번째인 empirical nearest-rank다. N=0은 0%가 아니라 NA다.',
        f'- 실제 강한 하락일은 old/new 각각 {summary["old_strong_days"]}/{summary["new_strong_days"]}일, 추가 가속일은 '
        f'{summary["old_additional_acceleration_days"]}/{summary["new_additional_acceleration_days"]}일이다. 경고 일수 감소는 상태 표시 구분의 효과이며 강한 하락 판정일이 줄었다는 뜻이 아니다.','',
        '| 모델 | 경고 일수 | 관찰 일수 | 일반 대응 일수 | 완료 경고 run N / median / P90 | episode 경고일 median/P90 | 관찰까지 median/P90 | 일반까지 median/P90 |',
        '|---|---:|---:|---:|---|---|---|---|']
    for model,metrics in summary['state_metrics'].items():
        phases=metrics['phase_days']; run=metrics['warning_runs']['complete']; episodes_summary=metrics['episodes']
        observation=episodes_summary['bars_to_observation']; normal=episodes_summary['bars_to_normal']; warning=episodes_summary['warning_days_per_complete_episode']
        lines.append(f'| {model} | {phases.get(SHARP,0)} | {phases.get(POST,0)} | {phases.get(NORMAL,0)} | {run["n"]} / {fmt(run["median"])} / {fmt(run["p90"])} | '
            f'{fmt(warning["median"])}/{fmt(warning["p90"])} | {fmt(observation["median"]) if observation else "NA"}/{fmt(observation["p90"]) if observation else "NA"} | {fmt(normal["median"])}/{fmt(normal["p90"])} |')
    lines+=['','| 모델 | 관찰 후 다음3봉 재급락 분자/분모 | 비율 | 일반 복귀 후 다음3봉 새 급락 분자/분모 | 비율 |','|---|---|---|---|---|']
    for model,metrics in summary['state_metrics'].items():
        post=metrics['post_drop_recurrence_3']; normal=metrics['normal_return_recurrence_3']
        lines.append(f'| {model} | {str(post["numerator"])+"/"+str(post["complete_denominator"]) if post else "NA"} | '
            f'{rate_text(post["rate"]) if post else "NA"} | {normal["numerator"]}/{normal["complete_denominator"]} | {rate_text(normal["rate"])} |')
    lines+=['','검열 건수와 각 날짜의 분모 포함 여부는 summary.json 및 metrics_* 표에 있다. 구안 active 속도 분할은 가상 대응이므로 native 변경 효과와 혼동하지 않는다.','',
        '## 후보 평가 — 미래는 평가에만 사용','',
        '발행 봉의 종가는 체결가가 아니다. 다음5봉 최대 고가/최저 저가의 발행종가 대비 가격거리를 보여줄 뿐 손익·실현 수익률·비중·비용 모델이 아니다. 발행 봉 자체의 high/low는 제외했다.','',
        '| 버전 | 날짜 | 원래 유형 | 대응 계열 | 발행 종가 | 다음5봉 수 | 최대 고가 거리% | 최저 저가 거리% |','|---|---|---|---|---:|---:|---:|---:|']
    for row in candidates:
        lines.append(f'| {row["model"]} | {row["day"]} | {row["type"]} | {row["family"]} | {row["issue_close"]:.2f} | '
                     f'{row["future_available_bars"]} | {fmt(row["max_high_distance_pct"])} | {fmt(row["min_low_distance_pct"])} |')
    lines+=['','유형별 요약에서 거리 값은 `median / P90 / 전체 최대(고가) 또는 전체 최저(저가)` 순서다. 미표본은 —이며 유지 후보는 새 발행으로 세지 않았다.','',
        '| 버전 | 후보 계열 | 발행 | 고유 ID | ID 중복 | 의미키 중복 | 5봉 완전/검열 | 고가 거리% med/P90/max | 저가 거리% med/P90/min |',
        '|---|---|---:|---:|---:|---:|---|---|---|']
    for model,families in summary['candidate_metrics_by_family'].items():
        for family in CANDIDATE_FAMILIES:
            metrics=families[family]
            lines.append(f'| {model} | {family} | {metrics["issued_records"]} | {metrics["unique_ids"]} | '
                f'{metrics["duplicate_ids"]} | {metrics["duplicate_semantic_keys"]} | {metrics["complete_denominator"]}/{metrics["censored"]} | '
                f'{distance_text(metrics,"max_high_distance_pct","maximum")} | {distance_text(metrics,"min_low_distance_pct","minimum")} |')
    lines+=['','과거 retest_long은 실데이터에 수동 지지가 없다는 확인 범위에서 auto_retest_long 대응으로만 비교한다. '
        '수동 두 계열의 0개는 성공·실패 평가가 아니라 실제 지지 이력이 없는 미표본이다.','',
        '## 검증과 한계','',f'원시 사건 전후: `{summary["raw_event_diff_counts"]}`. API 발행 전후: `{summary["signal_diff_counts"]}`.',
        '원시 ID 체계가 바뀌어도 같은 유형·날짜·실질 기준이 대응되면 삭제/추가로 부풀리지 않았다. ID 교체 수와 참조 갱신은 summary.json/changes.csv에 별도로 남겼다.',
        f'불변성: `{summary["invariance"]}`. 중복·후보 연결: `{summary["duplicates"]}`. 상태 독립식: `{summary["phase_oracle"]}`.',
        '모든 접두 구간에서 기존 모양부터 재계산했고, 미래 봉/미래 지지 추가 뒤 과거 market·summary·유지·history·신호 ID를 비교했다. 미래5봉 평가값은 이 판정 경로에 입력하지 않았다.',
        '수동 첫 반응·재시험과 지지 이탈 후 회복의 실제 경로는 지지 이력이 없어 검증 불가다. 합성 지지 결과는 별도 표시한다. 임계값은 최적화하지 않았다.',
        'SQLite 연결과 외부 요청은 runner에서 금지했다. 과거 D44→F046 DB 해시 불일치와 기존 사고 증거는 보존하며, 이번 계산으로 사고 전 보존 성공을 주장하지 않는다.','']
    (folder/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    folder = args.output_dir.resolve()
    if folder in (HERE/'results_v03', HERE/'results', HERE/'results_v02'):
        parser.error('과거 증거를 덮어쓰지 않도록 새 하위 폴더를 선택하세요.')
    folder.mkdir(parents=True, exist_ok=True)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('DB 및 네트워크 사용 금지')
    sqlite3.connect = forbidden
    import requests
    requests.sessions.Session.request = forbidden
    frame = load_frame()
    old, observations, shaped = historical_baseline(frame)
    native, speed = old_state_views(old)
    history = list(old.values())[-1]['history']
    candles = [dict(day=str(row.open_time.date()), close=row.close, high=row.high, low=row.low) for row in frame.itertuples()]
    native_metrics, native_details = state_metrics(native, observation_modelled=False)
    speed_metrics, speed_details = state_metrics(speed)
    old_candidates, old_candidate_metrics = evaluate_candidates(history, candles)
    old_families=candidate_metrics_by_family(history,candles)
    baseline = dict(base_commit=BASE, bars=len(frame), actual_support_count=0,
        native_phase_days=dict(Counter(row.regime_phase for row in observations)),
        strong_days=sum(row.strong_down is True for row in observations),
        additional_acceleration_days=sum(row.accelerating_down is True for row in observations),
        native_mapping='active 전체=기존 경고, eased/normal=경보 해제 대응값, 실제 관찰 단계 없음',
        speed_mapping='비교용 진단: active+strong=강한 경고, active+비strong=관찰 대응, eased/normal=일반 대응; 구안의 실제 UI 상태 아님',
        native_metrics=native_metrics, speed_mapped_metrics=speed_metrics, candidate_metrics=old_candidate_metrics,
        candidate_metrics_by_family=old_families,
        signal_counts=dict(Counter(signal['type'] for signal in history)),
        source_hashes={path: hashlib.sha256(historical_bytes(path)).hexdigest() for path in
            (shared.ENGINE_PATH,shared.API_PATH,shared.SHAPE_PATH,shared.CONFIG_PATH)})
    shared.write_json(folder,'old_baseline.json',baseline)
    if args.baseline_only:
        print(json.dumps(dict(baseline_ready=True, counts=baseline['signal_counts'], metrics=native_metrics),ensure_ascii=False),flush=True)
        return
    from app.services import rapid_drop_signals as svc
    from verify_v03 import verify_timeline_invariance
    calculation_before={path:hashlib.sha256((REPO/path).read_bytes()).hexdigest() for path in
        (shared.ENGINE_PATH,shared.API_PATH,shared.SHAPE_PATH,shared.CONFIG_PATH)}
    evidence_before={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in shared.EVIDENCE}
    new=svc.build_timeline(frame)
    assert all(state['market']['phase'] in (INSUFFICIENT,NORMAL,SHARP,POST) for state in new.values()),'새 stage engine/API를 기다리세요.'
    cfg=svc.config()
    oracle=phase_oracle(frame,new,cfg)
    duplicates=shared.check_duplicate_and_links(new)
    new_history=list(new.values())[-1]['history']
    current_rows=[dict(day=day,phase=state['market']['phase'],strong_drop=state['market']['strong_drop'],
                      accelerating_now=state['market']['accelerating_now']) for day,state in new.items()]
    current_metrics,current_details=state_metrics(current_rows)
    new_candidates,new_candidate_metrics=evaluate_candidates(new_history,candles)
    candidate_rows=[dict(model=model,**row) for model,rows in (('old',old_candidates),('new',new_candidates)) for row in rows]
    save_metric_tables(folder,dict(old_native=native_details,old_speed_mapping=speed_details,new_native=current_details))
    shared.write_csv(folder,'candidates_5bar.csv',candidate_rows)
    daily=[dict(day=day,close=candle['close'],old_phase=old[day]['market']['phase'],old_native=native[index]['phase'],
        old_speed_mapping=speed[index]['phase'],new_phase=new[day]['market']['phase'],
        old_market=old[day]['market'],new_market=new[day]['market'],
        old_signal_types=[signal['type'] for signal in old[day]['signals']],
        new_signal_types=[signal['type'] for signal in new[day]['signals']],
        old_maintained_ids=[signal['id'] for signal in old[day]['maintained_candidates']],
        new_maintained_ids=[signal['id'] for signal in new[day]['maintained_candidates']],new_summary=new[day]['summary'])
        for index,(day,candle) in enumerate(zip(old,candles))]
    shared.write_csv(folder,'daily_comparison.csv',daily)
    api_diff=semantic_diff(history,new_history,'api')
    new_raw=[event for state in new.values() for event in state.get('raw_events',[])]
    raw_diff=semantic_diff([asdict(event) for row in observations for event in row.events],new_raw,'engine')
    shared.write_csv(folder,'changes.csv',[dict(stream=stream,**row) for stream,rows in
        (('api',api_diff['changes']),('engine',raw_diff['changes'])) for row in rows],
        fields=['stream','status','day','old_type','new_type','old_kind','new_kind','old_id','new_id','id_changed','old_anchor_day','new_anchor_day','reason'])
    print(f'전체 전후 계산: API {len(history)}→{len(new_history)}, 후보 {len(old_candidates)}→{len(new_candidates)}',flush=True)
    invariance=verify_timeline_invariance(svc,frame,full=new,label='11/22 stage')
    # 수동 경로는 실제 데이터와 분리한 고정 합성 8봉으로 검사한다.
    import pandas as pd
    synthetic=pd.DataFrame([(108,109,107,108,100),(108,109,106,107,100),(107,108,105,106,100),
        (106,107,101,102,100),(102,103,96,97,100),(97,99,94,97,300),(97,103,96,102,80),(98,98.2,93,97.5,90)],
        columns=['open','high','low','close','volume'])
    synthetic['open_time']=pd.date_range('2022-01-01',periods=len(synthetic),tz='UTC')
    synthetic['close_time']=synthetic.open_time+pd.Timedelta(days=1)-pd.Timedelta(milliseconds=1)
    level=svc.engine().Level('synthetic_only',96,98,date(2022,1,1),date(2022,2,28))
    synth=svc.build_timeline(synthetic,(level,))
    synth_invariance=verify_timeline_invariance(svc,synthetic,(level,),full=synth,label='11/22 synthetic')
    shared.check_duplicate_and_links(synth)
    shared.write_json(folder,'synthetic_support.json',dict(source='synthetic_only',level=asdict(level),timeline=synth,invariance=synth_invariance))
    assert all(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==value for name,value in evidence_before.items())
    assert all(hashlib.sha256((REPO/path).read_bytes()).hexdigest()==value for path,value in calculation_before.items()),'계산 도중 engine/API source가 바뀌었습니다.'
    summary=dict(base_commit=BASE,bars=len(frame),actual_support_count=0,source='fixed_fixture',
        old_native_mapping=baseline['native_mapping'],old_speed_mapping=baseline['speed_mapping'],
        state_metrics=dict(old_native=native_metrics,old_speed_mapping=speed_metrics,new_native=current_metrics),
        old_signal_counts=baseline['signal_counts'],new_signal_counts=dict(Counter(signal['type'] for signal in new_history)),
        old_strong_days=baseline['strong_days'],old_additional_acceleration_days=baseline['additional_acceleration_days'],
        new_strong_days=sum(row['strong_drop'] is True for row in current_rows),new_additional_acceleration_days=sum(row['accelerating_now'] is True for row in current_rows),
        candidate_metrics=dict(old=old_candidate_metrics,new=new_candidate_metrics),
        candidate_metrics_by_family=dict(old=old_families,new=candidate_metrics_by_family(new_history,candles)),
        signal_diff_counts=api_diff['counts'],raw_event_diff_counts=raw_diff['counts'],
        matched_id_changes=dict(api=api_diff['matched_id_changes'],engine=raw_diff['matched_id_changes']),
        phase_oracle=oracle,duplicates=duplicates,invariance=invariance,synthetic_invariance=synth_invariance,
        current_source_hashes=calculation_before,
        old_source_hashes=baseline['source_hashes'],preserved_historical_evidence=evidence_before,
        future_evaluation='following five bars only; isolated from signal/state inputs',
        db_access='sqlite3.connect blocked; no user DB read/write',
        unverified=['실제 수동 지지 경로','체결 가능성·손익·비용·수익성'],
        incident_status='기존 D44→F046 해시 불일치 증거 보존; 사고 전 보존 성공 아님')
    shared.write_json(folder,'summary.json',summary)
    report(folder,summary,candidate_rows)
    print(json.dumps(dict(counts=summary['new_signal_counts'],new_metrics=current_metrics,candidates=new_candidate_metrics,invariance=invariance),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
