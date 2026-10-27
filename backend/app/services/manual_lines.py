"""
기능 1-A. 수동 지지선/저항선/추세선 근접·돌파 판정

- 자동 검출 없음: lines_store.py에 저장된, 사용자가 직접 그린 선만 사용
- 수평선(line_type="horizontal")은 지지/저항을 타입으로 고정하지 않음 - 캔들이 선
  위에 있으면 그 선은 지지, 아래 있으면 저항으로 그때그때 동적으로 판정 (위치 기반)
- 근접 판정 기준: 그날 캔들의 저가~고가(꼬리 포함) 범위가 선의 가격 레벨과
  0.1% 이내로 가까운지 (4-4 이평선 터치와 동일한 방식 - 이미 걸쳐있으면 거리 0)
- 추세선: 두 등록점을 지나는 직선을, 이른 쪽 점(time1)부터 오른쪽(미래)으로 끝없이 연장해서
  판정한다. time1 이전 날짜는 평가하지 않는다(화면에도 같은 모양의 연장선으로 그린다).
  추세선 돌파는 대부분 두 번째 점 이후에 일어나서, 두 점 사이 선분만 평가하면 실제 돌파를 못 잡기 때문.
  그날의 선 가격은 두 점을 잇는 직선의 값(선형 보간/외삽).
- 접근 상태가 여러 캔들 지속되면 매 캔들 반복 발생 (다른 임계값 조건들과 동일)
- 방향 규칙은 수평선/추세선 공통:
    근접 -> 그날 시가가 선(추세선은 그날의 선 가격) 위면 지지 시험(매수 후보), 아래면 저항 시험(매도 후보)
    돌파 -> 종가 기준: 종가가 선 위로 새로 마감하면 상향 돌파(롱), 아래로 새로 마감하면 하향 이탈(숏),
            종가가 다시 선 반대쪽으로 돌아오거나 캔들이 다음 수평선에 닿으면 상태 종료
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
    if line["line_type"] == "zone":
        return f"▭ 존 {line['price2']:,.0f}~{line['price1']:,.0f} ({line['time1']} → {line['time2']})"
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


def _scan_breakout_series(df: pd.DataFrame, level_by_day: list, direction: str, next_level_for) -> list:
    """날짜(행)별 라인값 리스트에 대해, 방향 하나(up/down)의 돌파 에피소드들을 스캔.

    level_by_day[i]: i번째 캔들 날의 선 가격. 수평선은 모든 날 같은 값, 추세선은 날마다 다른 값(연장선).
                     그 날 선이 없거나 평가하지 않으면(추세선의 time1 이전, 값이 0 이하) None.
    next_level_for(trigger_level): 돌파가 시작된 날의 선 가격 -> 그 방향의 "다음 수평선" 가격(없으면 None).
                     상태 종료 판정에 쓰고, 돌파 시작 시점에 한 번만 정해 상태가 끝날 때까지 고정한다.

    up: 종가가 그날 선 위로 새로 마감(직전 종가는 직전 날 선 위가 아니었음)하면 trigger.
        해제: ① 종가가 그날 선 이하로 되돌아 마감 ② 캔들 저가~고가가 next_level에 걸침(low<=next_level<=high)
        ③ 선이 없어짐(level None) - 둘 다 같은 캔들에서 해당하면 ①(reverse)을 우선.
    down: 방향만 반대 (넘음/이탈 부등호 반전).
    직전 날이나 오늘 중 하루라도 선이 없으면 전환을 판정할 수 없으므로 trigger하지 않는다
    (수평선은 항상 선이 있고, 첫 캔들을 건너뛰는 것과 같은 취급).
    next_level이 None이면 ①③만으로 해제.
    """
    close, low, high = df["close"], df["low"], df["high"]
    n = len(df)

    if direction == "up":
        is_breakout = lambda c, lv: c > lv
    elif direction == "down":
        is_breakout = lambda c, lv: c < lv
    else:
        raise ValueError(f"알 수 없는 direction: {direction}")

    episodes = []
    in_state = False
    trigger_idx = None
    next_level = None

    for i in range(1, n):
        lv, prev_lv = level_by_day[i], level_by_day[i - 1]

        if not in_state:
            if lv is None or prev_lv is None:
                continue
            if is_breakout(close.iloc[i], lv) and not is_breakout(close.iloc[i - 1], prev_lv):
                in_state = True
                trigger_idx = i
                next_level = next_level_for(lv)
            continue

        if lv is None:
            episodes.append({
                "trigger_index": trigger_idx, "state_end_index": i - 1, "end_reason": "line_gone",
            })
            in_state = False
            trigger_idx = None
            next_level = None
            continue

        reversed_ = not is_breakout(close.iloc[i], lv)
        touched_next = next_level is not None and low.iloc[i] <= next_level <= high.iloc[i]

        if reversed_ or touched_next:
            end_reason = "reverse" if reversed_ else "next_level"
            episodes.append({
                "trigger_index": trigger_idx, "state_end_index": i - 1, "end_reason": end_reason,
            })
            in_state = False
            trigger_idx = None
            next_level = None

    if in_state:
        episodes.append({
            "trigger_index": trigger_idx, "state_end_index": n - 1, "end_reason": "ongoing",
        })

    return episodes


def _scan_breakout_direction(df: pd.DataFrame, level: float, next_level, direction: str) -> list:
    """수평선 하나, 방향 하나(up/down)에 대한 돌파 에피소드 스캔 - 모든 날 같은 선 가격인 경우의
    _scan_breakout_series 래퍼 (일반화 이전과 결과가 똑같다)."""
    return _scan_breakout_series(df, [level] * len(df), direction, lambda _lv: next_level)


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


def _trend_start(line: dict) -> str:
    """추세선 평가 시작 날짜 = 두 점 중 이른 쪽(정상 행은 time1). 옛 행처럼 time1 > time2로 저장돼도
    같은 직선/시작이 되게 작은 쪽을 쓴다."""
    return min(line["time1"], line["time2"])


def _line_level_series(df: pd.DataFrame, line: dict) -> list:
    """날짜(행)별 선 가격 리스트. 선이 없거나 평가하지 않는 날은 None.
    수평선: 모든 날 같은 값 / 추세선: 시작일부터 오른쪽으로 연장한 직선 값, 시작일 이전은 None.
    값이 0 이하인 날도 None (가파르게 내려가는 추세선이 연장되다 0을 뚫는 경우)."""
    if line["line_type"] == "horizontal":
        level = line["price1"]
        return [level if level > 0 else None] * len(df)

    start = _trend_start(line)
    out = []
    for ts in df["open_time"]:
        if ts.strftime("%Y-%m-%d") < start:
            out.append(None)
            continue
        value = _trend_line_price(line["time1"], line["price1"], line["time2"], line["price2"], ts)
        out.append(value if value > 0 else None)
    return out


def compute_trend_breakout_events(df: pd.DataFrame, line: dict, levels: list) -> list:
    """추세선 하나에 대해 up/down 양방향 돌파 에피소드를 전부 계산 - 수평선(compute_line_breakout_events)과
    같은 스캔 함수(_scan_breakout_series)를 날짜별 선 가격(오른쪽 무한 연장)으로 돌린다.

    levels: _horizontal_levels(전체 lines) - 돌파 시작일의 선 가격 기준 다음 수평선 탐색용.
    반환 형식은 compute_line_breakout_events와 같다(level은 돌파가 시작된 날의 선 가격).
    """
    if line["line_type"] != "trend":
        raise ValueError(f"추세선만 지원 (line_type='trend'), 받은 값: {line['line_type']}")

    df = df.reset_index(drop=True)
    level_by_day = _line_level_series(df, line)

    events = []
    for direction in ("up", "down"):
        episodes = _scan_breakout_series(
            df, level_by_day, direction, lambda lv, d=direction: find_next_level(levels, lv, d),
        )
        for ep in episodes:
            events.append({
                "line_id": line["id"], "direction": direction,
                "level": level_by_day[ep["trigger_index"]],
                "trigger_index": ep["trigger_index"],
                "open_time": df["open_time"].iloc[ep["trigger_index"]],
                "state_end_index": ep["state_end_index"],
                "end_reason": ep["end_reason"],
            })

    events.sort(key=lambda e: e["trigger_index"])
    return events


def _trend_ref(line: dict) -> dict:
    """신호를 만든 도형의 id/생성일 - 사후적으로 그린 선의 신호를 백테스트가 걸러낼 수 있게 남긴다."""
    return {"ref_id": line.get("id"), "ref_created_at": line.get("created_at")}


def compute_manual_line_signals(df: pd.DataFrame, lines: list) -> dict:
    """
    df: open_time/open/close/low/high 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    lines: lines_store.list_lines()의 결과

    반환: {row_index: [Signal("수평선 90,000 근접 - 지지 시험 (매수 후보)", "long"), ...]}

    수평선/추세선 모두 그날 시가가 선(추세선은 그날의 연장선 가격) 위/아래에 있는지로 방향을 정한다
    (위=지지 시험/매수 후보=long, 아래=저항 시험/매도 후보=short). 시가가 선과 같으면 전날 종가가
    있던 쪽으로 정하고, 그것도 같거나 전날(선이 있는 날)이 없으면 long (기존 동률 관행).

    추세선은 이른 쪽 점(time1)부터 오른쪽으로 끝없이 연장한 직선을 평가한다 - time1 이전 캔들은 평가하지
    않는다. 추세선 신호에는 ref_id(lines.id)와 ref_created_at(lines.created_at)을 남긴다(수평선은 null).
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    for line in lines:
        if line["line_type"] not in ("horizontal", "trend"):
            continue  # 존은 여기서 판정하지 않는다(zone_signals.py) - 선으로 오인(추세선 취급)하지 않게 건너뜀
        label = line_label(line)
        level_by_day = _line_level_series(df, line)
        ref = _trend_ref(line) if line["line_type"] == "trend" else {}

        for i in range(n):
            level = level_by_day[i]
            if level is None:
                continue  # 선이 없는 날(추세선 time1 이전)이거나 값이 0 이하
            low, high, open_ = df["low"].iloc[i], df["high"].iloc[i], df["open"].iloc[i]

            if _distance_ratio(low, high, level) > PROXIMITY_PCT:
                continue

            # 방향은 종가가 아니라 시가가 선의 어느 쪽에 있었는지로 정한다
            # (시가가 위 = 지지 시험/매수 후보=long, 아래 = 저항 시험/매도 후보=short).
            # 수평선/추세선 공통. 시가가 선과 정확히 같으면 전날 종가가 선의 어느 쪽에
            # 있었는지로 정하고, 그것도 같거나 전날(선이 있는 날)이 없으면 long(기존 동률 관행).
            prev_level = level_by_day[i - 1] if i > 0 else None
            if open_ > level:
                is_support = True
            elif open_ < level:
                is_support = False
            elif prev_level is not None and df["close"].iloc[i - 1] != prev_level:
                is_support = df["close"].iloc[i - 1] > prev_level
            else:
                is_support = True

            if is_support:
                direction_label, direction = "지지 시험 (매수 후보)", "long"
            else:
                direction_label, direction = "저항 시험 (매도 후보)", "short"
            signals[i].append(Signal(f"{label} 근접 - {direction_label}", direction, **ref))

    return signals


