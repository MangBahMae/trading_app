"""
캔들 패턴 위치 판정 교체(N봉 ±8%/EMA/선 근접 -> 고점/저점 캔들) 전/후 신호 diff (읽기 전용).

- 전: git HEAD의 candle_patterns.py(+signal_types.py)   후: 작업 트리. DB는 sqlite 읽기 전용.
- 패턴별 롱 후보/숏 후보/참고/시세분출 무효 건수, 후보가 사라진/새로 생긴 날짜(당일/다음 봉), 같은 날 롱+숏 건수.
사용법: backend 디렉토리에서  .venv/Scripts/python tests/regression/diff_candle_position.py [출력파일]
"""
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "app" / "services"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import candle_patterns as new_cp  # noqa: E402
import manual_lines  # noqa: E402
import pipeline  # noqa: E402
from diff_near_zone import load_head_candle_patterns  # noqa: E402

DB = REPO / "data" / "merged" / "manual_lines.db"
PATTERNS = ("도지", "망치형", "역망치형")
CATS = ("롱 후보", "숏 후보", "참고", "시세분출 무효")


def classify(sig_map, dates):
    """{(날짜, 패턴, 종류(접미사 제외))): next_bar} 와 종류별 카운터."""
    items = {}
    cnt = Counter()
    for i, v in sig_map.items():
        for s in v:
            name, kind = s.text.split(" - ")
            nb = kind.endswith("(다음 봉)")
            kind = kind.replace(" (다음 봉)", "")
            if kind.startswith("참고"):
                kind = "참고"  # "참고 (고점/저점 아님)" 문구 접미사는 종류 비교에서 뺀다
            items[(dates[i], name, kind)] = nb
            cnt[(name, kind)] += 1
    return items, cnt


def main():
    out = []
    p = lambda *a: out.append(" ".join(str(x) for x in a))  # noqa: E731
    old_cp = load_head_candle_patterns()
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    dates = df["open_time"].dt.strftime("%Y-%m-%d").tolist()
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    lines = [dict(r) for r in conn.execute("SELECT * FROM lines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY id")]
    conn.close()
    manual = manual_lines.compute_manual_line_signals(df, lines)
    p(f"캔들 {len(df)}개 {dates[0]} ~ {dates[-1]} | DB 라인 {dict(Counter(l['line_type'] for l in lines))} | N={new_cp.POSITION_LOOKBACK_N}")

    before = old_cp.compute_candle_pattern_signals(df, manual, zones=lines)
    after = new_cp.compute_candle_pattern_signals(df, manual, zones=lines)
    b_items, b_cnt = classify(before, dates)
    a_items, a_cnt = classify(after, dates)

    p("\n패턴별 건수 (전 -> 후)")
    for name in PATTERNS:
        p(f"  {name}: " + ", ".join(f"{c} {b_cnt[(name, c)]}->{a_cnt[(name, c)]}" for c in CATS))
    tot = lambda cnt, c: sum(cnt[(n, c)] for n in PATTERNS)  # noqa: E731
    p("  합계: " + ", ".join(f"{c} {tot(b_cnt, c)}->{tot(a_cnt, c)}" for c in CATS))

    def both(items):
        by = defaultdict(set)
        for (d, _, kind), _nb in items.items():
            if kind in ("롱 후보", "숏 후보"):
                by[d].add(kind)
        return sum(1 for v in by.values() if len(v) == 2)

    p(f"\n같은 날 롱+숏 후보 동시: {both(b_items)} -> {both(a_items)}")
    nb = Counter(kind for (_, _, kind), v in a_items.items() if v)
    p(f"다음 봉 신호: {dict(nb)} (후 전체 {sum(1 for v in a_items.values() if v)}건)")

    for kind in ("롱 후보", "숏 후보", "시세분출 무효"):
        bk = {k for k in b_items if k[2] == kind}
        ak = {k for k in a_items if k[2] == kind}
        p(f"\n[{kind}] 겹침 {len(bk & ak)} | 사라짐 {len(bk - ak)} | 새로 생김 {len(ak - bk)}")
        p("  사라진 날짜: " + ", ".join(f"{d} {n}" for d, n, _ in sorted(bk - ak)))
        p("  새로 생긴 날짜: " + ", ".join(f"{d} {n}{'(다음 봉)' if a_items[(d, n, k)] else ''}" for d, n, k in sorted(ak - bk)))

    # near_zone 부착 확인
    flat = [s for v in after.values() for s in v]
    p(f"\nnear_zone True {sum(1 for s in flat if s.near_zone)} / False {sum(1 for s in flat if s.near_zone is False)} / None "
      f"{sum(1 for s in flat if s.near_zone is None)}; next_bar True {sum(1 for s in flat if s.next_bar)} / "
      f"False {sum(1 for s in flat if s.next_bar is False)} / None {sum(1 for s in flat if s.next_bar is None)}")
    text = "\n".join(out)
    print(text)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
