"""
임시 진단 스크립트 - ma_regime.py는 전혀 건드리지 않음, 기존 bullish_suspicion 컬럼도 안 건드림.
"래칫(ratchet)" 버전의 의심 단계를 이 스크립트 안에서만 새로 계산해서 비교.

래칫 정의:
- 정배열 구간(state 연속 True) 시작일 = 0단계로 강제
- 그 이후 매일 max(전날 래칫값, 오늘 스냅샷 bullish_suspicion) - 한번 오르면 구간 끝날 때까지 안 내려감
- 구간이 끝나면(state False) 리셋, 다음 구간에서 다시 0부터
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
ma9 = result["MA9"]
close = result["close"]

# ---------------- 래칫 계산 (이 스크립트 로컬 변수, 컬럼 저장/원본 수정 없음) ----------------
ratchet = [None] * n
elapsed = [None] * n
current_max = None
current_start = None
for i in range(n):
    if state.iloc[i]:
        if trigger.iloc[i] or current_max is None:
            current_max = 0  # 구간 시작일 = 0단계 강제
            current_start = i
        else:
            current_max = max(current_max, susp.iloc[i])
        ratchet[i] = current_max
        elapsed[i] = i - current_start + 1
    else:
        current_max = None
        current_start = None

bullish_idx = [i for i in range(n) if state.iloc[i]]
print(f"정배열 총 일수: {len(bullish_idx)}일")
print()

# ---------------- 표본 수 비교: 스냅샷 vs 래칫 ----------------
print("=== 단계별 표본 수 비교 (스냅샷 vs 래칫) ===")
for val in [0, 1, 2]:
    snap_n = sum(1 for i in bullish_idx if susp.iloc[i] == val)
    ratc_n = sum(1 for i in bullish_idx if ratchet[i] == val)
    print(f"  단계={val}: 스냅샷 {snap_n}일  ->  래칫 {ratc_n}일  (차이 {ratc_n - snap_n:+d})")
print()


def broken_within(i, n_):
    if i + n_ >= n:
        return None
    window_states = state.iloc[i + 1:i + n_ + 1]
    return bool((~window_states).any())


# ---------------- 표1: 래칫 단계별 붕괴율/유지회복율 ----------------
print("=" * 70)
print("표1. 래칫 단계별 5봉/10봉 붕괴율 + 유지·회복율")
print("=" * 70)
for val in [0, 1, 2]:
    group = [i for i in bullish_idx if ratchet[i] == val]
    total = len(group)
    print(f"=== ratchet_suspicion = {val}  (총 {total}일) ===")
    if total == 0:
        print("  해당 없음")
        continue
    for n_ in N_LIST:
        usable = [i for i in group if i + n_ < n]
        excluded = total - len(usable)
        broken = 0
        recovered = 0
        for i in usable:
            if broken_within(i, n_):
                broken += 1
            else:
                end_idx = i + n_
                if close.iloc[end_idx] > ma9.iloc[end_idx]:
                    recovered += 1
        usable_n = len(usable)
        if usable_n == 0:
            print(f"  [N={n_}봉] 표본 없음 (데이터 부족 {excluded}일)")
            continue
        broken_pct = broken / usable_n * 100
        recovered_pct = recovered / usable_n * 100
        rest = usable_n - broken - recovered
        print(f"  [N={n_}봉] 표본 {usable_n}일 (제외 {excluded}일) - 붕괴 {broken}일({broken_pct:.1f}%), "
              f"유지+회복 {recovered}일({recovered_pct:.1f}%), 유지+미회복 {rest}일({rest/usable_n*100:.1f}%)")
    print()

# ---------------- 표2: 같은 경과일수 구간 내 래칫 단계별 붕괴율 ----------------
print("=" * 70)
print("표2. 같은 경과일수 구간 내 래칫 단계별 붕괴율")
print("=" * 70)
for lo, hi in BUCKETS:
    label = f"{lo}~{hi if hi < 10_000 else '∞'}일차"
    print(f"[{label}]")
    for val in [0, 1, 2]:
        idxs = [i for i in bullish_idx if ratchet[i] == val and lo <= elapsed[i] <= hi]
        if not idxs:
            print(f"  ratchet={val}: 표본 없음")
            continue
        line = f"  ratchet={val}: 표본 {len(idxs)}일"
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
