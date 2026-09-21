"""
임시 진단 스크립트 - exhaustion.py 판정 로직은 안 건드림 (USE_VOLUME_FILTER 플래그만 사용).

버전B에서만 새로 잡히는 30건(cond1&cond2는 맞는데 cond3 때문에 탈락했던 날)에 대해,
발화 다음날부터 N봉(3/5/10) 구간의 MFE/MAE를 고가/저가 기준으로 계산.
기준가(entry) = 신호 발화일(트리거 캔들) 종가.
"""
import pandas as pd

import exhaustion
from data_fetcher import ensure_fresh_data

START_DATE = pd.Timestamp("2022-01-01", tz="UTC")
N_LIST = [3, 5, 10]

df = ensure_fresh_data().reset_index(drop=True)
df = df[df["open_time"] >= START_DATE].reset_index(drop=True)

# 1) 버전B(cond1&cond2만)에서 새로 잡히는 30건 재현
exhaustion.USE_VOLUME_FILTER = True
result_a = exhaustion.compute_exhaustion(df)
exhaustion.USE_VOLUME_FILTER = False
result_b = exhaustion.compute_exhaustion(df)

b_only_idx = []
for i in range(len(df)):
    sig_b = result_b["exhaustion_signal"].iloc[i]
    sig_a = result_a["exhaustion_signal"].iloc[i]
    if pd.notna(sig_b) and pd.isna(sig_a):
        b_only_idx.append(i)

print(f"버전B에서만 새로 잡히는 건수: {len(b_only_idx)}건")
print()

# 2) 각 건에 대해 N봉 MFE/MAE 계산
n = len(df)
rows_by_n = {n_: [] for n_ in N_LIST}

for i in b_only_idx:
    direction = "매수" if result_b["exhaustion_signal"].iloc[i] == "buy" else "매도"
    entry = df["close"].iloc[i]
    date = df["open_time"].iloc[i].date()

    for n_ in N_LIST:
        end = min(i + n_, n - 1)
        window = df.iloc[i + 1:end + 1]  # 발화 다음날부터 N봉
        available = len(window)

        if available == 0:
            rows_by_n[n_].append({
                "date": date, "방향": direction, "가용봉수": 0,
                "MFE%": None, "MFE_day": None, "MAE%": None, "MAE_day": None,
            })
            continue

        if direction == "매도":
            # MFE: 최저가 기준 최대 하락률, MAE: 최고가 기준 최대 상승률(역방향)
            min_low = window["low"].min()
            min_low_day = window["low"].values.tolist().index(min_low) + 1
            max_high = window["high"].max()
            max_high_day = window["high"].values.tolist().index(max_high) + 1

            mfe = (entry - min_low) / entry * 100
            mae = (max_high - entry) / entry * 100
            mfe_day, mae_day = min_low_day, max_high_day
        else:
            # 매수: MFE: 최고가 기준 최대 상승률, MAE: 최저가 기준 최대 하락률(역방향)
            max_high = window["high"].max()
            max_high_day = window["high"].values.tolist().index(max_high) + 1
            min_low = window["low"].min()
            min_low_day = window["low"].values.tolist().index(min_low) + 1

            mfe = (max_high - entry) / entry * 100
            mae = (entry - min_low) / entry * 100
            mfe_day, mae_day = max_high_day, min_low_day

        rows_by_n[n_].append({
            "date": date, "방향": direction, "가용봉수": available,
            "MFE%": round(mfe, 2), "MFE_day": mfe_day,
            "MAE%": round(mae, 2), "MAE_day": mae_day,
        })

pd.set_option("display.max_rows", None)
pd.set_option("display.width", 200)

for n_ in N_LIST:
    table = pd.DataFrame(rows_by_n[n_])
    print(f"=== N={n_}봉 (기준가=발화일 종가) ===")
    print(table.to_string(index=False))
    valid = table.dropna(subset=["MFE%"])
    if len(valid):
        print(f"  -> MFE% 평균={valid['MFE%'].mean():.2f}  MAE% 평균={valid['MAE%'].mean():.2f}  "
              f"MFE 중앙값={valid['MFE%'].median():.2f}  MAE 중앙값={valid['MAE%'].median():.2f}")
    print()
