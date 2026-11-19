# CoinCloudX · 급락 대응 관찰기 v0.2

검토 커밋 `38d3f59685e577da2991323d97b448e72b66dd54`에서 이어가는 독립 연구 프로그램이다. 기존 `rapid_drop.py`를 직접 수정했다. 앱 연결, 주문, 분할 비중, 손절, 체결·손익 모델, RSI는 구현하지 않는다. **사건의 중복 기록은 중복 진입이 아니며, 사건 수는 거래 수나 수익성이 아니다.**

운영 코드는 기존 `backend/app/services/candle_patterns.py`의 `compute_candle_shape`만 읽어 재사용한다. 운영 코드와 모양 상수, 사용자 DB, Streamlit, 골든값을 변경하지 않는다. `example_config.json`의 수치는 검증되지 않은 비교용 실험값 그대로다. 임계값을 최적화하거나 새로운 거래량 필수 조건을 추가하지 않았다.

## 실행과 결과

프로젝트 `backend/.venv` Python을 사용한다. 엔진은 표준 라이브러리만 사용하지만, 기존 모양 함수와 통합 테스트는 프로젝트의 pandas를 사용한다. 프로젝트 루트에서 PowerShell로:

```powershell
Set-Location research/ccx_rapid_drop
& ../../backend/.venv/Scripts/python.exe -B -m unittest discover -v
& ../../backend/.venv/Scripts/python.exe -B replay.py --repo ../.. --config example_config.json --levels levels.example.json --output results_v02/observations.jsonl
& ../../backend/.venv/Scripts/python.exe -B -u run_audit.py
```

`--output`은 UTF-8 JSONL로 저장하여 PowerShell 리다이렉션의 문자 인코딩에 기대지 않는다. 생략하면 표준 출력이다. 실행기는 기존 고정 마감 일봉 2022-01-01~2026-10-28, 1,762개 전용이다. 시세 수집·운영 API·SQLite 연결을 호출하지 않는다.

- `REPORT_V02.md`: 실제 전체 실행, 날짜, v0.1 대비 추가·삭제·재분류와 이유.
- `results_v02/`: 새 테스트 로그, 사건별 CSV, 비교 JSON/CSV, 합성 결과, 불변성·보존 증거. 전체 봉 JSONL은 Git에서 제외한 재생성 가능한 로컬 산출물이다.
- `REVIEW.md`, `results/`, `test_log.txt`: **v0.1의 과거 검토 기록**이며 현재 동작이나 최신 테스트 결과로 사용하지 않는다.
- `HANDOFF_V02.md`: 다음 기기의 재현 절차와 미검증 항목.

`run_audit.py`는 고정 기준 커밋의 v0.1 엔진을 `git show`로 읽어 비교할 때만 메모리에서 실행한다. 별도 엔진 파일이나 ZIP을 만들지 않는다. 과거 커밋을 포함한 Git 이력이 필요하다. 보존 검사는 현재 기기에 존재하는 파일의 실행 전후 해시를 비교하며, 다른 기기에 개인 DB나 `.vscode`가 없어도 만들거나 복원하지 않는다.

## 첫 반응과 기존 기준 추적

첫 지지 반응과 재지지 모두 `doji`, `hammer`, `inverted_hammer`를 동일하게 반전 모양 평가 대상으로 삼는다. 기존 모양 함수가 부여한 라벨을 사용하며 세 모양만으로 진입을 승인하지 않는다.

급락 가속 관찰 기간에 실제 지지 반응과 반전 모양이 있으면 `first_support_reaction`을 기록한다. 기존 기준이 살아 있으면 `support_reaction_while_tracking`, 이전 기준이 종가 이탈 또는 만료된 후 새 반응이면 `support_reaction_after_invalidation`이다. 새 반응은 기존 기준 추적 여부와 무관하게 기록한다. 지지 반응이 확인되지 않은 반전 모양은 `reversal_observed`이며, 지지 정보 부족과 확인된 지지 무반응을 구분한다.

`volume_red_watch_only`는 고거래량 장대음봉이라는 관찰 사실이다. 반전 모양과 겹치면 두 사건을 모두 남긴다. 고거래량은 원래의 직전 평균·배수와 장대음봉 기준으로 판정하며 마지막 매도나 매수 신호로 단정하지 않는다.

