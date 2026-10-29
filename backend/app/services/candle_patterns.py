"""
캔들패턴 4종 (도지/망치형/역망치형) - 롱/숏 각각. 신호2(일반도지)/9(고점도지)/
10(고점스피닝탑)을 전부 폐기하고 대체하는 통합 모듈.

모양 판정 (모든 비율은 캔들 범위 = 고가 - 저가 대비, 기준값은 아래 상수):
    몸통비율 = |종가-시가| / 범위, 위꼬리비율 = 위꼬리 / 범위, 아래꼬리비율 = 아래꼬리 / 범위
    망치형:   몸통비율 <= 35%  AND 위꼬리비율 <= 10%  AND 아래꼬리 >= 몸통 x 2
    역망치형: 몸통비율 <= 35%  AND 아래꼬리비율 <= 10%  AND 위꼬리 >= 몸통 x 2
    도지:     위 둘이 아니면서 몸통비율 <= 15%, 또는 15% < 몸통비율 <= 25%인데 당일 거래량 >= 직전 20일 평균거래량
              (당일 제외)의 1.5배. 도지는 대칭도 조건이 없다 - 망치형/역망치형 조건(꼬리 10%/배수)에 못 미치는
              몸통 15% 이하 캔들은 전부 도지가 된다.
    망치형/역망치형에는 도지의 거래량 조건을 적용하지 않는다. 고가 == 저가(범위 0)인 캔들은 모양 없음.
    (2026-10 이전에는 "대칭도 < 1/3이고 한쪽 꼬리가 더 길면 망치형/역망치형, 몸통 15~25%는 거래량 조건"이었다.)

고점 판정 (몸통만 사용, 꼬리는 안 씀):
    몸통 상단 = max(시가, 종가), 몸통 하단 = min(시가, 종가)
    고점 캔들: 당일 몸통 상단 >= 직전 N개 캔들 몸통 상단의 최댓값 (당일 제외, 동률 포함 - 2026-10 변경)
    N = POSITION_LOOKBACK_N. 처음 N개 캔들은 직전 N개가 없어 고점 캔들이 될 수 없다.

숏 신호 (모양이 도지/망치형/역망치형이면 - 모양 자체는 방향이 없다):
    고점 캔들 t가 모양이면 t에 신호. 아니면 t+1이 모양일 때 t+1에 신호("(다음 봉)" 표시, next_bar=True).
    둘 다 모양이면 t에서만(1번). t+1이 또 고점 캔들이면 t+1을 새 고점 캔들로 다시 판정(그 신호는 당일 신호).

롱 신호 (저점 판정 교체 - 2026-10):
    직전 캔들(t-1)이 음봉(종가 < 시가)이고 몸통 변화율 (시가-종가)/시가*100 >= LOW_PREV_BEAR_MIN_PCT 이며
    오늘(t) 캔들이 모양이면 t에 롱 신호. 롱에는 다음 봉 규칙이 없다(next_bar는 항상 False).
    예전의 "몸통 신저점 저점 캔들(직전 N개 몸통 하단의 최솟값보다 낮음) + 다음 봉" 판정 코드는 지우지 않고 남겨 뒀다
    (USE_BODY_NEW_LOW_FOR_LONG=False로 미사용, True로 바꾸면 예전 롱 판정으로 돌아간다).

같은 캔들에서 숏(고점 규칙)과 롱(저점 규칙)이 동시에 나면 둘 다 낸다(롱 -> 숏 순서).

무효 ("장대봉 무효" - 예전 "시세분출 무효"를 장대봉 포함, 양방향으로 확장):
    장대봉: 몸통 변화율 |종가-시가|/시가*100 >= BIG_CANDLE_MIN_PCT (양봉/음봉 구분)
    급등/급락(시세분출): 직전 N봉(N=3,4)의 (종가[t-1]-시가[t-N])/시가[t-N]*100/N 이 +CUM_PCT_PER_N_MIN 이상이면 급등,
        -CUM_PCT_PER_N_MIN 이하이면 급락 (volatility_expansion.py의 기준 4%/봉, 3봉 12% / 4봉 16%, 하락은 대칭)
    신호 캔들 i에서 직전 BIG_CANDLE_SUPPRESS_BARS봉 안에 아래 원인이 있으면 신호를 "무효"(reference, 카운트 제외)로 바꾼다:
        숏 신호 <- 상승 장대봉(i-K..i-1 중 하나) 또는 급등(윈도가 i-K..i-1에서 끝남)   (K = BIG_CANDLE_SUPPRESS_BARS)
        롱 신호 <- 하락 장대봉 또는 급락
    무효 문구에 원인을 표시: "{모양} - 롱 무효 (장대 음봉 10/20)", "{모양} - 숏 무효 (급등 3봉 10/17~10/19)".
    장대봉이 급등보다 우선해서 표시된다. 다음 봉 숏 신호는 뒤에 " (다음 봉)"이 붙는다.

표시: "{모양} - 롱 후보"/"{모양} - 숏 후보"(카운트됨), 다음 봉 신호는 뒤에 " (다음 봉)".
    신호가 하나도 안 난 모양 캔들에는 "{모양} - 참고 (고점/저점 아님)"(reference, 카운트 제외, near_zone 부착)을 낸다.
    같은 캔들에 신호(무효 포함)가 났으면 참고는 안 낸다. feature_flags.ENABLE_CANDLE_REFERENCE=False로 끌 수 있다.

미래 참조 없음: 모든 판정은 해당 신호 캔들 마감 시점까지의 정보만 쓴다(t+1 신호는 t+1 마감 값).
위치판정에 스윙저점/고점은 쓰지 않는다 (확정 지연으로 인한 미래참조 위험).

규칙 상수 목록 (모두 이 파일 상단):
    POSITION_LOOKBACK_N = 10          고점 판정에 쓰는 직전 캔들 수
    LOW_PREV_BEAR_MIN_PCT = 0.0       롱: 직전 음봉의 최소 몸통 변화율(%)
    USE_BODY_NEW_LOW_FOR_LONG = False 미사용 - 예전 몸통 신저점 롱 판정(다음 봉 포함)을 되살리는 스위치
    BIG_CANDLE_MIN_PCT = 3.5          장대봉 기준 몸통 변화율(%)
    BIG_CANDLE_SUPPRESS_BARS = 2      장대봉/급등락 후 신호를 무효로 만드는 봉 수
    SURGE_WINDOWS = (3, 4), SURGE_CUM_PCT_PER_N_MIN = 4.0   급등/급락 판정 (volatility_expansion.py와 같은 값)
    모양 기준: BODY_MAX_PCT / BODY_EXT_MAX_PCT / HAMMER_* / VOLUME_*  (위 모양 판정 참고)
제거된 예전 조건(함수/상수는 남겨 둠, 판정엔 안 씀): N봉(1~5) 누적등락률 ±8%, EMA50/EMA200 터치 방향, 수평선/추세선 근접 방향.

이 모듈의 신호 계산은 app.py의 언캐시드 경로에서 호출된다(pipeline.py의 build_signals_by_date 캐시 흐름 밖).

번호(참고용, app.py 표시 순서): 9.도지롱 10.도지숏 11.망치형롱 12.망치형숏 13.역망치형롱 14.역망치형숏
"""
from dataclasses import dataclass

