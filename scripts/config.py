"""
대시보드/데이터 파이프라인 공통 설정.

지금은 BTCUSDT/1d만 지원하지만, 나중에 다른 심볼/타임프레임을 추가할 때
이 파일의 값만 바꾸면 되도록 분리해둔다 (하드코딩 지양).
"""
from pathlib import Path

SYMBOL = "BTCUSDT"
INTERVAL = "1d"
HISTORY_START = "2022-01-01"  # 최초 적재 시 이 날짜부터 Binance API로 전부 받아옴

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MERGED_DIR = DATA_DIR / "merged"

# 대시보드 전용 캐시 (zip 기반 초기 적재 + Binance API 증분 갱신 결과를 저장)
# 기존 scripts/*.py들이 쓰는 data/merged/BTCUSDT_1d.parquet와는 별개 파일 -
# 그 스크립트들의 독립적인 CLI 검증 워크플로를 건드리지 않기 위함.
DASHBOARD_CACHE_PATH = MERGED_DIR / f"{SYMBOL}_{INTERVAL}_dashboard.parquet"

# 일봉 기준 하루에 한 번 갱신이면 충분 (새 캔들은 매 UTC 자정에 마감)
INTERVAL_TO_PANDAS_FREQ = {
    "1d": "1D",
    "4h": "4h",
    "1h": "1h",
}