def compute_manual_line_state_signals(df: pd.DataFrame, lines: list) -> dict:
    """
    df: open_time/close/low/high 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    lines: lines_store.list_lines()의 결과

    반환: {row_index: [Signal("수평선 90,000 상향 돌파 (롱) 진입", "long"), ...]}

    수평선과 추세선의 돌파/이탈이 대상(존은 zone_signals.py). 둘 다 같은 규칙: 종가가 선 위로 새로
    마감하면 상향 돌파(롱), 아래로 새로 마감하면 하향 이탈(숏), 종가가 반대쪽으로 돌아오거나 캔들이
    다음 수평선에 닿으면 상태 종료. 추세선은 이른 쪽 점부터 오른쪽으로 연장한 날짜별 선 가격과 비교한다.
    추세선 신호에는 ref_id/ref_created_at을 남긴다(수평선은 null).
    선이 삭제되면 다음 호출 때 lines에서 빠지므로 그 선의 state도 자동으로 사라짐 -
    별도 정리 코드 불필요.
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}
    levels = _horizontal_levels(lines)

    for line in lines:
        if line["line_type"] == "horizontal":
            events, ref = compute_line_breakout_events(df, line, levels), {}
        elif line["line_type"] == "trend":
            events, ref = compute_trend_breakout_events(df, line, levels), _trend_ref(line)
        else:
            continue  # 존(신호 미사용)은 대상 아님

        label = line_label(line)
        for ev in events:
            if ev["direction"] == "up":
                direction_label, direction = "상향 돌파 (롱)", "long"
            else:
                direction_label, direction = "하향 이탈 (숏)", "short"
            for day_idx in range(ev["trigger_index"], ev["state_end_index"] + 1):
                suffix = "진입" if day_idx == ev["trigger_index"] else "유지 중"
                signals[day_idx].append(Signal(f"{label} {direction_label} {suffix}", direction, **ref))

    return signals
