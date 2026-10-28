"""
캔들 패턴 위치(고점/저점) 판정 "새 방식" vs 현재 방식 비교 (읽기 전용, 앱 코드는 수정하지 않는다).

새 위치 판정 (몸통만 사용, 꼬리 미사용):
- 몸통 상단 = max(시가, 종가), 몸통 하단 = min(시가, 종가)
- 고점 캔들: 당일 몸통 상단 > 직전 N개 캔들 몸통 상단의 최댓값 (당일 제외, 엄격 초과)
- 저점 캔들: 당일 몸통 하단 < 직전 N개 캔들 몸통 하단의 최솟값
- 숏 신호: 고점 캔들 t가 캔들 패턴(도지/망치형/역망치형)이면 t에 신호. 아니면 t+1이 패턴이면 t+1에 신호.
  둘 다 아니면 없음. 롱 신호는 저점 캔들 기준으로 대칭.
- 모양 판정은 candle_patterns.compute_candle_shape 그대로. EMA 터치 / N봉 ±8% / 선 근접 / 시세분출 필터는 쓰지 않는다.
- 애매한 경우: (1) t와 t+1이 둘 다 패턴이면 고점 캔들 t에서만 신호. (2) t+1이 또 고점 캔들이면 t+1을 새 고점 캔들로
  다시 판정한다(t+1이 패턴이면 t+1 당일 신호, 아니면 t+2를 본다).
- 미래 참조 없음: t+1 신호는 t+1 마감 시점까지의 정보만 쓴다(t+1의 모양, 고점 여부 모두 t+1 마감 값).

현재 방식 = dashboard가 내는 candle_patterns의 롱 후보/숏 후보 (시세분출 무효·참고는 후보가 아니므로 제외).
DB(manual_lines.db)는 sqlite 읽기 전용으로만 연다.

사용법: backend 디렉토리에서  .venv/Scripts/python tests/regression/compare_candle_position.py [출력파일]
"""
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "app" / "services"))

import pandas as pd  # noqa: E402

import candle_patterns  # noqa: E402
import manual_lines  # noqa: E402
import pipeline  # noqa: E402
import volatility_expansion  # noqa: E402

DB = REPO / "data" / "merged" / "manual_lines.db"
PATTERNS = ("도지", "망치형", "역망치형")
NAME = candle_patterns.PATTERN_LABEL_KR


def new_method_signals(df: pd.DataFrame, shape: pd.Series, n_lookback: int):
    """반환: [(i, 'long'|'short', 패턴이름, '당일'|'t+1')] - i는 신호가 나는 캔들."""
    n = len(df)
    top = df[["open", "close"]].max(axis=1).tolist()
    bot = df[["open", "close"]].min(axis=1).tolist()
    sh = shape.tolist()
    is_high = [False] * n
    is_low = [False] * n
    for t in range(n_lookback, n):
        is_high[t] = top[t] > max(top[t - n_lookback:t])
        is_low[t] = bot[t] < min(bot[t - n_lookback:t])

    out = set()
    for kind, flags in (("short", is_high), ("long", is_low)):
        for t in range(n):
            if not flags[t]:
                continue
            if sh[t] is not None:
                out.add((t, kind, NAME[sh[t]], "당일"))
            elif t + 1 < n and sh[t + 1] is not None:
                # t+1이 또 고점/저점 캔들이면 t+1 자신의 신호(당일)로 본다 - 같은 날 중복 신호가 안 생기게 한 줄로 합친다
                out.add((t + 1, kind, NAME[sh[t + 1]], "당일" if flags[t + 1] else "t+1"))
    return sorted(out), is_high, is_low


