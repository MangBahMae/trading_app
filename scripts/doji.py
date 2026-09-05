"""
4-5. 도지캔들

판정식 (킥오프 문서 4-5):
    |종가 - 시가| / (고가 - 저가) <= 10%

- 고가==저가(범위 0)인 극단적 경우는 몸통도 반드시 0이 되므로(open=close=high=low),
  0/0 형태가 되지만 몸통이 없다는 의미에서 도지로 판정한다.

3-1-2. [v3] 유효 도지 필터링 (롱만 우선 구현, 숏은 추후 대칭 적용)
- 몸통 조건(위) + 위치 조건(스윙 저점/EMA50·200/수평 지지선 중 하나 근접, OR) + 거래량 증가
- 위치/거래량 판정은 사용자가 그은 선(manual_signals)에 의존하므로 pipeline.py의
  캐시된 흐름에 못 넣고, app.py의 uncached 경로에서 compute_valid_doji_long()으로 계산한다.
  compute_doji()의 순수 몸통 판정 자체는 안 건드림.
"""
from pathlib import Path

import pandas as pd

import swing_points
import sr_touch
from signal_types import Signal

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_doji.parquet"

DOJI_THRESHOLD = 0.10
PROXIMITY_PCT = 0.001         # 지지 근접 기준 (sr_touch.py/manual_lines.py와 동일 관례)
VOLUME_INCREASE_RATIO = 1.0   # 거래량 증가 기준: 직전 대비 배율 (1.0=단순 초과, 실검증 후 조정)


def compute_doji(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    body = (df["close"] - df["open"]).abs()
    candle_range = df["high"] - df["low"]

    ratio = pd.Series(0.0, index=df.index)
    nonzero_range = candle_range != 0
    ratio[nonzero_range] = body[nonzero_range] / candle_range[nonzero_range]
    # candle_range == 0 인 경우 body도 반드시 0이므로 ratio는 0으로 둔다 (도지로 판정됨)

    df["doji_ratio"] = ratio
    df["is_doji"] = ratio <= DOJI_THRESHOLD
    return df


def _near(low: float, high: float, level) -> bool:
    """sr_touch.py와 동일한 근접식 (걸쳐있거나 0.1% 이내)."""
    if level is None or pd.isna(level) or level <= 0:
        return False
    crossed = low <= level <= high
    near_low = abs(low - level) / level <= PROXIMITY_PCT
    near_high = abs(high - level) / level <= PROXIMITY_PCT
    return crossed or near_low or near_high


def _swing_low_price_series(df: pd.DataFrame, swings_df: pd.DataFrame) -> pd.Series:
    """가장 최근 "확정된" 스윙 저점 가격을 매 캔들에 전파.

    확정 시점(i + swing_points.N)부터 반영 - 스윙이 찍힌 그날(i)엔 아직 스윙인지
    알 수 없으므로(우측 N봉이 더 마감돼야 확정) 룩어헤드 방지 원칙에 맞춰 그 이후부터
    값을 채운다 (다이버전스 opposite_pivot 조건과 동일 원칙).
    """
    n = len(df)
    price_at = pd.Series([None] * n, dtype=object)
    for i in range(n):
        if swings_df["swing_low"].iloc[i]:
            confirm_idx = i + swing_points.N
            if confirm_idx < n:
                price_at.iloc[confirm_idx] = df["low"].iloc[i]
    return price_at.ffill()


def compute_valid_doji_long(df: pd.DataFrame, manual_signals: dict) -> dict:
    """도지 몸통 + (스윙저점 근접 OR EMA50/200 터치 OR 수평선 지지 근접) + 거래량 증가.

    df: open_time/open/high/low/close/volume/MA50/MA200 컬럼을 가진 캔들 데이터프레임
        (0-based 연속 인덱스. load_dashboard_data()가 이미 MA50/MA200을 붙여서 넘김)
    manual_signals: compute_manual_line_signals()의 결과 - "수평선 지지 근접"은 여기서
        direction=="long"인 날인지만 확인 (근접 판정 로직 재구현 없이 그대로 재사용)

    반환: {row_index: [Signal("유효한 도지 (지지 근처, 거래량 증가)", "long")]}
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    doji_df = compute_doji(df)
    swings_df = swing_points.find_swing_points(df, n=swing_points.N)
    swing_low_price = _swing_low_price_series(df, swings_df)
    touch_df = sr_touch.compute_sr_touch(df)

    for i in range(1, n):
        if not doji_df["is_doji"].iloc[i]:
            continue

        low, high = df["low"].iloc[i], df["high"].iloc[i]

        near_swing = _near(low, high, swing_low_price.iloc[i])
        near_ema = bool(touch_df["MA50_touch"].iloc[i] or touch_df["MA200_touch"].iloc[i])
        near_line = any(s.direction == "long" for s in manual_signals.get(i, []))

        if not (near_swing or near_ema or near_line):
            continue

        if df["volume"].iloc[i] <= df["volume"].iloc[i - 1] * VOLUME_INCREASE_RATIO:
            continue

        signals[i].append(Signal("유효한 도지 (지지 근처, 거래량 증가)", "long"))

    return signals


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_doji(df)

    print(f"도지캔들 개수: {result['is_doji'].sum()} / 전체 {len(result)}개")

    result.to_parquet(OUT_PATH, index=False)
    print(f"저장 완료: {OUT_PATH}")
