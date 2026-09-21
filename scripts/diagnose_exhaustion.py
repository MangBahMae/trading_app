"""
임시 진단 스크립트 - exhaustion.py는 전혀 건드리지 않음, 결과만 검증용으로 확인.

최근 60봉에 대해 조건 3개를 직접(부호 있는 값으로) 재계산해서,
compute_exhaustion()이 실제로 기록한 신호와 비교한다.
"""
import pandas as pd

import exhaustion
from data_fetcher import ensure_fresh_data

N = 60

df = ensure_fresh_data().reset_index(drop=True)
result = exhaustion.compute_exhaustion(df)

n = len(df)
start = max(1, n - N)

rows = []
for i in range(start, n):
    prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    curr_open, curr_close = df["open"].iloc[i], df["close"].iloc[i]
    prev_vol, curr_vol = df["volume"].iloc[i - 1], df["volume"].iloc[i]

    prev_pct = (prev_close - prev_open) / prev_open * 100
    curr_pct = (curr_close - curr_open) / curr_open * 100

    cond1 = abs(prev_pct) >= exhaustion.PREV_MIN_PCT
    cond2 = abs(curr_pct) <= abs(prev_pct) / 2
    cond3 = curr_vol >= prev_vol * exhaustion.VOLUME_MIN_RATIO
    all_cond = cond1 and cond2 and cond3

    actual = result["exhaustion_signal"].iloc[i]
    fired = pd.notna(actual)  # dtype이 object/str라 결측이 None이 아니라 NaN(float)으로 저장됨 -> `is not None`은 NaN도 True로 잘못 판정
    prev_color = "양봉" if prev_close > prev_open else ("음봉" if prev_close < prev_open else "보합")
    direction_label = {"buy": "매수", "sell": "매도"}.get(actual, "-")

    mismatch = ""
    if all_cond and not fired:
        mismatch = "<< cond 충족인데 미발화"
    elif fired and not all_cond:
        mismatch = "<< 발화했는데 cond 불충족"

    rows.append({
        "date": df["open_time"].iloc[i].date(),
        "prev_pct": round(prev_pct, 2),
        "curr_pct": round(curr_pct, 2),
        "cond1(|prev|>=3.5)": cond1,
        "cond2(|curr|<=|prev|/2)": cond2,
        "cond3(vol>=50%)": cond3,
        "all_cond": all_cond,
        "실제발화": fired,
        "방향": direction_label,
        "직전캔들색": prev_color,
        "불일치": mismatch,
    })

table = pd.DataFrame(rows)
pd.set_option("display.max_rows", None)
pd.set_option("display.width", 200)
print(table.to_string(index=False))

mism = table[table["불일치"] != ""]
print()
print(f"=== 불일치 건수: {len(mism)} / {len(table)} ===")
if len(mism):
    print(mism.to_string(index=False))
else:
    print("cond 충족 여부와 실제 발화 여부가 최근 60봉에서 전부 일치함.")
