"""
기능 1-A. 수동 지지선/저항선/추세선 근접 판정

- 자동 검출 없음: lines_store.py에 저장된, 사용자가 직접 그은 선만 사용
- 근접 판정 기준: 그날 캔들의 저가~고가(꼬리 포함) 범위가 선의 가격 레벨과
  0.1% 이내로 가까운지 (4-4 이평선 터치와 동일한 방식 - 이미 걸쳐있으면 거리 0)
- 추세선의 그날 가격은 두 등록점을 선형으로 잇고, 등록 구간 밖으로도 그대로
  연장(외삽)해서 계산 - 과거에 그은 추세선이 최근 가격과 비교되려면 필요
- 접근 상태가 여러 캔들 지속되면 매 캔들 반복 발생 (다른 임계값 조건들과 동일)
- 지지선 근접 -> 매수 후보, 저항선/추세선 근접 -> 매도 후보 (기획서 스펙)
"""
from pathlib import Path

import pandas as pd

PROXIMITY_PCT = 0.001  # 0.1%


def _distance_ratio(low: float, high: float, level: float) -> float:
    if low <= level <= high:
        return 0.0
    if level > high:
        return (level - high) / level
    return (low - level) / level


def _trend_line_price(time1, price1, time2, price2, target_time) -> float:
    # df["open_time"]는 UTC-aware라서, "YYYY-MM-DD" 문자열로 들어오는 라인 좌표도
    # 같은 tz로 맞춰야 뺄셈이 된다.
    t1 = pd.Timestamp(time1, tz="UTC")
    t2 = pd.Timestamp(time2, tz="UTC")
    t = pd.Timestamp(target_time)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    if t2 == t1:
        return price1
    frac = (t - t1) / (t2 - t1)
    return price1 + frac * (price2 - price1)


def line_label(line: dict) -> str:
    if line["line_type"] == "support":
        return f"지지선 {line['price1']:,.0f}"
    if line["line_type"] == "resistance":
        return f"저항선 {line['price1']:,.0f}"
    return f"추세선 ({line['time1']} {line['price1']:,.0f} → {line['time2']} {line['price2']:,.0f})"


def compute_manual_line_signals(df: pd.DataFrame, lines: list) -> dict:
    """
    df: open_time/low/high 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    lines: lines_store.list_lines()의 결과

    반환: {row_index: ["지지선 근접 - 매수 후보 (라벨)", ...]}
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    for line in lines:
        label = line_label(line)
        is_buy = line["line_type"] == "support"
        direction_label = "매수 후보" if is_buy else "매도 후보"

        for i in range(n):
            low, high = df["low"].iloc[i], df["high"].iloc[i]

            if line["line_type"] in ("support", "resistance"):
                level = line["price1"]
            else:
                level = _trend_line_price(
                    line["time1"], line["price1"], line["time2"], line["price2"],
                    df["open_time"].iloc[i],
                )

            if level <= 0:
                continue

            if _distance_ratio(low, high, level) <= PROXIMITY_PCT:
                signals[i].append(f"{label} 근접 - {direction_label}")

    return signals
