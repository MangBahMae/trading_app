"""
망치형/역망치형 "새 정의" vs 현재 정의 비교 (읽기 전용, 앱 코드는 수정하지 않는다).

새 정의 (모든 비율은 캔들 범위 = 고가 - 저가 대비, 꼬리 배수만 몸통 대비):
- 망치형: 몸통 <= 35%, 위꼬리 <= 10%, 아래꼬리 >= 몸통 x 2
- 역망치형: 몸통 <= 35%, 아래꼬리 <= 10%, 위꼬리 >= 몸통 x 2
- 도지: 몸통 <= 15% (15~25%는 기존대로 거래량 >= 직전 20일 평균 x 1.5 필요) 이면서 위 둘이 아닌 것
- 망치형/역망치형에는 거래량 조건을 적용하지 않는다. 도지의 두 꼬리가 모두 0인 캔들은 기존처럼 제외.
위치 판정(고점/저점 캔들, N=10)과 t+1 규칙은 현재 새 방식 그대로(compare_candle_position.new_method_signals).
비교 신호는 시세분출 필터를 적용하기 전 값이다(숏 중 시세분출 구간 건수는 따로 표시).

사용법: backend 디렉토리에서  .venv/Scripts/python tests/regression/compare_hammer_def.py [출력파일]
"""
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "app" / "services"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import candle_patterns  # noqa: E402
import pipeline  # noqa: E402
import volatility_expansion  # noqa: E402
from compare_candle_position import new_method_signals  # noqa: E402

N = candle_patterns.POSITION_LOOKBACK_N
NAME = candle_patterns.PATTERN_LABEL_KR
PATTERNS = ("도지", "망치형", "역망치형")


def new_shape_series(sh: pd.DataFrame) -> list:
    """compute_candle_shape()가 계산한 비율 컬럼(body/upper/lower/volume_ratio)으로 새 정의를 적용한다."""
    out = []
    for i in sh.index:
        br, uw, lw = sh["body_ratio"].iloc[i], sh["upper_wick_ratio"].iloc[i], sh["lower_wick_ratio"].iloc[i]
        vr = sh["volume_ratio"].iloc[i]
        if sh["high"].iloc[i] == sh["low"].iloc[i]:
            out.append(None)
            continue
        if br <= 0.35 and uw <= 0.10 and lw >= 2 * br:
            out.append("hammer")
        elif br <= 0.35 and lw <= 0.10 and uw >= 2 * br:
            out.append("inverted_hammer")
        elif br <= 0.15 or (br <= 0.25 and pd.notna(vr) and vr >= candle_patterns.VOLUME_RATIO_MIN):
            out.append(None if max(uw, lw) == 0 else "doji")
        else:
            out.append(None)
    return out