추적 기준은 여전히 한 개다. 살아 있는 기준을 새 반응이 자동 교체하지 않는다. 새 장대음봉도 자체 참조 ID와 `tracking_anchor=false`로 관찰할 수 있다. 기준이 없고 급락 관찰 기간이면 장대음봉, 그렇지 않으면 확인된 지지의 반전 반응을 기준으로 삼는다. 두 조건이 동시에 있으면 같은 장대음봉 기준에 두 사실을 연결한다. 거래량이 낮은 반전 반응도 관찰·기준 생성이 가능하며 거래량 상태를 별도로 남긴다.

기준은 종가가 기준대 하단을 이탈하면 `anchor_lost_on_close`, 기존 `max_age`를 넘으면 `anchor_expired`다. **반전 모양 재시험으로 기준을 소진하지 않는다.** 반복 접촉과 이후 수명 종료까지 사실대로 기록한다. 같은 날 이전 기준 무효화와 새 기준 반응이 있어도 각 사건의 기준 참조가 다르므로 덮어쓰지 않는다.

## 재시험 사실, 종가 위치, 진입 미평가

`retest_observed`는 기준 유효기간 안에서 **이전 봉까지** 종가 반등이 확인됐고 오늘 고가~저가가 기준 종가 주변 허용대에 겹친 사실이다. 반등과 재시험을 같은 일봉에서 동시에 판정하지 않는다. 종가가 허용대 아래인 날도 접촉 사실과 기준 무효화를 함께 기록한다.

- `reference_price/bottom/top`: 자동 기준 봉의 종가와 기존 `tolerance`로 만든 가격대. 사용자 수동 지지선으로 취급하지 않는다.
- `close_location`: `within_reference_band`, `above_reference_band`, `below_reference_band`를 구분한다.
- `close_far_rebounded`: 종가가 기존 `rebound` 이상 높다. 별도의 새로운 “멀다” 임계값은 없다. 허용대 위지만 이 반등 기준 미만인 종가도 구분된다.
- `range_tests_reference`, `lower_wick_tests_reference`: 전체 범위 접촉과 아래꼬리 접촉을 분리한다.
- `first_wick_undercut`, `wick_recovered_on_close`: 첫 기준 봉의 저가 하회와 그 저가의 종가 회복 여부다. “첫”은 첫 기준 봉을 가리키며, 최초 한 번만 기록한다는 뜻이 아니다.
- `shape`: 기존 반전 모양. v0.1의 `retest_preferred`를 별도의 진입 선호 신호로 유지하지 않는다.
- `entry_status`: 모든 사건이 `not_evaluated`다. 재시험 사실·가격 위치는 기록하지만 진입 가능성 규칙은 구현하지 않는다.

## 수동 지지, 시간, 이탈 후 회복

`levels.example.json`은 빈 목록이다. 현재 고정 일봉 실행은 실제 지지에서의 첫 반응이나 수동 지지 회복을 검증하지 않는다. 자동 기준 가격의 재시험과 수동 지지 반응은 별개다.

수동 지지는 `key`(좌표 버전), `bottom`, `top`, `known_from`, `through`가 필요하다. 날짜는 ISO `YYYY-MM-DD`, 양끝 포함이다. 선택적인 `support_id`는 동일 도형의 버전을 묶는다. 생략하면 `key`가 지지 ID다. 동일 지지의 좌표 버전 기간이 겹치면 거절한다. `known_from` 이전에는 좌표를 사용하지 않으며, 현재 도형이나 생성 시각만으로 과거 좌표 이력을 추측하지 않는다. 도형 좌표 버전의 역사적 진위를 프로그램이 입증하지는 못한다.

`manual_support_status=unconfirmed`와 빈 `support_evaluations`는 당일 사용 가능한 수동 지지가 없다는 뜻이다. 사용 가능한 지지가 있지만 반응이 없으면 평가 행에 `known_no_reaction`을 남긴다. 지지에 닿고 시가·종가가 지지 하단 이상이면서 미회복 이탈 상태가 아닌 경우 `reaction`이다.

