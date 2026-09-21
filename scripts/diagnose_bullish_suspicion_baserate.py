"""
임시 진단 스크립트 - ma_regime.py는 전혀 건드리지 않음, 결과만 검증.

앞선 suspicion 방향성 분석(diagnose_bullish_suspicion_direction.py)에 base rate 통제 추가:
- suspicion 2단계가 그냥 "정배열 후반부에 몰려있어서" 붕괴율이 높게 나온 착시인지,
  아니면 같은 경과일수(진입 후 며칠째)에서도 suspicion 자체가 붕괴를 더 잘 예측하는지 확인.

정의 (사후 집계용, ma_regime.py 로직과 무관):
- 경과일수 = bullish_trigger 시점을 1일차로 해서 그 이후 정배열이 끊기지 않고 이어진 날수
- "N봉 이내 붕괴" = 앞선 스크립트와 동일 정의 (다음날부터 N봉 안에 state가 하루라도 False)
"""
import pandas as pd

import ma_regime
from data_fetcher import ensure_fresh_data

START_DATE = pd.Timestamp("2022-01-01", tz="UTC")
N_LIST = [5, 10]
BUCKETS = [(1, 5), (6, 10), (11, 20), (21, 10_000)]

df = ensure_fresh_data().reset_index(drop=True)
df = df[df["open_time"] >= START_DATE].reset_index(drop=True)

result = ma_regime.compute_ma_regime(df)
n = len(result)

state = result["bullish_state"]
trigger = result["bullish_trigger"]
susp = result["bullish_suspicion"]

# ---------------- 경과일수 계산 ----------------
elapsed = [None] * n
current_start = None
for i in range(n):
    if state.iloc[i]:
        if trigger.iloc[i] or current_start is None:
            current_start = i
        elapsed[i] = i - current_start + 1
    else:
        current_start = None

bullish_idx = [i for i in range(n) if state.iloc[i]]
print(f"정배열 총 일수: {len(bullish_idx)}일")
print()

# ---------------- 1) suspicion 그룹별 평균 경과일수 ----------------
print("=== suspicion 그룹별 경과일수(진입 후 며칠째) 통계 ===")
for susp_val in [0, 1, 2]:
    vals = [elapsed[i] for i in bullish_idx if susp.iloc[i] == susp_val]
    if not vals:
        print(f"  suspicion={susp_val}: 해당 없음")
        continue
    s = pd.Series(vals)
    print(f"  suspicion={susp_val}: 표본 {len(vals)}일, 평균 {s.mean():.1f}일차, 중앙값 {s.median():.0f}일차, "
          f"최소 {s.min()}일차, 최대 {s.max()}일차")
print()


def broken_within(i, n_):
    if i + n_ >= n:
        return None  # 데이터 부족
    window_states = state.iloc[i + 1:i + n_ + 1]
    return bool((~window_states).any())


# ---------------- 2) 같은 경과일수 구간에서 suspicion별 붕괴율 ----------------
print("=== 같은 경과일수 구간 내 suspicion별 붕괴율 비교 ===")
for lo, hi in BUCKETS:
    label = f"{lo}~{hi if hi < 10_000 else '∞'}일차"
    print(f"[{label}]")
    for susp_val in [0, 1, 2]:
        idxs = [i for i in bullish_idx if susp.iloc[i] == susp_val and lo <= elapsed[i] <= hi]
        if not idxs:
            print(f"  suspicion={susp_val}: 표본 없음")
            continue
        line = f"  suspicion={susp_val}: 표본 {len(idxs)}일"
        for n_ in N_LIST:
            flags = [broken_within(i, n_) for i in idxs]
            usable = [f for f in flags if f is not None]
            if not usable:
                line += f" | N={n_}: 데이터부족"
                continue
            pct = sum(usable) / len(usable) * 100
            line += f" | N={n_}봉 붕괴율={pct:.1f}%(표본{len(usable)})"
        print(line)
    print()
