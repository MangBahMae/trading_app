# 차트 날짜 선택 검증

빌드한 프런트와 격리된 실제 API를 같은 로컬 주소에서 열고, Playwright Chromium의 새 headless 컨텍스트에서 캔버스를 클릭했다. 실험 토글의 초기 OFF와 요청 0건을 확인한 뒤, 선택한 날짜에 도착한 HTTP 200 응답의 시장·롱 종료·숏 세 값을 패널과 대조했다. 확인한 7개 날짜에서 세 값이 모두 일치했다. 합성 사례의 화면에는 **합성 데이터 · 검증용**이 표시된다.

| 입력 | UTC 일봉 | 화면에서 확인한 결과 | 증거 |
|---|---|---|---|
| 고정 일봉, 당시 수동 도형 없음 | 2022-02-17 | 시장 일반 · 숏 관찰 · 고점 재시도 실패 | [화면](results/fixed-2022-02-17.png), [결과](results/fixed.json) |
| 합성 급등 뒤 도지 | 2022-01-05 | 상승 추세 유지 · 숏 해당 없음 | [결과](results/surge_doji.json) |
| 합성 횡보와 재시도 | 2022-01-04, 07, 09 | 4일 횡보, 7일 첫 숏 관찰, 9일 상방 돌파로 관찰 해제 | [7일 화면](results/high_retry-2022-01-07.png), [날짜별 결과](results/high_retry.json) |
| 합성 우상향 추세선 | 2022-01-04 | 기존 롱 종료 검토 · 숏 해당 없음. 기존 집계의 숏은 1개 | [화면](results/trendline-2022-01-04.png), [결과](results/trendline.json) |
| 합성 지지 존 | 2022-01-03 | 숏 후보 · 지지 재시험 실패 | [화면](results/support_fail-2022-01-03.png), [결과](results/support_fail.json) |

모든 컨텍스트에서 페이지 오류와 허용 주소 밖의 요청은 0건이었다. 이미지 4장을 확인했고 서버 5개 종료 후 18873~18877 포트의 리스너도 0개였다. 첫 시도의 연속 클릭이 더블클릭으로 해석돼 7일 선택 확인이 실패했고, 검사 스크립트에 단일 클릭 간격을 둔 뒤 5개 입력을 모두 재검사했다.

## 재현

저장소 루트에서 프런트를 빌드한 뒤 빈 포트에 프로젝트 가상환경의 검증 서버를 실행한다.

```powershell
Push-Location frontend
npm.cmd run build
Pop-Location
& .\backend\.venv\Scripts\python.exe -B research/rise_response/validation.py --case high_retry --port 18874 --frontend
```

다른 터미널에서 Playwright와 Chromium이 설치된 Python으로 아래 명령을 실행한다. `--output`에 새 디렉터리를 지정하면 기존 검증 기록을 보존한다.

```powershell
$resultDir = Join-Path $env:TEMP ("ccx-rise-chart-" + [guid]::NewGuid())
python -B research/rise_response/browser/check_chart.py --case high_retry --url http://127.0.0.1:18874 --output $resultDir
```

검사 후 서버를 Ctrl+C로 종료한다. 다른 입력은 서버와 검사 명령의 `--case`를 같은 값으로 바꿔 재현할 수 있다.