당시 사용 가능한 같은 버전의 이전 종가가 지지 하단 이상이었는데 오늘 종가가 하단 아래라면 `support_break_observed`다. 이후 종가가 존 상단 이상으로 회복하면 `support_recovery_trap_watch`를 기록하고 이전 이탈 사건 ID를 연결한다. 존 안으로만 돌아오면 아직 완전 회복이 아니다. 회복한 당일을 새 첫 지지 반응으로 분류하지 않는다. 이는 트랩 후보 관찰이며 자동 매수·매도 전환이 아니다.

관찰 시작부터 가격이 지지 아래였거나 시가가 아래였다는 사실만으로 과거 이탈을 만들어내지 않는다. 그런 경우 회복은 `support_reclaim_without_observed_break`로 구분한다. 좌표 버전이 바뀌면 이전 버전의 이탈을 새 버전에 승계하지 않는다.

## 사건 스키마와 거래량

v0.2 JSONL은 `schema_version="0.2"`이며 `events`는 문자열 배열에서 **사건 객체 배열**로 바뀌었다. v0.1 소비 코드와 직접 호환되지 않는다. 현재 연구 프로그램 외의 소비자는 없다.

각 사건은 `id`, `anchor_id/day/source`, `support_id/version_id/source`, `manual_support_ids`와 가격·모양·거래량을 가진다. `manual_support_ids`는 기준 생성 당시의 관련 지지, `evaluated_support_ids`는 당일 평가 가능한 지지 ID 목록이다. 확인된 지지 무반응도 어떤 지지를 평가했는지 확인할 수 있다. ID는 날짜·사건 종류·기준·지지 버전으로 결정되며 미래 봉 수나 전체 순번에 의존하지 않는다. 같은 날 여러 지지에 반응하면 지지별 사건을 남긴다. 지지 입력의 순서를 바꾸어도 ID와 결과가 같다.

`support_source=manual`은 입력 지지, `automatic_reference`는 자동 기준 가격, `unconfirmed`는 수동 지지 미확인, `known_no_reaction`은 입력 지지에서 유효한 반응이 없는 반전 관찰이다. 미확인 지지의 `support_id`는 `null`이며 가짜 수동 지지 ID를 만들지 않는다. 자동 기준의 지지 참조 ID는 기준 ID다. 이전·신규 기준 교체는 `previous_anchor_id`로, 회복은 `related_event_id`로 연결한다.

거래량은 두 배수를 따로 기록한다. `volume_ratio_recent`는 당일 제외 직전 `volume_bars` 평균 대비이며 평균 0·데이터 부족이면 `null`이다. `volume_ratio_anchor_red`는 **사건이 참조하는 기준이 장대음봉인 경우** 그 기준 봉 거래량 대비다. 해당 기준이 수동 지지 반응 등으로 시작돼 장대음봉 기준이 없으면 `null`이다. `volume_red_anchor_id/day`로 분모를 확인할 수 있다. 하루 관찰에도 추적 기준의 두 배수를 남긴다. 새로 관찰된 미추적 장대음봉은 자신의 사건에서 자기 기준을 사용하므로 배수가 1이고, 당일 추적 기준의 배수와 다를 수 있다. 어느 배수에도 새 필수 임계값을 추가하지 않았다.

## 검증 범위

갱신된 엔진·연동 테스트 46개가 통과했다. 고정 1,762봉의 모든 접두 구간에서 기존 모양 함수부터 다시 계산해 모든 과거 필드와 사건 ID를 비교했다. 합성 미래 32일과 미래 지지를 추가하는 검사, 실제 지지와 분리한 합성 13개 시나리오의 89개 접두 구간 및 각 32일 확장도 일치했다. 실제 과거 데이터 자체나 설정·당시 알려진 지지 좌표를 수정해도 판정이 같다는 뜻은 아니다.

v0.1 110개 사건에서 v0.2는 144개 사실이다. 분류 유지 57개, 분류·속성 변경 53개, 추가 35개, 삭제 0개다. 이전의 별도 꼬리 회복 1개는 같은 재시험의 속성으로 합쳐졌다. 재시험은 7개에서 17개로 늘었지만 이는 반복 접촉 및 이탈일 접촉의 기록 범위 변화이며 거래 증가나 수익성 향상을 뜻하지 않는다. 상세 날짜와 이유는 보고서와 비교 CSV를 참고한다.
