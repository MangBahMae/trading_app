"""프로젝트 가상환경으로 백엔드/기존 연구 회귀 로그를 UTF-8 원문으로 남긴다."""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE/'results_v03'
env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
commands = [
    ('backend_tests.log', REPO/'backend', ['-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider',
      '--basetemp', str(RESULTS/'.tmp_backend')]),
    ('research_tests.log', HERE, ['-m', 'unittest', 'discover', '-v']),
]
for name, cwd, arguments in commands:
    result = subprocess.run([sys.executable, '-B', *arguments], cwd=cwd, env=env, capture_output=True)
    (RESULTS/name).write_bytes(result.stdout+result.stderr)
    print(f'{name}: exit={result.returncode}', flush=True)
    print((result.stdout+result.stderr).decode('utf-8', errors='replace')[-1800:], flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
