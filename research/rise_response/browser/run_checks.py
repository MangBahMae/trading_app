"""빌드된 프런트를 케이스별 임시 DB·로컬 포트에서 열어 날짜 선택 검사를 실행한다."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validation import ROOT, isolated
from app.main import app
from fastapi.staticfiles import StaticFiles
import uvicorn


@contextmanager
def local_server():
    """검증 컨텍스트 안에서만 실행하며 OS가 배정한 루프백 포트를 호출자에게 넘긴다."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while thread.is_alive() and not server.started and time.monotonic() < deadline:
                time.sleep(0.05)
            if not server.started:
                raise RuntimeError('격리 서버를 시작하지 못했습니다.')
            yield f'http://127.0.0.1:{sock.getsockname()[1]}'
        finally:
            server.should_exit = True
            thread.join(30)
            if thread.is_alive():
                raise RuntimeError('격리 서버가 종료되지 않았습니다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--case', action='append', help='생략 시 모든 입력을 검사한다.')
    parser.add_argument('--browser-python', default='python', help='Playwright가 설치된 Python')
    args = parser.parse_args()
    cases = json.loads((HERE / 'direction_cases.json').read_text(encoding='utf-8'))
    app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True))
    for case in args.case or cases:
        with isolated(case), local_server() as url:
            subprocess.run([args.browser_python, '-B', str(HERE / 'check_chart.py'), '--case', case,
                            '--url', url, '--output', str(args.output)], check=True)


if __name__ == '__main__':
    main()
