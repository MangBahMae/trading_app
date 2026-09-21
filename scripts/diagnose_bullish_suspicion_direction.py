"""
임시 진단 스크립트 - ma_regime.py는 전혀 건드리지 않음, 결과만 검증.

정배열(state=True)인 날을 그날의 bullish_suspicion(0/1/2)으로 그룹핑해서,
그 뒤 5봉/10봉 이내에 실제로 정배열이 깨지는지 vs 종가가 EMA9 위로 회복하는지 확인.

정의 (여기서 임의로 정한 것, ma_regime.py 로직과 무관 - 순수 사후 집계용):
- "N봉 이내 붕괴" = 신호일 다음날부터 N봉 안에 bullish_state가 하루라도 False가 됨
- "N봉 시점 유지+회복" = N봉 동안 bullish_state가 계속 True로 유지됐고, N봉째 되는 날
  종가가 EMA9 위(>)로 마감함 (즉 그 시점엔 컴포넌트A가 더 이상 안 걸림)
- 데이터가 N봉만큼 안 남은 날(최근 구간)은 그 N 기준 집계에서 제외하고 표본수에 별도 표기
"""
import pandas as pd

import ma_regime
from data_fetcher import ensure_fresh_data

START_DATE = pd.Timestamp("2022-01-01", tz="UTC")
N_LIST = [5, 10]

df = ensure_fresh_data().reset_index(drop=True)
df = df[df["open_time"] >= START_DATE].reset_index(drop=True)

result = ma_regime.compute_ma_regime(df)
n = len(result)

state = result["bullish_state"]
susp = result["bullish_suspicion"]
ma9 = result["MA9"]
close = result["close"]

bullish_days = result.index[state].tolist()

print(f"기간: {df['open_time'].iloc[0].date()} ~ {df['open_time'].iloc[-1].date()}  (캔들 {n}개)")
print(f"정배열(state=True) 총 일수: {len(bullish_days)}일")
print()

for susp_val in [0, 1, 2]:
    group = [i for i in bullish_days if susp.iloc[i] == susp_val]
    total = len(group)
    print(f"=== bullish_suspicion = {susp_val}  (총 {total}일) ===")
    if total == 0:
        print("  해당 없음")
        print()
        continue

    for n_ in N_LIST:
        usable = [i for i in group if i + n_ < n]
        excluded = total - len(usable)

        broken = 0
        recovered = 0
        for i in usable:
            window_states = state.iloc[i + 1:i + n_ + 1]
            is_broken = (~window_states).any()
            if is_broken:
                broken += 1
            else:
                end_idx = i + n_
                if close.iloc[end_idx] > ma9.iloc[end_idx]:
                    recovered += 1

        usable_n = len(usable)
        broken_pct = broken / usable_n * 100 if usable_n else float("nan")
        recovered_pct = recovered / usable_n * 100 if usable_n else float("nan")
        not_broken_not_recovered = usable_n - broken - recovered

        print(f"  [N={n_}봉] 표본 {usable_n}일 (데이터 부족으로 제외 {excluded}일)")
        print(f"    - {n_}봉 이내 정배열 붕괴: {broken}일 ({broken_pct:.1f}%)")
        print(f"    - {n_}봉 시점까지 유지 + 종가 EMA9 위로 회복: {recovered}일 ({recovered_pct:.1f}%)")
        print(f"    - 유지됐지만 {n_}봉째도 EMA9 아래(회복 아님): {not_broken_not_recovered}일 "
              f"({not_broken_not_recovered/usable_n*100:.1f}%)" if usable_n else "")
    print()
