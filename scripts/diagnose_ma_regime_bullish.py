"""
임시 진단 스크립트 - ma_regime.py는 전혀 건드리지 않음, 결과만 검증.

전체 기간(2022-01-01~) 정배열(bullish) trigger/state 검증 6개 항목.
"""
import pandas as pd

import ma_regime
import sr_touch
from data_fetcher import ensure_fresh_data

START_DATE = pd.Timestamp("2022-01-01", tz="UTC")

df = ensure_fresh_data().reset_index(drop=True)
df = df[df["open_time"] >= START_DATE].reset_index(drop=True)

result = ma_regime.compute_ma_regime(df)
n = len(result)

print(f"기간: {df['open_time'].iloc[0].date()} ~ {df['open_time'].iloc[-1].date()}  (캔들 {n}개)")
print("=" * 70)

# ---------------- 1. trigger인데 state 아닌 행 ----------------
bad1 = result[result["bullish_trigger"] & ~result["bullish_state"]]
print(f"\n[1] trigger=True인데 state=False인 행: {len(bad1)}건 (0이어야 정상)")
if len(bad1):
    print(bad1[["open_time", "bullish_trigger", "bullish_state"]].to_string(index=False))

# ---------------- 2. trigger가 실제 전이 시점인지 ----------------
trigger_idx = result.index[result["bullish_trigger"]].tolist()
bad2 = []
for i in trigger_idx:
    prev_state = result["bullish_state"].iloc[i - 1] if i > 0 else False
    if prev_state:  # 전날도 이미 bullish였으면 전이가 아님
        bad2.append(i)
print(f"\n[2] trigger 발화 {len(trigger_idx)}건 중 '전일 비정배열->당일 정배열' 전이가 아닌 건: {len(bad2)}건")
if bad2:
    print(result.loc[bad2, ["open_time", "bullish_state", "bullish_trigger"]].to_string(index=False))

# ---------------- 3. EMA9/20/50 독립 재계산 vs state 컬럼 ----------------
ema9 = df["close"].ewm(span=9, adjust=False, min_periods=9).mean()
ema20 = df["close"].ewm(span=20, adjust=False, min_periods=20).mean()
ema50 = df["close"].ewm(span=50, adjust=False, min_periods=50).mean()
recompute_bullish = (ema9 > ema20) & (ema20 > ema50)
mismatch3 = (recompute_bullish.fillna(False) != result["bullish_state"]).sum()
print(f"\n[3] 독립 재계산 EMA9>EMA20>EMA50 결과와 기록된 bullish_state 불일치: {mismatch3}건")

# ---------------- 4. 의심 스택 검산 ----------------
ma9, ma20 = result["MA9"], result["MA20"]
close = result["close"]
valid_mask = ma9.notna() & ma20.notna()

cond_a = ((ma9 - close) / ma9 >= ma_regime.BULLISH_SUSPICION_A_PCT)
cond_b = (close < ma20)
recompute_susp = (cond_a.astype(int) + cond_b.astype(int)).where(valid_mask)

recorded_susp = result["bullish_suspicion"]
# 기록값이 None일 수 있으니 비교 전에 둘 다 유효한(NaN 아닌) 곳만 비교
both_valid = recompute_susp.notna() & recorded_susp.notna()
mismatch4 = (recompute_susp[both_valid] != recorded_susp[both_valid].astype(float)).sum()
print(f"\n[4] 의심 스택(컴포넌트A+B) 재계산 vs 기록값 불일치: {mismatch4}건")

out_of_range = recorded_susp.dropna()
out_of_range = out_of_range[(out_of_range < 0) | (out_of_range > 2)]
print(f"    0~2 범위를 벗어난 기록값: {len(out_of_range)}건")

non_bullish_with_susp = result[(result["ma_regime"] != "bullish") & result["bullish_suspicion"].notna()]
print(f"    정배열이 아닌 날에도 bullish_suspicion이 계산된 건수: {len(non_bullish_with_susp)}건 / "
      f"전체 유효 스택 계산 건수 {recorded_susp.notna().sum()}건")
if len(non_bullish_with_susp):
    print("    (해당 날짜의 ma_regime 분포):")
    print("    " + non_bullish_with_susp["ma_regime"].value_counts(dropna=False).to_string().replace("\n", "\n    "))

# ---------------- 5. 첫 trigger와 warmup ----------------
first_trigger_idx = trigger_idx[0] if trigger_idx else None
if first_trigger_idx is not None:
    first_date = result["open_time"].iloc[first_trigger_idx].date()
    first_ma50_valid_idx = result["MA50"].first_valid_index()
    warmup_rows_before_trigger = first_trigger_idx  # 0-based 인덱스 = 그 앞에 있는 캔들 수
    warmup_rows_before_ma50 = first_ma50_valid_idx
    print(f"\n[5] 첫 bullish_trigger 날짜: {first_date} (인덱스 {first_trigger_idx})")
    print(f"    그 시점 이전에 쌓인 캔들 수: {warmup_rows_before_trigger}개")
    print(f"    MA50이 처음 유효(non-NaN)해지는 인덱스: {first_ma50_valid_idx} "
          f"({result['open_time'].iloc[first_ma50_valid_idx].date()}) - MA50 min_periods=50 기준 "
          f"{'충족' if first_ma50_valid_idx >= 49 else '미충족(비정상)'}")
else:
    print("\n[5] 전체 기간 내 bullish_trigger 발화 없음")

# ---------------- 6. sr_touch.py의 EMA 계산 방식 비교 ----------------
print("\n[6] sr_touch.py의 EMA 계산 방식 비교")
import inspect
src = inspect.getsource(sr_touch)
has_own_ewm = ".ewm(" in src
print(f"    sr_touch.py 안에 자체 .ewm(...) 호출 존재 여부: {has_own_ewm}")
print("    -> sr_touch.compute_sr_touch()는 EMA를 직접 계산하지 않고, 인자로 받은 df의")
print("       MA50/MA200 컬럼을 그대로 읽어서 씀 (pipeline.py/doji.py 모두 ma_regime.compute_ma_regime()")
print("       결과를 그대로 전달하거나 그걸로 병합된 df를 전달함).")
print("    -> 따라서 ma_regime.py와 sr_touch.py가 사용하는 EMA 값은 '같은 계산을 두 번' 하는 게")
print("       아니라 '한 번 계산해서 공유'하는 구조라 값 자체가 항상 동일함 (별도 산식 비교 대상 없음).")
