"""
추세선 신호 규칙 변경(선분 -> time1부터 오른쪽 무한 연장 + 돌파/이탈 신호 추가) 전/후 신호 diff (읽기 전용).

- 전(before): git HEAD의 manual_lines.py (임시 모듈로 로드)    후(after): 작업 트리의 manual_lines.py
- 실제 DB(manual_lines.db)는 sqlite 읽기 전용(mode=ro)으로만 연다 - 쓰지 않는다.
  DB에는 추세선이 없으므로 실제 스윙 고/저점으로 합성 추세선을 메모리에서 만들어 사용한다.
- 출력: (A) 실제 라인/존만 -> 수평선·존 신호 0 diff 증명(수동선 신호, 상태 신호, 하류 캔들패턴 신호 모두)
        (B) 합성 추세선별 날짜별 변경 신호: 근접 변경(선분 -> 연장), 신규 돌파/이탈
        (C) 합성 추세선 + 실제 라인 동시 사용 시 추세선 외 신호가 안 변했는지, 하류 캔들패턴 diff, 요약

사용법: python tests/regression/diff_manual_line_signals.py   (backend 디렉토리에서, .venv 파이썬)
"""
import importlib.util
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
SERVICES = BACKEND / "app" / "services"
sys.path.insert(0, str(SERVICES))

import pandas as pd  # noqa: E402

import candle_patterns  # noqa: E402
import manual_lines as new_ml  # noqa: E402
import pipeline  # noqa: E402
import swing_points  # noqa: E402

DB = REPO / "data" / "merged" / "manual_lines.db"
CREATED = "2026-10-27T00:00:00+00:00"