import pandas as pd

import feature_flags
import volatility_expansion
from signal_types import Signal

BODY_MAX_PCT = 0.15       # 도지: 몸통비율 상한
BODY_EXT_MAX_PCT = 0.25   # 도지 확장구간 상한(15~25%) - 거래량 조건 만족 시만 도지 인정
HAMMER_BODY_MAX_PCT = 0.35         # 망치형/역망치형: 몸통비율 상한
HAMMER_OPPOSITE_WICK_MAX_PCT = 0.10  # 망치형은 위꼬리, 역망치형은 아래꼬리 비율 상한
HAMMER_WICK_BODY_MULT = 2          # 긴 꼬리(망치형은 아래꼬리) >= 몸통 x 이 배수
VOLUME_LOOKBACK = 20      # 확장구간 판정용 평균거래량 계산 기간
VOLUME_RATIO_MIN = 1.5    # 확장구간 진입에 필요한 거래량 배수(직전 20일 평균 대비)
TREND_PCT = 8.0           # (미사용: 위치 판정 교체로 제거된 N봉 추세 조건)
TREND_N_RANGE = range(1, 6)  # (미사용)

# 고점 캔들 판정에 쓰는 직전 캔들 수 N - 여기 한 곳만 바꾸면 된다.
POSITION_LOOKBACK_N = 10

