"""--synthetic 개발 서버의 실제 HTTP 응답 검사. 브라우저 화면 검사와는 별도다."""
import json
from pathlib import Path
from urllib.request import urlopen

examples = []
for day in ('2022-01-06', '2022-01-07', '2022-01-08'):
    with urlopen(f'http://127.0.0.1:8000/api/rapid-drop?date={day}') as response:
        data = json.loads(response.read())
    assert data['data_source'] == 'synthetic_demo'
    examples.append({key: data[key] for key in ('date','data_source','market','support','signals','maintained_candidates')})
first = next(s for s in examples[0]['signals'] if s['type'] == 'first_brake_long')
assert examples[0]['market']['accelerating_down'] is True
assert any(s['type'] == 'acceleration_warning' for s in examples[0]['signals'])
assert examples[1]['maintained_candidates'][0]['id'] == first['id']
retest = next(s for s in examples[2]['signals'] if s['type'] == 'retest_long')
assert retest['previous_candidate_ids'] == [first['id']]
Path(__file__).with_name('results_v03').joinpath('synthetic_api_examples.json').write_text(
    json.dumps(dict(source='synthetic_demo', actual_manual_support=False, examples=examples), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('합성 실제 HTTP: 첫 후보+경고 / 유지 / 재지지 후보 연결 통과. 브라우저 합성 표시 검증은 아님.')
