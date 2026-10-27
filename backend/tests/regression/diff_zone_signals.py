"""
존 신호 규칙 변경 전/후 신호 diff (읽기 전용). 4-1(time2에서 끝 -> 오른쪽 연장) 때 만들었고,
4-2(유동성 스윕 추가)에서는 스윕 변경분을 분류해 보여준다.

- 전: git HEAD의 zone_signals.py   후: 작업 트리의 zone_signals.py
- 실제 DB(manual_lines.db)는 sqlite 읽기 전용으로만 연다. 쓰지 않는다.
- 출력: 존별로 날짜별 변경 신호. time2 이하 날짜에서 바뀌면 버그. 수평선/추세선/캔들패턴 하류는 변하지 않아야 한다.
사용법: backend 디렉토리에서  .venv/Scripts/python tests/regression/diff_zone_signals.py
"""
import importlib.util
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "app" / "services"))

import candle_patterns  # noqa: E402
import manual_lines  # noqa: E402
import pipeline  # noqa: E402
import zone_signals as new_zs  # noqa: E402

DB = REPO / "data" / "merged" / "manual_lines.db"


def load_head():
    src = subprocess.run(["git", "show", "HEAD:backend/app/services/zone_signals.py"], capture_output=True,
                         check=True, cwd=REPO).stdout
    path = Path(tempfile.mkdtemp(prefix="zs_head_")) / "zone_signals_head.py"
    path.write_bytes(src)
    spec = importlib.util.spec_from_file_location("zone_signals_head", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    old_zs = load_head()
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    lines = [dict(r) for r in conn.execute("SELECT * FROM lines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY id")]
    conn.close()
    zones = [ln for ln in lines if ln["line_type"] == "zone"]
    # 실제 존 2개는 time2 이후 가격이 다시 오지 않아 diff가 0일 수 있다 - 연장 효과를 보이는 합성 존(메모리에서만) 추가
    for k, (t1, hi, lo) in enumerate([("2026-09-01", 80500.0, 79000.0), ("2025-06-01", 108000.0, 104000.0),
                                       ("2024-03-01", 66000.0, 62000.0)]):
        zones.append({"id": 9100 + k, "line_type": "zone", "time1": t1, "price1": hi, "time2": t1,
                      "price2": lo, "created_at": "2026-10-27T00:00:00+00:00"})
    last = df["open_time"].iloc[-1].strftime("%Y-%m-%d")
    print(f"캔들 {len(df)}개, 마지막 {last}. 존 {len(zones)}개 (실제 DB는 읽기 전용, id 9100~ 는 합성)\n")

    dates = df["open_time"].dt.strftime("%Y-%m-%d")
    O, H, L, C = (df[c].tolist() for c in ("open", "high", "low", "close"))
    bad = 0
    tally = {}
    for z in zones:
        b = old_zs.compute_zone_signals(df, [z])
        a = new_zs.compute_zone_signals(df, [z])
        top, bot = z["price1"], z["price2"]
        print(f"--- 존 id={z['id']}: {z['time1']} ~ {z['time2']}, {bot:,.0f}~{top:,.0f} (created {z['created_at'][:10]})")
        n_b = sum(len(v) for v in b.values())
        n_a = sum(len(v) for v in a.values())
        for i in range(len(df)):
            tb = [(s.direction, s.text) for s in b[i]]
            ta = [(s.direction, s.text) for s in a[i]]
            if tb == ta:
                continue
            d = dates.iloc[i]
            new_sweep = [t for _, t in ta if "스윕" in t]
            kind = "기타"
            if not new_sweep:
                kind = "!!! 스윕이 아닌데 바뀜"
                bad += 1
            elif tb:
                kind = "반응 대체"
            else:
                long_ = "지지 스윕" in new_sweep[0]
                open_in = (bot <= O[i] < top) if long_ else (bot < O[i] <= top)
                pc = C[i - 1] if i > 0 else None
                outside_side = (O[i] >= top) if long_ else (O[i] <= bot)
                not_first = outside_side and not (pc is not None and (pc > top if long_ else pc < bot))
                kind = ("신규-시가가 존 안" if open_in else "신규-첫 터치 아니라서" if not_first else "신규-기타")
            tally[kind] = tally.get(kind, 0) + 1
            print(f"  {d} [{kind}] 전:{tb or '-'} 후:{ta or '-'}  (O{O[i]:,.0f} H{H[i]:,.0f} L{L[i]:,.0f} C{C[i]:,.0f})")
        print(f"  기존 {n_b}건 -> {n_a}건")
        print()

    # 하류: 존 외 신호/캔들패턴은 변하지 않아야 함
    ms = manual_lines.compute_manual_line_signals(df, lines)
    print("수평선/추세선 신호, 캔들패턴 신호는 존 신호를 입력으로 쓰지 않는다:",
          "compute_candle_pattern_signals 입력 = 수동선 신호만")
    cp = candle_patterns.compute_candle_pattern_signals(df, ms)
    print(f"  (참고) 캔들패턴 신호 {sum(len(v) for v in cp.values())}건 - 존 코드 변경과 무관")
    print()
    print(f"요약: 분류별 건수 {tally}; 스윕이 아닌 변경 {bad}건 {'(OK)' if bad == 0 else '!!!'}")


if __name__ == "__main__":
    main()
