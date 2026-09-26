"""
scripts/pipeline.py(원본)과 backend/app/services/pipeline.py(이식본)이 완전히
동일한 결과(캔들 수, OHLCV+EMA+RSI 수치, 날짜별 신호, 다이버전스 마커)를
만들어내는지 검증하는 회귀 테스트.

원본/이식본을 완전히 격리된 서브프로세스 2개로 각각 실행해서(이유는
regression/dump_pipeline_result.py 상단 docstring 참고) JSON으로 저장한 뒤
그 결과를 diff한다. 둘 다 저장소 루트의 같은 data/merged/*.parquet를 보므로
입력 데이터도 완전히 동일하다.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SERVICES_DIR = REPO_ROOT / "backend" / "app" / "services"
DUMP_SCRIPT = Path(__file__).resolve().parent / "regression" / "dump_pipeline_result.py"
OUTPUT_DIR = Path(__file__).resolve().parent / "regression" / "_output"


def _prime_shared_cache():
    """두 서브프로세스를 돌리기 전에 data/merged/*_dashboard.parquet 캐시를
    한 번 미리 채워둔다.

    이게 없으면(실제로 처음 겪은 문제): 캐시가 비어있을 때 원본/이식본 서브
    프로세스가 각각 독립적으로 Binance 실시간 API를 호출하는데, 그 시점에
    "오늘" 캔들이 아직 정산 중이면(장 마감 직후 짧은 기간 거래소 쪽 수치가
    미세 조정됨) 몇 초 간격으로 호출한 두 서브프로세스가 서로 다른 close/volume
    스냅샷을 받아서 실제로는 코드가 완전히 동일한데도 마지막 캔들 1건이 다르게
    나왔다.

    조사해보니 원인이 하나 더 있었다 - scripts/data_fetcher.py::ensure_fresh_data()의
    기존 버그(이식 대상 코드에 원래 있던 것, 이번에 발견): 캐시 파일이 아직 없을 때
    fetch_full_history()로 받아온 직후 "이미 최신"(latest_closed_open) 체크에 걸려
    early return 하는데, 그 return이 df.to_parquet() 저장 코드보다 먼저라서 캐시
    파일이 "한 번도" 디스크에 안 써진다. 그 결과 캐시가 영영 안 생기고, 호출할
    때마다 매번 Binance에서 2022년부터 전체를 다시 받아온다(이번 포팅과 무관한
    원본 버그 - 별도로 보고, 여기서 임의 수정하지 않음). 그래서 이 헬퍼가 받아온
    DataFrame을 직접 캐시 경로에 저장해 우회한다 - 이후 두 서브프로세스는 이미
    존재하는 캐시 파일을 읽고 "이미 최신"으로 판단해 재조회 없이 반환하므로,
    완전히 동일한(고정된) 데이터를 보게 된다.
    """
    proc = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, r'{SCRIPTS_DIR}'); "
            "from data_fetcher import ensure_fresh_data; import config; "
            "df = ensure_fresh_data(); "
            "config.DASHBOARD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True); "
            "df.to_parquet(config.DASHBOARD_CACHE_PATH, index=False)",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"캐시 프라이밍 실패\nstdout: {proc.stdout}\nstderr: {proc.stderr}"


@pytest.fixture(scope="module")
def original_and_ported_results():
    _prime_shared_cache()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    original_path = OUTPUT_DIR / "original.json"
    ported_path = OUTPUT_DIR / "ported.json"

    for source_dir, out_path in [(SCRIPTS_DIR, original_path), (SERVICES_DIR, ported_path)]:
        proc = subprocess.run(
            [sys.executable, str(DUMP_SCRIPT), str(source_dir), str(out_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 0, (
            f"{source_dir} 덤프 실패\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    with open(original_path, encoding="utf-8") as f:
        original = json.load(f)
    with open(ported_path, encoding="utf-8") as f:
        ported = json.load(f)

    return original, ported


def test_candle_count_and_range_match(original_and_ported_results):
    original, ported = original_and_ported_results
    assert original["candle_count"] == ported["candle_count"]
    assert original["first_date"] == ported["first_date"]
    assert original["last_date"] == ported["last_date"]


def test_candle_numeric_series_match_exactly(original_and_ported_results):
    original, ported = original_and_ported_results
    mismatches = []
    for o, p in zip(original["candles"], ported["candles"]):
        if o != p:
            mismatches.append((o["date"], o, p))
    assert not mismatches, f"{len(mismatches)}개 날짜에서 OHLCV/EMA/RSI 불일치: {mismatches[:5]}"


def test_signals_match_exactly(original_and_ported_results):
    original, ported = original_and_ported_results
    orig_signals = original["signals_by_date"]
    port_signals = ported["signals_by_date"]

    assert set(orig_signals.keys()) == set(port_signals.keys()), (
        f"신호가 있는 날짜 집합이 다름 - 원본에만: "
        f"{set(orig_signals) - set(port_signals)}, 이식본에만: {set(port_signals) - set(orig_signals)}"
    )

    mismatches = []
    for date in sorted(orig_signals.keys()):
        if orig_signals[date] != port_signals[date]:
            mismatches.append((date, orig_signals[date], port_signals[date]))

    assert not mismatches, f"{len(mismatches)}개 날짜에서 신호 불일치: {mismatches[:5]}"


def test_divergence_markers_match_exactly(original_and_ported_results):
    original, ported = original_and_ported_results
    assert original["divergence_markers"] == ported["divergence_markers"]


def test_total_signal_and_marker_counts(original_and_ported_results):
    """콘솔에서 눈으로 확인할 수 있게 총계도 출력."""
    original, ported = original_and_ported_results
    orig_count = sum(len(v) for v in original["signals_by_date"].values())
    port_count = sum(len(v) for v in ported["signals_by_date"].values())
    print(f"\n캔들 {original['candle_count']}개, 원본 신호 {orig_count}건 / 이식본 신호 {port_count}건")
    print(f"다이버전스 마커: 원본 {len(original['divergence_markers'])}건 / 이식본 {len(ported['divergence_markers'])}건")
    assert orig_count == port_count