# 롱(저점) 판정: 직전 캔들이 음봉이고 몸통 변화율 (시가-종가)/시가*100 이 이 값 이상이어야 한다.
LOW_PREV_BEAR_MIN_PCT = 0.0
# 미사용: True면 예전 롱 판정(몸통 신저점 저점 캔들 + 다음 봉 규칙)을 쓰고 위 직전 음봉 규칙은 건너뛴다.
USE_BODY_NEW_LOW_FOR_LONG = False

# 장대봉/급등락 무효
BIG_CANDLE_MIN_PCT = 3.5     # 장대봉: 몸통 변화율 |종가-시가|/시가*100 이 이 값 이상
BIG_CANDLE_SUPPRESS_BARS = 2  # 장대봉/급등락 후 이 봉 수 동안 반대 방향 신호를 무효로 만든다
SURGE_WINDOWS = volatility_expansion.WINDOWS                      # 급등/급락 판정 창(3, 4봉)
SURGE_CUM_PCT_PER_N_MIN = volatility_expansion.CUM_PCT_PER_N_MIN  # 봉당 누적 변화율 기준(4%)

REFERENCE_SUFFIX = "참고 (고점/저점 아님)"   # 위치 조건을 못 채운 모양 캔들의 참고 문구

PATTERN_LABEL_KR = {
    "doji": "도지",
    "hammer": "망치형",
    "inverted_hammer": "역망치형",
}


@dataclass(frozen=True)
class ShapeParams:
    """모양 판정 기준값 묶음. compute_candle_shape(df, params)에 넘기면 그 값으로 판정한다(주봉처럼 다른 기준을 쓰는 쪽용).
    안 넘기면 default_shape_params() - 호출 시점의 모듈 상수(일봉 기준)로 만든다."""
    body_max: float             # 도지: 몸통비율 상한
    body_ext_max: float         # 도지 확장구간 상한(거래량 조건)
    hammer_body_max: float      # 망치형/역망치형 몸통비율 상한
    hammer_opposite_wick_max: float  # 반대쪽 꼬리비율 상한
    hammer_wick_body_mult: float     # 긴 꼬리 >= 몸통 x 배수
    volume_lookback: int        # 확장구간 평균거래량 기간(봉 수)
    volume_ratio_min: float     # 확장구간 거래량 배수


def default_shape_params() -> ShapeParams:
    """현재 모듈 상수(일봉 기준)로 만든 기본 기준값. 호출 시점에 읽으므로 테스트가 모듈 상수를 바꿔도 따라간다."""
    return ShapeParams(
        body_max=BODY_MAX_PCT, body_ext_max=BODY_EXT_MAX_PCT, hammer_body_max=HAMMER_BODY_MAX_PCT,
        hammer_opposite_wick_max=HAMMER_OPPOSITE_WICK_MAX_PCT, hammer_wick_body_mult=HAMMER_WICK_BODY_MULT,
        volume_lookback=VOLUME_LOOKBACK, volume_ratio_min=VOLUME_RATIO_MIN,
    )


