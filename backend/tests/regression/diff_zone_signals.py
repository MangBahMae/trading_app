"""
존 신호 규칙 변경(time2에서 끝 -> time1부터 오른쪽 무한 연장) 전/후 신호 diff (읽기 전용).

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
    zones.append({"id": 9100, "line_type": "zone", "time1": "2026-09-01", "price1": 80500.0, "time2": "2026-09-10",
                  "price2": 79000.0, "created_at": "2026-10-27T00:00:00+00:00"})
    last = df["open_time"].iloc[-1].strftime("%Y-%m-%d")
    print(f"캔들 {len(df)}개, 마지막 {last}. 존 {len(zones)}개 (실제 DB는 읽기 전용, 마지막 1개는 합성)\n")

    dates = df["open_time"].dt.strftime("%Y-%m-%d")
    bad = 0
    for z in zones:
        b = old_zs.compute_zone_signals(df, [z])
        a = new_zs.compute_zone_signals(df, [z])
        print(f"--- 존 id={z['id']}: {z['time1']} ~ {z['time2']}, {z['price2']:,.0f}~{z['price1']:,.0f} (created {z['created_at'][:10]})")
        n_b = sum(len(v) for v in b.values())
        n_a = sum(len(v) for v in a.values())
        removed = added = 0
        for i in range(len(df)):
            tb = [(s.direction, s.text) for s in b[i]]
            ta = [(s.direction, s.text) for s in a[i]]
            if tb == ta:
                continue
            d = dates.iloc[i]
            flag = "" if d > z["time2"] else "  <-- !!! time2 이하인데 바뀜"
            bad += bool(flag)
            removed += len([x for x in tb if x not in ta]); added += len([x for x in ta if x not in tb])
            print(f"  {d} 전:{tb or '-'} 후:{ta or '-'}{flag}")
        print(f"  기존 {n_b}건 -> {n_a}건 (제거 {removed}, 추가 {added})\n")

    # 하류: 존 외 신호/캔들패턴은 변하지 않아야 함
    ms = manual_lines.compute_manual_line_signals(df, lines)
    print("수평선/추세선 신호, 캔들패턴 신호는 존 신호를 입력으로 쓰지 않는다:",
          "compute_candle_pattern_signals 입력 = 수동선 신호만")
    cp = candle_patterns.compute_candle_pattern_signals(df, ms)
    print(f"  (참고) 캔들패턴 신호 {sum(len(v) for v in cp.values())}건 - 존 코드 변경과 무관")
    print(f"\n요약: time2 이하 날짜에서 바뀐 건 {bad}건 {'(OK)' if bad == 0 else '!!!'}")


if __name__ == "__main__":
    main()
