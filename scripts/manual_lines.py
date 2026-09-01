"""
기능 1-A. 수동 지지선/저항선/추세선 근접 판정

- 자동 검출 없음: lines_store.py에 저장된, 사용자가 직접 그은 선만 사용
- 수평선(line_type="horizontal")은 지지/저항을 타입으로 고정하지 않음 - 캔들이 선
  위에 있으면 그 선은 지지, 아래 있으면 저항으로 그때그때 동적으로 판정 (위치 기반)
- 근접 판정 기준: 그날 캔들의 저가~고가(꼬리 포함) 범위가 선의 가격 레벨과
  0.1% 이내로 가까운지 (4-4 이평선 터치와 동일한 방식 - 이미 걸쳐있으면 거리 0)
- 추세선의 그날 가격은 두 등록점을 선형으로 잇고, 등록 구간 밖으로도 그대로
  연장(외삽)해서 계산 - 과거에 그은 추세선이 최근 가격과 비교되려면 필요
- 접근 상태가 여러 캔들 지속되면 매 캔들 반복 발생 (다른 임계값 조건들과 동일)
- 수평선 근접 -> 그날 종가가 선 위/아래인지로 지지 시험(매수 후보)/저항 시험(매도 후보) 판정
  추세선 근접 -> 항상 매도 후보 (기획서 스펙, 위치 무관 고정 규칙)
"""
from pathlib import Path

import pandas as pd

from signal_types import Signal

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
    if line["line_type"] == "horizontal":
        return f"수평선 {line['price1']:,.0f}"
    return f"추세선 ({line['time1']} {line['price1']:,.0f} → {line['time2']} {line['price2']:,.0f})"


def _horizontal_levels(lines: list) -> list:
    """추세선 제외, 수평선 가격(price1)만 모은 리스트."""
    return [line["price1"] for line in lines if line["line_type"] == "horizontal"]


def find_next_level(levels: list, current_level: float, direction: str) -> float | None:
    """current_level 기준으로 direction("up"/"down") 방향의 가장 가까운 다음 레벨.

    levels는 지지/저항 구분 없이 전부 포함된 가격 리스트 (호출 전에 _horizontal_levels로 준비).
    없으면 None (해제조건 ①만 적용하라는 뜻).
    """
    if direction == "up":
        candidates = [lv for lv in levels if lv > current_level]
        return min(candidates) if candidates else None
    if direction == "down":
        candidates = [lv for lv in levels if lv < current_level]
        return max(candidates) if candidates else None
    raise ValueError(f"알 수 없는 direction: {direction}")


def _scan_breakout_direction(df: pd.DataFrame, level: float, next_level, direction: str) -> list:
    """수평선 하나, 방향 하나(up/down)에 대해 돌파 에피소드들을 스캔.

    up: 종가가 level 위로 새로 마감(직전엔 아래/같았음)하면 trigger.
        해제: ① 종가가 다시 level 이하로 마감 ② 캔들 저가~고가가 next_level에 걸침(low<=next_level<=high)
        - 둘 다 같은 캔들에서 해당하면 ①(reverse)을 우선.
    down: 방향만 반대 (넘음/이탈 부등호 반전).
    next_level이 None이면 ①만으로 해제.
    """
    close, low, high = df["close"], df["low"], df["high"]
    n = len(df)

    if direction == "up":
        is_breakout = lambda c: c > level
    elif direction == "down":
        is_breakout = lambda c: c < level
    else:
        raise ValueError(f"알 수 없는 direction: {direction}")

    episodes = []
    in_state = False
    trigger_idx = None

    for i in range(1, n):
        if not in_state:
            if is_breakout(close.iloc[i]) and not is_breakout(close.iloc[i - 1]):
                in_state = True
                trigger_idx = i
            continue

        reversed_ = not is_breakout(close.iloc[i])
        touched_next = next_level is not None and low.iloc[i] <= next_level <= high.iloc[i]

        if reversed_ or touched_next:
            end_reason = "reverse" if reversed_ else "next_level"
            episodes.append({
                "trigger_index": trigger_idx, "state_end_index": i - 1, "end_reason": end_reason,
            })
            in_state = False
            trigger_idx = None

    if in_state:
        episodes.append({
            "trigger_index": trigger_idx, "state_end_index": n - 1, "end_reason": "ongoing",
        })

    return episodes


