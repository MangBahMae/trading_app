# 시장 방향 · 롱 종료 · 숏 관찰의 차트 검증

빌드된 차트에서 BTCUSDT 일봉을 직접 클릭했다. 같은 날짜의 HTTP 200 응답과 패널의 세 줄을 글자 단위로 대조하고, 상세를 펼쳐 스윙의 발생일·확인일과 각 관찰·후보의 시작일·종료일·지속 일수를 확인했다. 각 입력은 별도 임시 DB·도형 이력과 새 headless Chromium 컨텍스트를 사용했다. 최초 진입 시 실험은 OFF였고 상승 API 요청은 0건이었다.

## 고정 BTCUSDT 일봉

| 선택한 날짜 | 화면에서 확인한 판단 |
|---|---|
| 2022-01-17 | EMA 배열 자료가 부족해도 고점 재시도 실패가 확인되어 숏 관찰 신규. [화면](direction_results/fixed-2022-01-17.png) |
| 2022-01-20 | 기존 고점 관찰은 유지, 확정 저점의 재시험 실패로 별도 숏 후보 신규. [화면](direction_results/fixed-2022-01-20.png) |
| 2022-03-09 | 시장 방향은 역배열 속 반등. 종전 숏 관찰은 유지. |
| 2024-02-12 | 2022-02-11부터 이어진 고점 관찰이 상방 돌파로 해제. 양 끝 날짜를 포함해 732일. |
| 2024-03-16 | 정배열에서 확정 스윙 저점 67,024.96 하회. 기존 롱 종료 검토만 표시. [화면](direction_results/fixed-2024-03-16.png) |

고정 입력에 실제 과거 수동 도형은 없다. [일자별 API·패널 대조와 관찰 이력](direction_results/fixed.json)

## 합성 BTCUSDT 일봉

| 입력·날짜 (2022년) | 선택 결과 |
|---|---|
| 완만한 상승 02-19, 03-15 | 누적 급등·장대양봉 없이 롱 우세, 이후 고점 재시도 실패. [화면](direction_results/gentle_rise-2022-03-15.png) |
| 장대양봉 뒤 도지 01-05 | 배열 미확인, 신규 롱 종료·숏 모두 없음. [결과](direction_results/surge_doji.json) |
| 정배열 속 수동 추세선 03-07, 03-08 | 7일은 꼬리 이탈 회복, 8일 종가 이탈에 롱 종료 검토. 숏 없음. [화면](direction_results/bull_trendline-2022-03-08.png) |
| 역배열 속 EMA50 반등 08-11~14 | 11일은 두 경로 모두 접촉만 발생. 12일 위로 진행한 경로는 숏 없음. 거부된 경로는 12일 신규, 13일 유지, 14일 EMA 관찰 해제. [상승 경로](direction_results/ema_resist_rise.json) · [거부 경로 화면](direction_results/ema_resist_fail-2022-08-12.png) |
| 동일 지지 존 이탈 01-03, 01-05 | 3일 재시험 실패 경로에서만 숏 후보. 5일 회복에 후보 무효. 다른 두 경로의 3일은 회복 또는 미접촉 하락. [실패](direction_results/support_fail.json) · [회복](direction_results/support_recover.json) · [미접촉](direction_results/support_no_retest.json) |
| 혼조 04-08, 04-10 | 구조 자료가 엇갈리거나 부족하면 방향 미확인. 고점과 저점이 함께 오르거나 내리면 같은 혼조에서도 상승 우세·하락 우세로 구분. [상승·미확인](direction_results/mixed_structure.json) · [하락](direction_results/mixed_fall.json) |

합성 화면에는 **합성 데이터 · 검증용**을 표시했다. 고정 5회와 합성 18회, 총 23번의 날짜 선택에서 응답과 화면이 일치했다. 페이지 오류 및 허용 주소 밖의 요청은 0건이었다. 최초 검사에서는 오른쪽 빈 공간의 호버가 직전 선택일로 표시되어 마지막 봉을 찾지 못했다. 검사기가 실제 두 봉의 호버 위치를 먼저 확인하도록 수정한 뒤 전체 입력을 재실행했다.

## 다음 기기에서 재현

저장소 루트에서 실행한다. 프로젝트 가상환경 외에 Playwright와 Chromium을 설치한 Python이 필요하다. 무작위 빈 포트에 케이스별 서버를 띄우고 검사 직후 정상 종료한다.

```powershell
Push-Location frontend
npm.cmd run build
Pop-Location
$resultDir = Join-Path $env:TEMP ("ccx-rise-chart-" + [guid]::NewGuid())
& .\backend\.venv\Scripts\python.exe -B research/rise_response/browser/run_checks.py --output $resultDir
```

일부 입력만 재생하려면 `--case fixed` 등을 덧붙인다. Playwright가 다른 Python에 있으면 `--browser-python <경로>`를 지정한다. [선택일과 기대 사건](direction_cases.json) · [이전 PR 버전의 화면 7건과 재현 문서](https://github.com/MangBahMae/trading_app/blob/8d0ee31ff011a605c3297bb2d15ec517cb151373/research/rise_response/browser/README.md)