def main():
    out_lines = []

    def p(*a):
        out_lines.append(" ".join(str(x) for x in a))

    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    dates = df["open_time"].dt.strftime("%Y-%m-%d").tolist()
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    lines = [dict(r) for r in conn.execute("SELECT * FROM lines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY id")]
    conn.close()
    p(f"캔들 {len(df)}개 {dates[0]} ~ {dates[-1]} | DB 라인 {dict(Counter(l['line_type'] for l in lines))}"
      f" (선 근접 조건은 DB에 수평선/추세선이 없으면 0일)")

    shape = candle_patterns.compute_candle_shape(df)["shape"]
    manual = manual_lines.compute_manual_line_signals(df, lines)
    cur_sig = candle_patterns.compute_candle_pattern_signals(df, manual)
    current = set()          # (i, direction, 패턴)
    for i, v in cur_sig.items():
        for s in v:
            if s.direction in ("long", "short"):
                current.add((i, s.direction, s.text.split(" - ")[0]))
    ve = volatility_expansion.compute_volatility_expansion(df)["is_volatility_expansion"].tolist()

    def per_pattern(keys):
        c = Counter((pat, d) for _, d, pat in keys)
        return {pat: (c[(pat, "long")], c[(pat, "short")]) for pat in PATTERNS}

    def same_day_both(keys):
        by = defaultdict(set)
        for i, d, _ in keys:
            by[i].add(d)
        return sum(1 for v in by.values() if len(v) == 2)

    cur_keys = current
    p("\n" + "=" * 78 + "\n현재 방식 (롱 후보/숏 후보)\n" + "=" * 78)
    p("패턴별 (롱, 숏):", per_pattern(cur_keys), "| 합계", len(cur_keys), "| 같은 날 롱+숏 동시:", same_day_both(cur_keys))

    results = {}
    for N in (10, 20):
        sigs, is_high, is_low = new_method_signals(df, shape, N)
        new_keys = {(i, d, pat) for i, d, pat, _ in sigs}
        how = {(i, d, pat): h for i, d, pat, h in sigs}
        results[N] = (new_keys, how, is_high, is_low)
        p("\n" + "=" * 78 + f"\n새 방식 N={N}\n" + "=" * 78)
        p(f"고점 캔들 {sum(is_high)}개 / 저점 캔들 {sum(is_low)}개 (전체 캔들 {len(df)})")
        p("패턴별 (롱, 숏):", per_pattern(new_keys), "| 합계", len(new_keys), "| 같은 날 롱+숏 동시:", same_day_both(new_keys))
        h_cnt = Counter((d, h) for _, d, _, h in sigs)
        p(f"신호 시점: 숏 당일 {h_cnt[('short', '당일')]} / t+1 {h_cnt[('short', 't+1')]}, "
          f"롱 당일 {h_cnt[('long', '당일')]} / t+1 {h_cnt[('long', 't+1')]}")
        kept = cur_keys & new_keys
        removed = sorted(cur_keys - new_keys)
        added = sorted(new_keys - cur_keys)
        p(f"현재 후보와 겹침 {len(kept)}건 | 현재에만 있음(새 방식에서 빠짐) {len(removed)}건 | 새 방식에만 있음 {len(added)}건")
        shorts_hit = sum(1 for (i, d, _) in new_keys if d == "short" and ve[i])
        p(f"(참고) 새 숏 신호 중 시세분출 구간(현재 방식이면 무효 처리될 날) {shorts_hit}건")

        p(f"\n--- N={N}: 현재 후보인데 새 방식에서 빠진 날짜 ({len(removed)}건)")
        for i, d, pat in removed:
            p(f"  {dates[i]} {pat} {'롱' if d == 'long' else '숏'}")
        p(f"\n--- N={N}: 새 방식에서 새로 생긴 날짜 ({len(added)}건): 날짜 / 패턴 / 롱·숏 / 고점·저점 캔들 당일 or t+1")
        for i, d, pat in added:
            p(f"  {dates[i]} {pat} {'롱' if d == 'long' else '숏'} {how[(i, d, pat)]}")

    # 최근 1년 표
    cutoff = (pd.Timestamp(dates[-1]) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    p("\n" + "=" * 78 + f"\n최근 1년({cutoff} ~ {dates[-1]}) 신호 날짜 - 차트 확인용\n" + "=" * 78)
    p("날짜 | 패턴 | 방향 | N=10 | N=20 | 현재 후보")
    cur_by = {(i, d, pat) for (i, d, pat) in cur_keys}
    rows = set()
    for N in (10, 20):
        for (i, d, pat) in results[N][0]:
            rows.add((i, d, pat))
    for k in cur_keys:
        rows.add(k)
    for (i, d, pat) in sorted(rows):
        if dates[i] < cutoff:
            continue
        cells = []
        for N in (10, 20):
            keys, how, _, _ = results[N]
            cells.append(how[(i, d, pat)] if (i, d, pat) in keys else "-")
        p(f"{dates[i]} | {pat} | {'롱' if d == 'long' else '숏'} | {cells[0]} | {cells[1]} | {'O' if (i, d, pat) in cur_by else '-'}")

    text = "\n".join(out_lines)
    print(text)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