def main():
    out = []
    p = lambda *a: out.append(" ".join(str(x) for x in a))  # noqa: E731
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    dates = df["open_time"].dt.strftime("%Y-%m-%d").tolist()
    sh = candle_patterns.compute_candle_shape(df)
    cur = [None if x is None else x for x in sh["shape"].tolist()]
    new = new_shape_series(sh)
    p(f"캔들 {len(df)}개 {dates[0]} ~ {dates[-1]} | 위치 판정 N={N} (새 방식, 시세분출 필터 전)")

    def cnt(shapes):
        c = Counter(s for s in shapes if s)
        return {NAME[k]: c[k] for k in ("doji", "hammer", "inverted_hammer")}

    p("\n== 모양 캔들 수 (현재 정의 -> 새 정의)")
    cc, nc = cnt(cur), cnt(new)
    for name in PATTERNS:
        p(f"  {name}: {cc[name]} -> {nc[name]}")
    p(f"  합계: {sum(cc.values())} -> {sum(nc.values())}")
    trans = Counter((c, n) for c, n in zip(cur, new) if c != n)
    p("\n== 모양이 바뀐 캔들 (현재 -> 새)")
    for (c, n), v in sorted(trans.items(), key=lambda kv: -kv[1]):
        p(f"  {NAME.get(c, '없음')} -> {NAME.get(n, '없음')}: {v}")

    ve = volatility_expansion.compute_volatility_expansion(df)["is_volatility_expansion"].tolist()
    sig_cur, _, _ = new_method_signals(df, pd.Series(cur, dtype=object), N)
    sig_new, _, _ = new_method_signals(df, pd.Series(new, dtype=object), N)

    def per(sigs):
        c = Counter((pat, d) for _, d, pat, _ in sigs)
        return {pat: (c[(pat, "long")], c[(pat, "short")]) for pat in PATTERNS}

    p("\n== 위치 판정(새 방식) 신호 수 (롱, 숏): 현재 모양 정의 -> 새 모양 정의")
    pc, pn = per(sig_cur), per(sig_new)
    for name in PATTERNS:
        p(f"  {name}: {pc[name]} -> {pn[name]}")
    p(f"  합계: 롱 {sum(v[0] for v in pc.values())} 숏 {sum(v[1] for v in pc.values())} -> "
      f"롱 {sum(v[0] for v in pn.values())} 숏 {sum(v[1] for v in pn.values())}")
    p(f"  (참고) 숏 중 시세분출 구간: {sum(1 for i, d, _, _ in sig_cur if d == 'short' and ve[i])} -> "
      f"{sum(1 for i, d, _, _ in sig_new if d == 'short' and ve[i])}")
    keys_cur = {(i, d, pat) for i, d, pat, _ in sig_cur}
    keys_new = {(i, d, pat) for i, d, pat, _ in sig_new}
    p(f"  겹침 {len(keys_cur & keys_new)} | 현재 정의에만 {len(keys_cur - keys_new)} | 새 정의에만 {len(keys_new - keys_cur)}")

    def row(i):
        o, h, l, c = (df[k].iloc[i] for k in ("open", "high", "low", "close"))
        return (f"{dates[i]} O{o:,.0f} H{h:,.0f} L{l:,.0f} C{c:,.0f} | 몸통 {sh['body_ratio'].iloc[i]*100:.0f}% "
                f"위꼬리 {sh['upper_wick_ratio'].iloc[i]*100:.0f}% 아래꼬리 {sh['lower_wick_ratio'].iloc[i]*100:.0f}% "
                f"거래량배수 {sh['volume_ratio'].iloc[i]:.2f}")

    sig_cur_days = {(i, pat) for i, _, pat, _ in sig_cur}
    sig_new_days = {(i, pat) for i, _, pat, _ in sig_new}
    for key, label in (("hammer", "망치형"), ("inverted_hammer", "역망치형")):
        removed = [i for i in range(len(df)) if cur[i] == key and new[i] != key]
        added = [i for i in range(len(df)) if new[i] == key and cur[i] != key]
        p("\n" + "=" * 78 + f"\n{label}: 빠진 캔들 {len(removed)} / 새로 들어온 캔들 {len(added)}\n" + "=" * 78)
        p(f"--- {label}에서 빠진 캔들 (현재 -> 새 모양, 신호 여부는 현재 정의/새 정의)")
        for i in removed:
            p(f"  {row(i)} | -> {NAME.get(new[i], '없음')} | 신호 {'O' if (i, label) in sig_cur_days else '-'}/"
              f"{'O' if (i, NAME.get(new[i], '')) in sig_new_days else '-'}")
        p(f"--- {label}로 새로 들어온 캔들 (현재 모양 -> 새 모양)")
        for i in added:
            p(f"  {row(i)} | {NAME.get(cur[i], '없음')} -> | 신호 "
              f"{'O' if (i, NAME.get(cur[i], '')) in sig_cur_days else '-'}/{'O' if (i, label) in sig_new_days else '-'}")

    cutoff = (pd.Timestamp(dates[-1]) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    p("\n" + "=" * 78 + f"\n최근 1년({cutoff} ~ {dates[-1]}) 신호 날짜 - 차트 확인용 (위치 판정 N={N})\n" + "=" * 78)
    p("날짜 | 현재 정의 신호 | 새 정의 신호  (패턴 롱/숏 당일·t+1)")
    how_cur = {(i, d): (pat, h) for i, d, pat, h in sig_cur}
    how_new = {(i, d): (pat, h) for i, d, pat, h in sig_new}
    fmt = lambda v: "-" if v is None else f"{v[0]} {h2(v[1])}"  # noqa: E731
    h2 = lambda h: h  # noqa: E731
    for i, d in sorted(set(how_cur) | set(how_new)):
        if dates[i] < cutoff:
            continue
        p(f"{dates[i]} {'롱' if d == 'long' else '숏'} | {fmt(how_cur.get((i, d)))} | {fmt(how_new.get((i, d)))}")

    text = "\n".join(out)
    print(text)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
