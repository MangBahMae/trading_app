"""
[DISABLED] 실험용 스크립트 - 활성 파이프라인에서 제외됨 (scripts/_disabled/로 이동, 2026-08-27)
참고/비교 목적으로만 보관. 정식 4단계 로직은 scripts/exhaustion.py를 볼 것.

4-6 매물소진 패턴 - 실험용 대안 버전 (기존 scripts/exhaustion.py는 그대로 유지, 비교 목적)

계산:
- Relative Range = 오늘 (고가-저가) / 최근 20봉 평균 (고가-저가)
- Relative Volume = 오늘 거래량 / 최근 20봉 평균 거래량
- ER Score = Relative Volume / Relative Range (참고용으로 함께 저장)

"최근 20봉 평균"은 4-7(거래량 급증)과 동일한 방식: 오늘 이전 최근 20개 캔들 중
주말(토/일) 캔들은 제외하고 남은 평일 캔들만으로 평균 (오늘 자신은 평균 계산에 포함하지 않음 -
look-ahead bias 방지)

판정: Relative Range <= 0.9 AND Relative Volume >= 1.1
     (원래 스펙은 0.7 / 1.5였으나, 이 데이터에서는 두 지표의 상관계수가 0.83으로 강한 양의
      상관관계가 있어 0.7/1.5 조합으로는 신호가 0개였음 - 사용자 확인 후 0.9/1.1로 완화)

방향: 기존 매물소진 패턴과 동일 - 직전 캔들이 음봉이면 매수 신호, 양봉이면 매도 신호
     (이번 캔들 방향은 무관)
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "merged" / "BTCUSDT_1d_exhaustion_v2.parquet"

LOOKBACK = 20
RANGE_MAX_RATIO = 0.9
VOLUME_MIN_RATIO = 1.1


def compute_exhaustion_v2(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    is_weekday = df["open_time"].dt.weekday < 5
    candle_range = df["high"] - df["low"]
    volume = df["volume"]

    rel_range_arr = [None] * len(df)
    rel_volume_arr = [None] * len(df)
    er_score_arr = [None] * len(df)
    signals = [None] * len(df)

    for i in range(LOOKBACK, len(df)):
        window = range(i - LOOKBACK, i)
        weekday_idx = [j for j in window if is_weekday.iloc[j]]
        if not weekday_idx:
            continue

        avg_range = candle_range.iloc[weekday_idx].mean()
        avg_volume = volume.iloc[weekday_idx].mean()
        if avg_range == 0 or avg_volume == 0:
            continue

        rel_range = candle_range.iloc[i] / avg_range
        rel_volume = volume.iloc[i] / avg_volume
        er_score = rel_volume / rel_range if rel_range != 0 else None

        rel_range_arr[i] = rel_range
        rel_volume_arr[i] = rel_volume
        er_score_arr[i] = er_score

        if rel_range <= RANGE_MAX_RATIO and rel_volume >= VOLUME_MIN_RATIO:
            prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
            if prev_close < prev_open:
                signals[i] = "buy"
            elif prev_close > prev_open:
                signals[i] = "sell"

    df["rel_range"] = rel_range_arr
    df["rel_volume"] = rel_volume_arr
    df["er_score"] = er_score_arr
    df["exhaustion_signal_v2"] = signals
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_exhaustion_v2(df)

    print(result["exhaustion_signal_v2"].value_counts(dropna=True))

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