def compute_candle_shape(df: pd.DataFrame, params: ShapeParams | None = None) -> pd.DataFrame:
    params = default_shape_params() if params is None else params
    df = df.reset_index(drop=True).copy()

    body = (df["close"] - df["open"]).abs()
    candle_range = df["high"] - df["low"]
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    nonzero_range = candle_range != 0
    body_ratio = pd.Series(0.0, index=df.index)
    upper_wick_ratio = pd.Series(0.0, index=df.index)
    lower_wick_ratio = pd.Series(0.0, index=df.index)
    body_ratio[nonzero_range] = body[nonzero_range] / candle_range[nonzero_range]
    upper_wick_ratio[nonzero_range] = upper_wick[nonzero_range] / candle_range[nonzero_range]
    lower_wick_ratio[nonzero_range] = lower_wick[nonzero_range] / candle_range[nonzero_range]

    # 확장구간(몸통 15~25%) 도지 판정용 거래량배수 - 당일 자신은 평균에서 제외(shift(1))
    # 해서 순수 과거 20일 평균과만 비교(미래참조 아님). 앞 20봉은 자연히 NaN.
    avg_volume = df["volume"].shift(1).rolling(params.volume_lookback).mean()
    volume_ratio = df["volume"] / avg_volume

    shape = pd.Series([None] * len(df), dtype=object)
    for i in df.index:
        if not nonzero_range.iloc[i]:
            continue  # 고가 == 저가: 비율을 정의할 수 없음
        br = body_ratio.iloc[i]
        uw, lw = upper_wick_ratio.iloc[i], lower_wick_ratio.iloc[i]

        # 망치형/역망치형 - 거래량 조건 없음. 두 조건이 동시에 성립하는 캔들은 없다(몸통+두 꼬리 = 범위).
        if br <= params.hammer_body_max:
            if uw <= params.hammer_opposite_wick_max and lw >= params.hammer_wick_body_mult * br:
                shape.iloc[i] = "hammer"
                continue
            if lw <= params.hammer_opposite_wick_max and uw >= params.hammer_wick_body_mult * br:
                shape.iloc[i] = "inverted_hammer"
                continue

        # 도지 - 위 둘이 아닌 것 중 몸통 15% 이하(15~25%는 거래량 조건)
        if br > params.body_ext_max:
            continue
        if br > params.body_max:
            vr = volume_ratio.iloc[i]
            if not (pd.notna(vr) and vr >= params.volume_ratio_min):
                continue
        if max(uw, lw) == 0:
            continue  # 두 꼬리 다 0(사실상 점) - 판정 제외
        shape.iloc[i] = "doji"

    df["body_ratio"] = body_ratio
    df["upper_wick_ratio"] = upper_wick_ratio
    df["lower_wick_ratio"] = lower_wick_ratio
    df["volume_ratio"] = volume_ratio
    df["shape"] = shape
    return df


def _cum_return(close: pd.Series, t: int, N: int):
    if t - 1 - N < 0:
        return None
    c_prev = close.iloc[t - 1]
    c_before = close.iloc[t - 1 - N]
    if c_before == 0:
        return None
    return (c_prev - c_before) / c_before * 100


