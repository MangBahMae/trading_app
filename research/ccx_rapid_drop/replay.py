"""로컬 CoinCloudX checkout의 일봉 fixture와 기존 캔들 모양 함수를 사용하는 읽기 전용 실행기."""
import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from rapid_drop import Bar, Config, Level, analyze


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, type=Path, help='신뢰하는 CoinCloudX checkout 경로')
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--levels', type=Path, help='당시 이용 가능했던 지지 구간 버전 JSON 목록. 생략 시 []')
    args = p.parse_args()
    repo = args.repo.resolve()
    # 운영 API, DB, 시세 수집, 기존 신호 파이프라인을 호출하지 않는다.
    services = repo / 'backend/app/services'
    fixture = repo / 'backend/tests/fixtures/BTCUSDT_1d_2022-01-01_2026-10-28.csv'
    if not (services/'candle_patterns.py').is_file() or not fixture.is_file():
        p.error('저장소 경로와 기준 일봉 fixture를 확인하세요.')
    import pandas as pd
    sys.path.insert(0, str(services))
    from candle_patterns import compute_candle_shape
    cfg = Config(**json.loads(args.config.read_text(encoding='utf-8')))
    raw = json.loads(args.levels.read_text(encoding='utf-8')) if args.levels else []
    levels = [Level(x['key'], x['bottom'], x['top'], date.fromisoformat(x['known_from']),
                    date.fromisoformat(x['through'])) for x in raw]
    frame = pd.read_csv(fixture)
    frame['open_time'] = pd.to_datetime(frame['open_time'], utc=True)
    # 이 실행기는 현재 진행 중인 봉이 없는 고정 fixture 전용이다.
    shaped = compute_candle_shape(frame)
    bars = [Bar(row.open_time.date(), row.open, row.high, row.low, row.close, row.volume,
                row.shape if isinstance(row.shape, str) else None) for row in shaped.itertuples()]
    for obs in analyze(bars, levels, cfg):
        print(json.dumps(asdict(obs), ensure_ascii=False, default=str, allow_nan=False))


if __name__ == '__main__':
    main()
