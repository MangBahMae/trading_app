"""PR #2 기준 코드와 현재 코드의 기존 일봉·주봉·상승·급락 출력을 독립 실행해 비교한다."""
from argparse import ArgumentParser
from contextlib import nullcontext
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

BASE = '5caf1b344701ee42b238d7ff6baa75c277cc5f92'
ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def existing_outputs(tree):
    sys.path.insert(0, str(tree / 'research/rise_response'))
    from validation import isolated, journal, rise_response, rapid_drop_signals, dashboard
    from fastapi.testclient import TestClient
    from app.main import app

    results = {}
    for case in ('fixed', 'support_fail', 'trendline'):
        with isolated(case) as frame:
            client = TestClient(app)
            query = {'date': frame.open_time.iloc[-1].date().isoformat()}
            experiment = (patch.object(dashboard.feature_flags, 'ENABLE_BREAKOUT_RETEST', True)
                          if tree == ROOT else nullcontext())
            with experiment:
                if tree == ROOT:
                    client.get('/api/breakout-retest', params=query).raise_for_status()
                endpoints = {}
                for path in ('dashboard', 'dashboard/weekly', 'rise-response', 'rapid-drop'):
                    response = client.get('/api/' + path, params=query)
                    response.raise_for_status()
                    endpoints[path] = digest(response.json())
                versions = journal.load_drawing_versions(query['date'])['versions']
                rise = rise_response.build_timeline(frame, versions)
                levels = [rapid_drop_signals.engine().Level(
                    v['key'], v['bottom'], v['top'], date.fromisoformat(v['known_from']),
                    date.fromisoformat(v['through']), v['support_id'])
                    for v in journal.load_levels(query['date'])['levels']]
                drop = rapid_drop_signals.build_timeline(frame, levels)
                history = []
                for state in drop.values():
                    history.extend(state['signals'])
                    assert state.pop('history') == history
                results[case] = dict(bars=len(frame), api=endpoints, rise=digest(rise), drop=digest(drop))
    return results


def execute(tree):
    run = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--tree', str(tree)],
                         stdout=subprocess.PIPE, check=True, text=True)
    return json.loads(run.stdout)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path)
    args = parser.parse_args()
    if args.tree:
        print(json.dumps(existing_outputs(args.tree)))
    else:
        paths = ['backend/app', 'backend/tests/fixtures', 'backend/tests/golden_support.py',
                 'backend/tests/rise_support_examples.py', 'research/rise_response/validation.py',
                 'research/ccx_rapid_drop/rapid_drop.py', 'research/ccx_rapid_drop/example_config.json']
        with TemporaryDirectory(prefix='ccx-breakout-legacy-') as tmp:
            work = Path(tmp)
            archive = work / 'baseline.zip'
            subprocess.run(['git', 'archive', '--format=zip', '-o', str(archive), BASE, *paths],
                           cwd=ROOT, check=True)
            with ZipFile(archive) as contents:
                contents.extractall(work)
            before, after = execute(work), execute(ROOT)
            assert before == after, (before, after)
            print(json.dumps(dict(base=BASE, identical=True, cases=after), indent=2))