def _compute_nbar_trend(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """N=1~5 중 하나라도 -8%/+8%를 만족하면 True (down/up 각각)."""
    n = len(df)
    close = df["close"]
    down_nbar = pd.Series(False, index=df.index)
    up_nbar = pd.Series(False, index=df.index)
    for t in range(n):
        for N in TREND_N_RANGE:
            r = _cum_return(close, t, N)
            if r is None:
                continue
            if r <= -TREND_PCT:
                down_nbar.iloc[t] = True
            if r >= TREND_PCT:
                up_nbar.iloc[t] = True
    return down_nbar, up_nbar


def _volatility_expansion_matches(vol_exp_df: pd.DataFrame, i: int) -> list[dict]:
    """(미사용 - 2026-10부터 _surge_matches가 급등/급락 양방향을 직접 계산한다) i번째 캔들이 걸린 시세 분출 창(N) 목록. pipeline.py의 동명 헬퍼와 동일 로직
    (volatility_expansion.py 자체는 안 건드리고, 그 결과를 소비하는 패턴만 복제)."""
    matches = []
    for window in volatility_expansion.WINDOWS:
        if vol_exp_df[f"expansion_{window}"].iloc[i]:
            matches.append({
                "n": window,
                "cum_pct": vol_exp_df[f"cum_pct_{window}"].iloc[i],
                "cum_pct_per_n": vol_exp_df[f"cum_pct_per_n_{window}"].iloc[i],
            })
    return matches


def _near_zone_flags(df: pd.DataFrame, zones: list) -> list:
    """캔들별로 고가~저가 범위가 존과 조금이라도 겹치는지(low <= 상단 and high >= 하단).
    존의 유효 범위는 zone_signals.py와 같다: time1 <= 날짜 <= time2 (time2 이후 캔들은 근처 아님)."""
    n = len(df)
    flags = [False] * n
    dates = df["open_time"].dt.strftime("%Y-%m-%d").tolist()
    highs, lows = df["high"].tolist(), df["low"].tolist()
    for z in zones:
        if z.get("line_type") != "zone" or z.get("time1") is None or z.get("price2") is None:
            continue
        top, bottom = max(z["price1"], z["price2"]), min(z["price1"], z["price2"])
        for i in range(n):
            if not flags[i] and z["time1"] <= dates[i] <= (z["time2"] or "9999-12-31") and lows[i] <= top and highs[i] >= bottom:
                flags[i] = True
    return flags


def _position_flags(df: pd.DataFrame, n_lookback: int) -> tuple[list, list]:
    """몸통 기준 (고점 캔들, 저점 캔들) 플래그.
    고점: 몸통 상단 >= 직전 n개 몸통 상단 최댓값(동률 포함). 저점: 몸통 하단 < 직전 n개 몸통 하단 최솟값(엄격) -
    저점 플래그는 예전 롱 판정용이라 지금은 USE_BODY_NEW_LOW_FOR_LONG=True일 때만 쓰인다(미사용)."""
    n = len(df)
    top = df[["open", "close"]].max(axis=1).tolist()
    bottom = df[["open", "close"]].min(axis=1).tolist()
    is_high = [False] * n
    is_low = [False] * n
    for t in range(n_lookback, n):
        is_high[t] = top[t] >= max(top[t - n_lookback:t])
        is_low[t] = bottom[t] < min(bottom[t - n_lookback:t])
    return is_high, is_low


def _body_pct(df: pd.DataFrame) -> list:
    """몸통 변화율 |종가-시가|/시가*100 (시가 0이면 0)."""
    op, cl = df["open"].tolist(), df["close"].tolist()
    return [abs(c - o) / o * 100 if o else 0.0 for o, c in zip(op, cl)]


def _surge_matches(df: pd.DataFrame) -> dict:
    """급등/급락(시세분출) 판정: {"up": {j: [(창, 누적%, 봉당%), ...]}, "down": {...}}.
    j번째 캔들 기준으로 직전 N봉 [j-N, j-1]의 (종가[j-1]-시가[j-N])/시가[j-N]*100 / N 이 +기준 이상이면 급등,
    -기준 이하이면 급락. volatility_expansion.py의 급등 판정과 같은 식이고 하락 방향을 대칭으로 더했다."""
    n = len(df)
    op, cl = df["open"].tolist(), df["close"].tolist()
    out = {"up": {}, "down": {}}
    for window in SURGE_WINDOWS:
        for j in range(window, n):
            start_open = op[j - window]
            if not start_open:
                continue
            pct = (cl[j - 1] - start_open) / start_open * 100
            per_n = pct / window
            if per_n >= SURGE_CUM_PCT_PER_N_MIN:
                out["up"].setdefault(j, []).append((window, pct, per_n))
            elif per_n <= -SURGE_CUM_PCT_PER_N_MIN:
                out["down"].setdefault(j, []).append((window, pct, per_n))
    return out


def compute_candle_pattern_signals(
    df: pd.DataFrame, manual_signals: dict | None = None, invalidated_log: list | None = None,
    zones: list | None = None, n_lookback: int | None = None,
) -> dict:
    """모양(도지/망치형/역망치형) x 방향(롱/숏) 신호 - 규칙은 모듈 docstring 참고.

    df: open_time/open/high/low/close/volume 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    manual_signals: 호출부 호환용으로만 남긴 인자 - 선 근접 조건이 일시 제거돼 지금은 쓰이지 않는다.
    zones: lines_store.list_lines()의 결과를 넘기면 모든 캔들 패턴 신호에 near_zone(True/False)을 채운다
        (신호가 나는 캔들 기준). 표시용 플래그일 뿐 판정에는 영향이 없다. 안 넘기면 None.
    invalidated_log: 리스트를 넘기면 무효로 바뀐 신호(숏/롱 모두)가 원인과 함께 기록된다.
    n_lookback: 고점 판정 N. 안 넘기면 POSITION_LOOKBACK_N.

    반환: {row_index: [Signal("도지 - 롱 후보", "long", next_bar=False), ...]}
    """
    n_lookback = POSITION_LOOKBACK_N if n_lookback is None else n_lookback
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    shape_df = compute_candle_shape(df)
    shapes = shape_df["shape"].tolist()
    near_flags = _near_zone_flags(df, zones) if zones is not None else None
    is_high, is_low = _position_flags(df, n_lookback)
    op, cl = df["open"].tolist(), df["close"].tolist()
    md = df["open_time"].dt.strftime("%m/%d").tolist()

    # --- 신호 후보: (신호 캔들 i, 방향) -> next_bar(True면 고점 캔들의 다음 봉에서 난 신호)
    events: dict[tuple[int, str], bool] = {}
    for t in range(n):                                  # 숏: 고점 캔들 당일 또는 다음 봉
        if not is_high[t]:
            continue
        if shapes[t] is not None:
            events[(t, "short")] = False
        elif t + 1 < n and shapes[t + 1] is not None:
            # t+1이 또 고점 캔들이면 t+1 자신의 신호(당일)로 본다 - 같은 날 중복 신호가 안 생긴다
            events.setdefault((t + 1, "short"), not is_high[t + 1])
    if USE_BODY_NEW_LOW_FOR_LONG:                       # (미사용) 예전 롱: 몸통 신저점 저점 캔들 당일 또는 다음 봉
        for t in range(n):
            if not is_low[t]:
                continue
            if shapes[t] is not None:
                events[(t, "long")] = False
            elif t + 1 < n and shapes[t + 1] is not None:
                events.setdefault((t + 1, "long"), not is_low[t + 1])
    else:                                               # 롱: 직전 음봉 + 오늘 모양 -> 당일 (다음 봉 규칙 없음)
        for t in range(1, n):
            if shapes[t] is None or not op[t - 1] or cl[t - 1] >= op[t - 1]:
                continue
            if (op[t - 1] - cl[t - 1]) / op[t - 1] * 100 >= LOW_PREV_BEAR_MIN_PCT:
                events[(t, "long")] = False

    # --- 무효 원인 (장대봉 / 급등락)
    body_pct = _body_pct(df)
    surge = _surge_matches(df)
    suppress_bars = BIG_CANDLE_SUPPRESS_BARS

    def find_cause(i: int, side: str):
        """side: 'up'(숏을 막는 상승 원인) / 'down'(롱을 막는 하락 원인). (설명 문구, 로그용 급등락 매치 목록) 또는 None."""
        for j in range(i - 1, max(i - suppress_bars, 0) - 1, -1):          # 장대봉: i-K .. i-1 (가까운 것부터)
            if body_pct[j] >= BIG_CANDLE_MIN_PCT and (cl[j] > op[j] if side == "up" else cl[j] < op[j]):
                return f"장대 {'양봉' if side == 'up' else '음봉'} {md[j]}", []
        for j in range(i, i - suppress_bars, -1):                          # 급등락: 윈도가 i-K .. i-1에서 끝남(j = i-K+1 .. i)
            if j in surge[side]:
                matches = surge[side][j]
                window = matches[0][0]
                return f"{'급등' if side == 'up' else '급락'} {window}봉 {md[j - window]}~{md[j - 1]}", matches
        return None

    for i in range(n):
        shape = shapes[i]
        if shape is None:
            continue
        label = PATTERN_LABEL_KR[shape]
        near = None if near_flags is None else near_flags[i]
        emitted = False

        for direction in ("long", "short"):  # 같은 캔들에서는 롱 -> 숏 순서
            if (i, direction) not in events:
                continue
            next_bar = events[(i, direction)]
            suffix = " (다음 봉)" if next_bar else ""
            emitted = True
            word = "롱" if direction == "long" else "숏"
            cause = find_cause(i, "down" if direction == "long" else "up")
            if cause is None:
                signals[i].append(Signal(f"{label} - {word} 후보{suffix}", direction, near_zone=near, next_bar=next_bar))
                continue
            text, matches = cause
            if invalidated_log is not None:
                entries = matches or [(None, None, None)]
                for window, pct, per_n in entries:
                    invalidated_log.append({
                        "index": i,
                        "date": df["open_time"].iloc[i],
                        "signal_text": f"{label} - {word} 후보{suffix}",
                        "cause": text,
                        "n": window,
                        "cum_pct": pct,
                        "cum_pct_per_n": per_n,
                    })
            signals[i].append(Signal(f"{label} - {word} 무효 ({text}){suffix}", "reference", near_zone=near, next_bar=next_bar))

        # 신호가 안 된 모양 캔들의 "참고" 표시 (feature_flags.ENABLE_CANDLE_REFERENCE로 끌 수 있다)
        if not emitted and feature_flags.ENABLE_CANDLE_REFERENCE:
            signals[i].append(Signal(f"{label} - {REFERENCE_SUFFIX}", "reference", near_zone=near, next_bar=False))

    return signals
