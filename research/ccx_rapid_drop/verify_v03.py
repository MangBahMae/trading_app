"""전체 고정 일봉의 v0.3 신호와 당시 상태 불변성을 확인한다. 실제 수동 지지는 없다."""
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO/'backend'))
sys.path.insert(0, str(REPO/'backend/tests'))


def verify_timeline_invariance(svc, df, levels=(), full=None, future_days=32, label='v0.3'):
    """정책별 후보 날짜를 가정하지 않는 순수 검증. 실제 DB와 API 저장 경로는 호출하지 않는다."""
    import pandas as pd
    full = full if full is not None else svc.build_timeline(df, levels)
    full_values = list(full.values())
    canonical = [{k: v for k, v in state.items() if k != 'history'} for state in full_values]
    comparisons = 0
    for k in range(1, len(df)+1):
        part = svc.build_timeline(df.iloc[:k].copy(), levels)
        values = list(part.values())
        assert [{name: value for name, value in state.items() if name != 'history'} for state in values] == canonical[:k], k
        assert values[-1]['history'] == full_values[k-1]['history'], k
        comparisons += k
        if k % 200 == 0 or k == len(df):
            print(f'{label} 접두 구간 {k}/{len(df)} 통과', flush=True)
    future = df.iloc[[-1]*future_days].copy().reset_index(drop=True)
    future['open_time'] = pd.date_range(df.open_time.iloc[-1]+pd.Timedelta(days=1), periods=future_days, tz='UTC')
    future['close_time'] = future.open_time+pd.Timedelta(days=1)-pd.Timedelta(milliseconds=1)
    future_level = svc.engine().Level('future_invariance_only', 1, 2,
        future.open_time.iloc[0].date(), future.open_time.iloc[-1].date())
    extended = svc.build_timeline(pd.concat([df, future], ignore_index=True), (*levels, future_level))
    assert {day: extended[day] for day in full} == full
    return dict(prefixes=len(df), historical_state_comparisons=comparisons, history_prefix_tips_checked=len(df),
                shape_recomputed_each_prefix=True, future_days=future_days, future_support_injected=True, mismatches=0)


def main():
    import pandas as pd
    import golden_support
    from app.services import rapid_drop_signals as svc
    results = HERE/'results_v03'
    df = golden_support.load_daily_df()
    full = svc.build_timeline(df)
    history = full[str(df.open_time.iloc[-1].date())]['history']
    counts = Counter(s['type'] for s in history)
    candidates = [s for s in history if s['direction'] == 'long']
    assert [(s['type'], s['occurred_on']) for s in candidates] == [('retest_long', '2023-06-11')]
    assert not full['2023-06-12']['signals'] and not full['2023-06-13']['signals']
    assert full['2023-06-12']['maintained_candidates'][0]['id'] == candidates[0]['id']
    expired = next(s for s in full['2023-06-14']['signals'] if s['type'] == 'candidate_expired')
    assert expired['previous_candidate_ids'] == [candidates[0]['id']]
    assert not full['2023-06-14']['maintained_candidates']
    invariance = verify_timeline_invariance(svc, df, full=full)
    baseline = json.loads((results/'baseline.json').read_text(encoding='utf-8-sig'))
    changed = [x['path'] for x in baseline['protected_files']
               if hashlib.sha256((REPO/x['path']).read_bytes()).hexdigest() != x['sha256']]
    assert not changed, changed
    with (results/'signals.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id','type','occurred_on','confirmed_at','anchor_id','anchor_day','previous_candidate_ids'])
        writer.writeheader()
        writer.writerows({k:json.dumps(s[k], ensure_ascii=False) if isinstance(s[k], list) else s[k] for k in writer.fieldnames} for s in history)
    summary = dict(base_commit='aefe83ef583f1ae76129208ef3133cf089dfc610', bars=len(df), actual_support_count=0,
        source='fixed_fixture', counts=dict(counts), new_candidates=candidates,
        candidate_maintained_dates=[d for d,state in full.items() if state['maintained_candidates']],
        invariance=invariance,
        preservation=dict(checked=len(baseline['protected_files']), changed=changed),
        unverified=['실제 지지에서의 첫 반응 및 회복: 과거 좌표 버전 이력 없음',
                    '외부 앱의 관찰 사이 편집 시각 복원', '후보의 수익성·체결 가능성'])
    (results/'full_replay.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(counts), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