def load_head_module():
    src = subprocess.run(["git", "show", "HEAD:backend/app/services/manual_lines.py"], capture_output=True,
                         check=True, cwd=REPO).stdout
    path = Path(tempfile.mkdtemp(prefix="ml_head_")) / "manual_lines_head.py"
    path.write_bytes(src)
    spec = importlib.util.spec_from_file_location("manual_lines_head", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_real_lines():
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM lines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY id")]
    finally:
        conn.close()


def synthetic_trend_lines(df, per_kind=4):
    """실제 스윙 저점(오르는 지지선)/고점(내리는 저항선) 두 점으로 합성. 결정적으로 고르기 위해 균등 간격 표본."""
    sw = swing_points.find_swing_points(df)
    dates = df["open_time"].dt.strftime("%Y-%m-%d")
    out = []
    for kind, col, price_col, rising in (("지지", "swing_low", "low", True), ("저항", "swing_high", "high", False)):
        idx = list(sw.index[sw[col]])
        pairs = []
        for a, b in zip(idx, idx[1:]):
            gap = b - a
            pa, pb = float(df[price_col].iloc[a]), float(df[price_col].iloc[b])
            if 15 <= gap <= 80 and ((pb > pa) if rising else (pb < pa)):
                pairs.append((a, b))
        step = max(1, len(pairs) // per_kind)
        for a, b in pairs[::step][:per_kind]:
            out.append({"kind": kind, "line": {
                "id": 9000 + len(out), "line_type": "trend", "time1": dates.iloc[a],
                "price1": float(df[price_col].iloc[a]), "time2": dates.iloc[b],
                "price2": float(df[price_col].iloc[b]), "created_at": CREATED}})
    return out


def sig_key(s):
    return (s.direction, s.text, s.source, s.tier, tuple(s.evidence), s.ref_id, s.ref_created_at)


def flatten(sig_map, df):
    out = {}
    for i, lst in sig_map.items():
        for s in lst:
            out.setdefault(df["open_time"].iloc[i].strftime("%Y-%m-%d"), []).append(sig_key(s))
    return out


def diff_maps(before, after):
    """{date: ([only_before], [only_after])} - 같은 날 같은 신호 다중집합 비교."""
    res = {}
    for d in sorted(set(before) | set(after)):
        b, a = Counter(before.get(d, [])), Counter(after.get(d, []))
        ob, oa = list((b - a).elements()), list((a - b).elements())
        if ob or oa:
            res[d] = (ob, oa)
    return res


def compute_all(ml, df, lines):
    manual = ml.compute_manual_line_signals(df, lines) if lines else {}
    state = ml.compute_manual_line_state_signals(df, lines) if lines else {}
    cp = candle_patterns.compute_candle_pattern_signals(df, manual)
    return manual, state, cp


def short(k):
    return f"[{'롱' if k[0] == 'long' else '숏' if k[0] == 'short' else '참고'}] {k[1]}"


def main():
    old_ml = load_head_module()
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    real = read_real_lines()
    kinds = Counter(r["line_type"] for r in real)
    print(f"캔들 {len(df)}개 ({df['open_time'].iloc[0]:%Y-%m-%d} ~ {df['open_time'].iloc[-1]:%Y-%m-%d})")
    print(f"실제 DB 라인(읽기 전용): {dict(kinds)}  (추세선 {kinds.get('trend', 0)}개)\n")

    # ---------- (A) 실제 라인/존만: 0 diff 증명
    print("=" * 78 + "\n(A) 실제 라인/존만 - 변경 전/후 비교 (수평선·존은 0 diff여야 함)\n" + "=" * 78)
    ob = compute_all(old_ml, df, real)
    na = compute_all(new_ml, df, real)
    total_a = 0
    for name, b, a in zip(("수동선 신호", "수동선 상태 신호", "하류 캔들패턴 신호"), ob, na):
        d = diff_maps(flatten(b, df), flatten(a, df))
        total_a += len(d)
        n_sig = sum(len(v) for v in flatten(b, df).values())
        print(f"  {name}: 기존 {n_sig}건 -> 날짜별 diff {len(d)}일")
        for date, (x, y) in list(d.items())[:10]:
            print(f"    {date} 전:{[short(k) for k in x]} 후:{[short(k) for k in y]}")
    print(f"  => (A) 총 diff 일수: {total_a}  {'OK (0 diff)' if total_a == 0 else '!!! 수평선/존 동작이 바뀜'}\n")

    # ---------- (B) 합성 추세선별 diff
    synth = synthetic_trend_lines(df)
    print("=" * 78 + f"\n(B) 합성 추세선 {len(synth)}개별 diff (실제 DB 라인은 제외하고 추세선 1개씩만)\n" + "=" * 78)
    sum_prox_removed = sum_prox_added = sum_break = 0
    for s in synth:
        line = s["line"]
        bm, bs, _ = compute_all(old_ml, df, [line])
        am, as_, _ = compute_all(new_ml, df, [line])
        prox = diff_maps(flatten(bm, df), flatten(am, df))
        state = diff_maps(flatten(bs, df), flatten(as_, df))
        print(f"\n--- {s['kind']}선 id={line['id']}: {line['time1']} {line['price1']:.0f} -> {line['time2']} {line['price2']:.0f}"
              f"  (기울기 {(line['price2'] - line['price1']) / max(1, (pd.Timestamp(line['time2']) - pd.Timestamp(line['time1'])).days):+.1f}/일)")
        t2 = line["time2"]
        print(f"  근접 신호 변경 {len(prox)}일 (time2={t2} 이전은 선분 안쪽이라 같아야 함):")
        inside_diff = [d for d in prox if d <= t2]
        for date, (x, y) in prox.items():
            tag = "" if date > t2 else "  <-- !!! 선분 안쪽인데 바뀜"
            sum_prox_removed += len(x)
            sum_prox_added += len(y)
            print(f"    {date} 전:{[short(k) for k in x] or '-'} 후:{[short(k) for k in y] or '-'}{tag}")
        assert not inside_diff, "time1~time2 안쪽 근접 신호는 변하면 안 된다"
        n_enter = sum(1 for _, (x, y) in state.items() for k in y if k[1].endswith("진입"))
        print(f"  돌파/이탈 상태 신호(신규) {len(state)}일, 진입 {n_enter}건:")
        for date, (x, y) in state.items():
            assert not x, "기존 상태 신호가 사라지면 안 된다 (추세선은 원래 상태 신호가 없었음)"
            sum_break += len(y)
            print(f"    {date} 후:{[short(k).replace('추세선 ', '') for k in y]}")

    # ---------- (C) 합성 추세선 + 실제 라인 동시: 추세선 외 신호 불변
    print("\n" + "=" * 78 + "\n(C) 합성 추세선 전부 + 실제 라인 - 추세선이 아닌 신호는 변하지 않아야 함\n" + "=" * 78)
    all_lines = real + [s["line"] for s in synth]
    bm, bs, bc = compute_all(old_ml, df, all_lines)
    am, as_, ac = compute_all(new_ml, df, all_lines)

    def non_trend(m):
        return {d: [k for k in v if not k[1].startswith("추세선")] for d, v in flatten(m, df).items()}

    for name, b, a in (("수동선 신호", bm, am), ("상태 신호", bs, as_)):
        d = diff_maps({k: v for k, v in non_trend(b).items() if v}, {k: v for k, v in non_trend(a).items() if v})
        print(f"  {name} 중 추세선이 아닌 신호 diff: {len(d)}일  {'OK' if not d else '!!!'}")
    cpd = diff_maps(flatten(bc, df), flatten(ac, df))
    print(f"  하류 캔들패턴 신호 diff(추세선 근접 방향 변경이 캔들패턴 후보/참고 판정에 미친 영향): {len(cpd)}일")
    for date, (x, y) in cpd.items():
        print(f"    {date} 전:{[short(k) for k in x] or '-'} 후:{[short(k) for k in y] or '-'}")

    print("\n" + "=" * 78 + "\n요약\n" + "=" * 78)
    print(f"  (A) 실제 수평선/존 diff 일수: {total_a}")
    print(f"  (B) 근접 신호: 제거 {sum_prox_removed}건 / 추가 {sum_prox_added}건 (선분 밖 연장 구간),  신규 돌파·이탈 상태 신호 {sum_break}건")
    print(f"  (C) 하류 캔들패턴 diff 일수: {len(cpd)}")


if __name__ == "__main__":
    main()