def compute_line_breakout_events(df: pd.DataFrame, line: dict, levels: list) -> list:
    """수평선 하나에 대해 up/down 양방향 돌파 에피소드를 전부 계산.

    타입(지지/저항) 구분 없이 항상 양방향을 다 본다 - direction 자체가 그 순간의
    위치 전환(아래->위 = up, 위->아래 = down)을 의미하므로 별도의 주/보조 신호
    구분(is_primary)이 필요 없다.

    df: open_time/close/low/high 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    line: lines_store 반환 dict 하나 (line_type="horizontal"만 지원, trend는 대상 아님)
    levels: _horizontal_levels(전체 lines) 결과 - 다음 레벨 탐색용

    반환: [{"line_id", "level", "direction", "trigger_index", "open_time",
            "state_end_index", "end_reason"}, ...]
    """
    if line["line_type"] != "horizontal":
        raise ValueError(f"수평선만 지원 (line_type='horizontal'), 받은 값: {line['line_type']}")

    df = df.reset_index(drop=True)
    level = line["price1"]

    events = []
    for direction in ("up", "down"):
        next_level = find_next_level(levels, level, direction)
        episodes = _scan_breakout_direction(df, level, next_level, direction)
        for ep in episodes:
            events.append({
                "line_id": line["id"], "direction": direction, "level": level,
                "trigger_index": ep["trigger_index"],
                "open_time": df["open_time"].iloc[ep["trigger_index"]],
                "state_end_index": ep["state_end_index"],
                "end_reason": ep["end_reason"],
            })

    events.sort(key=lambda e: e["trigger_index"])
    return events


def compute_manual_line_signals(df: pd.DataFrame, lines: list) -> dict:
    """
    df: open_time/close/low/high 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    lines: lines_store.list_lines()의 결과

    반환: {row_index: [Signal("수평선 90,000 근접 - 지지 시험 (매수 후보)", "long"), ...]}

    수평선은 타입 고정이 아니라 그날 종가가 선 위/아래에 있는지로 방향을 정한다
    (위=지지 시험/매수 후보=long, 아래=저항 시험/매도 후보=short, 동률은 매수 후보로
    취급 - 부동소수점상 극히 드문 케이스라 실질적 영향 없음). 추세선은 위치 무관하게
    항상 매도 후보=short로 고정 (기획서 스펙).
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    for line in lines:
        label = line_label(line)

        for i in range(n):
            low, high, close = df["low"].iloc[i], df["high"].iloc[i], df["close"].iloc[i]

            if line["line_type"] == "horizontal":
                level = line["price1"]
                if close >= level:
                    direction_label, direction = "지지 시험 (매수 후보)", "long"
                else:
                    direction_label, direction = "저항 시험 (매도 후보)", "short"
            else:
                level = _trend_line_price(
                    line["time1"], line["price1"], line["time2"], line["price2"],
                    df["open_time"].iloc[i],
                )
                direction_label, direction = "매도 후보", "short"

            if level <= 0:
                continue

            if _distance_ratio(low, high, level) <= PROXIMITY_PCT:
                signals[i].append(Signal(f"{label} 근접 - {direction_label}", direction))

    return signals


def compute_manual_line_state_signals(df: pd.DataFrame, lines: list) -> dict:
    """
    df: open_time/close/low/high 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    lines: lines_store.list_lines()의 결과

    반환: {row_index: [Signal("수평선 90,000 상향 돌파 (롱) 진입", "long"), ...]}

    수평선 돌파(compute_line_breakout_events)만 대상 - 추세선은 아직 돌파/이탈
    이벤트 판정 로직 자체가 없어서 범위 밖 (근접 판정만 존재, 미결 사항 14번 참고).
    선이 삭제되면 다음 호출 때 lines에서 빠지므로 그 선의 state도 자동으로 사라짐 -
    별도 정리 코드 불필요.
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}
    levels = _horizontal_levels(lines)

    for line in lines:
        if line["line_type"] != "horizontal":
            continue

        label = line_label(line)
        for ev in compute_line_breakout_events(df, line, levels):
            if ev["direction"] == "up":
                direction_label, direction = "상향 돌파 (롱)", "long"
            else:
                direction_label, direction = "하향 이탈 (숏)", "short"
            for day_idx in range(ev["trigger_index"], ev["state_end_index"] + 1):
                suffix = "진입" if day_idx == ev["trigger_index"] else "유지 중"
                signals[day_idx].append(Signal(f"{label} {direction_label} {suffix}", direction))

    return signals
