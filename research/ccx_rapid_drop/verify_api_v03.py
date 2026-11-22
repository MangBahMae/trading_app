"""임시 DB를 쓰는 --synthetic 개발 서버의 HTTP 응답을 검증한다."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18703)
    parser.add_argument('--output', type=Path, help='결과를 저장할 새 JSON 파일')
    args = parser.parse_args()
    days = {}
    for day in ('2022-01-06', '2022-01-07', '2022-01-08'):
        with urlopen(f'http://127.0.0.1:{args.port}/api/rapid-drop?date={day}', timeout=15) as response:
            data = json.load(response)
        assert data['data_source'] == 'synthetic_demo'
        days[day] = data
    first_day, bounce, retest_day = days.values()
    first, = [s for s in first_day['signals'] if s['type'] == 'manual_first_long']
    assert first_day['market']['phase'] == 'sharp_drop' and first_day['market']['accelerating_now']
    assert first in bounce['maintained_candidates']
    retest, = [s for s in retest_day['signals'] if s['type'] == 'manual_retest_long']
    assert retest['previous_candidate_ids'] == [first['id']]
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(days, stream, ensure_ascii=False, indent=2)
    print('합성 HTTP 검사 통과 · 수동 첫 후보와 추가 가속, 유지, 재시험 후보 연결')


if __name__ == '__main__':
    main()
