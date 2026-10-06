"""
기능 1 개편 3b단계: 존(가격 구간 직사각형) 신호 판정.

존: price1=상단(T), price2=하단(B), time1=시작, time2=끝 (lines_store의 line_type="zone").
일봉 확정 캔들만 쓰고, 그날 캔들(O/H/L/C)과 직전 종가(PC)만 본다(미래 참조 없음).
"존 안"은 경계 포함(B <= x <= T). 방향은 시가 기준(시가가 존 위 = 지지, 아래 = 저항).

하루에 한 존에서 최대 신호 1개, 이탈 > 반응 순으로 판정한다.

1) 이탈 (종가 마감이 넘어간 첫날만):
   - C > T and PC <= T -> 롱 "상방 이탈"
   - C < B and PC >= B -> 숏 "하방 이탈"
   (방향 부호는 수평선 돌파(manual_lines.py)와 같다: 위로 넘으면 롱, 아래로 이탈하면 숏.
    다만 수평선 돌파는 "유지 중"을 매일 내고, 존 이탈은 넘어간 첫날만 낸다.)
2) 반응 (이탈이 아닐 때):
   - O >= T (존 위에서 시작): L <= T and C >= B -> 롱 "지지 반응"
   - O <= B (존 아래에서 시작): H >= B and C <= T -> 숏 "저항 반응"
   - B < O < T (갭으로 존 안에서 시작): PC > T면 롱 규칙, PC < B면 숏 규칙 그대로
     적용(이때 L <= T / H >= B는 시가가 존 안이라 자동 성립). PC도 존 안이면 신호 없음.
   - 종가가 존 반대편으로 완전히 넘어가면(롱인데 C < B, 숏인데 C > T) 반응이 아니라
     이탈이므로 반응 조건(C >= B / C <= T)에서 자연히 빠진다.
   - first_touch_only=True(기본, B안): 존 밖에서 시작한 반응도 직전 종가가 "같은 쪽 존 밖"
     (롱: PC > T, 숏: PC < B)일 때만 인정한다 - 이미 존에 닿아 있던 상태(직전 종가가 존
     안)에서 다시 내려오는 날을 반복해서 세지 않는다. False면(A안, 비교/참고용) 이
     조건 없이 위 조건만으로 매일 판정한다.
3) 존 안에 머무는 날(시가/종가/직전 종가 모두 존 안)은 위 규칙대로 하면 신호가 없다.

유효 기간: 캔들 날짜(UTC YYYY-MM-DD)가 time1 <= 날짜 <= time2인 캔들만 평가한다(양 끝
포함). time2 이후에는 평가하지 않는다(존은 오른쪽으로 자동 연장되지 않는다). 첫 캔들처럼
직전 종가가 없으면 이탈과 갭 규칙, B안의 반응은 건너뛴다.

사후적으로 그린 존은 형성 시점(created_at) 이전 캔들에도 신호가 나올 수 있다 - 그래서
신호에 존 id/생성일(ref_id/ref_created_at)을 남겨 백테스트가 걸러낼 수 있게 한다.

이 모듈은 존 신호만 만든다. 캔들패턴/EMA 등 다른 신호의 자리 판정에는 연결하지 않는다.
요청마다 다시 계산한다(dashboard.py가 1시간 캐시 밖에서 호출).
"""
import pandas as pd

from signal_types import Signal

SOURCE = "zone"


def _zone_label(top: float, bottom: float) -> str:
    return f"존 {bottom:,.0f}~{top:,.0f}"


def _classify_day(o, h, l, c, pc, top, bottom, first_touch_only):
    """하루 한 존의 판정 -> (suffix, direction) 또는 None. pc는 None일 수 있다(첫 캔들)."""
    # 1) 이탈 우선 (마감이 넘어간 첫날만)
    if pc is not None:
        if c > top and pc <= top:
            return "상방 이탈 (롱)", "long"
        if c < bottom and pc >= bottom:
            return "하방 이탈 (숏)", "short"

    # 2) 반응
    if o >= top:
        side = "support"
    elif o <= bottom:
        side = "resistance"
    else:  # 갭으로 존 안에서 시작 - 직전 종가가 있던 쪽을 기준으로 삼는다
        if pc is None:
            return None
        if pc > top:
            side = "support"
        elif pc < bottom:
            side = "resistance"
        else:
            return None  # 직전 종가도 존 안 -> 신호 없음

    if side == "support":
        if first_touch_only and not (pc is not None and pc > top):
            return None
        if l <= top and c >= bottom:
            return "지지 반응 (매수 후보)", "long"
    else:
        if first_touch_only and not (pc is not None and pc < bottom):
            return None
        if h >= bottom and c <= top:
            return "저항 반응 (매도 후보)", "short"
    return None


def compute_zone_signals(df: pd.DataFrame, lines: list, first_touch_only: bool = True) -> dict:
    """
    df: open_time/open/high/low/close 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    lines: lines_store.list_lines()의 결과 (line_type이 "zone"인 행만 사용)

    반환: {row_index: [Signal("존 28,000~29,000 지지 반응 (매수 후보)", "long", source="zone",
                              ref_id=..., ref_created_at=...), ...]}
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    zones = [ln for ln in lines if ln["line_type"] == "zone"]
    if not zones or n == 0:
        return signals

    dates = df["open_time"].dt.strftime("%Y-%m-%d").tolist()
    opens = df["open"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()

    for zone in zones:
        if zone["time1"] is None or zone["time2"] is None or zone["price2"] is None:
            continue
        top, bottom = zone["price1"], zone["price2"]
        label = _zone_label(top, bottom)

        for i in range(n):
            if dates[i] < zone["time1"] or dates[i] > zone["time2"]:
                continue
            pc = closes[i - 1] if i > 0 else None
            result = _classify_day(opens[i], highs[i], lows[i], closes[i], pc, top, bottom, first_touch_only)
            if result is None:
                continue
            suffix, direction = result
            signals[i].append(Signal(
                f"{label} {suffix}", direction, source=SOURCE,
                ref_id=zone["id"], ref_created_at=zone["created_at"],
            ))

    return signals
