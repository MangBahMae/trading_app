"""
임시 진단 스크립트 - exhaustion.py는 전혀 건드리지 않음.

전체 기간(2022-01-01~)에서 두 버전을 비교:
- 버전A: 현재 로직 그대로 (cond1 & cond2 & cond3) - compute_exhaustion() 결과로 교차 검증
- 버전B: 거래량 조건(cond3) 뺀 버전 (cond1 & cond2만)
"""
import pandas as pd

import exhaustion
from data_fetcher import ensure_fresh_data

START_DATE = pd.Timestamp("2022-01-01", tz="UTC")

df = ensure_fresh_data().reset_index(drop=True)
df = df[df["open_time"] >= START_DATE].reset_index(drop=True)

result = exhaustion.compute_exhaustion(df)  # 교차 검증용, 로직 변경 없음

count_a = 0
count_b = 0
b_only = []  # (date, volume_ratio) - cond1&cond2는 맞는데 cond3에서 탈락했던 날

for i in range(1, len(df)):
    prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    curr_open, curr_close = df["open"].iloc[i], df["close"].iloc[i]
    prev_vol, curr_vol = df["volume"].iloc[i - 1], df["volume"].iloc[i]

    prev_pct = abs((prev_close - prev_open) / prev_open * 100)
    curr_pct = abs((curr_close - curr_open) / curr_open * 100)

    cond1 = prev_pct >= exhaustion.PREV_MIN_PCT
    cond2 = curr_pct <= prev_pct / 2
    cond3 = curr_vol >= prev_vol * exhaustion.VOLUME_MIN_RATIO

    cond_b = cond1 and cond2
    cond_a = cond_b and cond3

    if cond_a:
        count_a += 1
    if cond_b:
        count_b += 1
        if not cond3:
            ratio = curr_vol / prev_vol
            b_only.append((df["open_time"].iloc[i].date(), ratio))

# compute_exhaustion() 결과로 버전A 교차 검증
actual_fired = result["exhaustion_signal"].notna().sum()

print(f"기간: {df['open_time'].iloc[0].date()} ~ {df['open_time'].iloc[-1].date()}  (캔들 {len(df)}개)")
print()
print("=== 총 발화 수 ===")
print(f"버전A (cond1 & cond2 & cond3, 현재 로직) : {count_a}건   (compute_exhaustion() 실측: {actual_fired}건)")
print(f"버전B (cond1 & cond2만, 거래량 조건 제외)  : {count_b}건")
print(f"차이(cond3 때문에 탈락한 건수)            : {count_b - count_a}건")
print()

print(f"=== 버전B에서만 새로 잡히는 날짜 ({len(b_only)}건) - volume[t]/volume[t-1] 비율 ===")
for date, ratio in b_only:
    print(f"  {date}   volume비율={ratio:.3f}  (cond3 기준 0.5 미만이라 탈락)")
