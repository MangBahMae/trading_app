# 지속 급락 구간 정책 · 고정 일봉 전후 비교

기준 `869df6183c59cd81fc6236114cd4d9f0d637a6b9`와 새 단일 엔진/API projection을 비교했다. 실제 지지 입력은 0개이며 후보 수는 거래 수·수익성이 아니다.

고정 일봉 1762개, UTC 2022-01-01~2026-10-28. 새 phase 분포: `{'insufficient': 2, 'normal': 2, 'active': 504, 'eased': 1254}`.

이전 API 신호: `{'acceleration_warning': 148, 'retest_watch': 14, 'retest_long': 1, 'candidate_expired': 1}`. 새 API 신호: `{'acceleration_warning': 148, 'brake_watch': 96, 'retest_watch': 14, 'retest_long': 1, 'candidate_expired': 1}`.

신호 추가/삭제/판정·참조 변경/표시명 변경: `{'retained': 16, 'added': 96, 'removed': 0, 'reclassified': 0, 'relabeled': 148}`. 원시 관찰 사건: `{'retained': 138, 'added': 31, 'removed': 6, 'reclassified': 0, 'relabeled': 0}`.

`relabeled`는 제목만 바뀌고 ID·유형·발생일·판정이 같은 경우다. 이번 가속 경고의 “현재 하락 가속 경고”→“추가 가속 경고”를 판정 변화와 구별한다. `reclassified`는 판정·참조가 바뀐 경우다.

active는 recent≤-2%/봉에서 시작한다. 추가 가속은 그 중 recent≤previous-1%p/봉일 때만 참이다. 완화는 recent>-1%/봉과 이전까지 구간 종가 저점 갱신 없음이 동시에 3봉 연속인 날 확정한다. 종가 저점은 비교 후 갱신하며, 한 조건이 깨지면 연속 횟수는 0이다.

## 요청 구간의 일별 상태

| UTC 날짜 | 종가 | recent/봉 | 이전 관찰창 | 새 phase | 추가 가속 | 안정 봉 | 새 신호 | 요약 |
|---|---:|---:|---|---|---|---:|---|---|
| 2026-01-25 | 86,670.36 | -1.662% | False | eased | False | 3 | 없음 | 신호 없음 |
| 2026-01-26 | 88,347.08 | -0.495% | False | eased | False | 3 | 없음 | 신호 없음 |
| 2026-01-27 | 89,250.00 | 1.466% | False | eased | False | 3 | 없음 | 신호 없음 |
| 2026-01-28 | 89,299.99 | 0.536% | False | eased | False | 3 | 없음 | 신호 없음 |
| 2026-01-29 | 84,650.16 | -2.646% | True | active | True | 0 | acceleration_warning | 신호 없음 |
| 2026-01-30 | 84,260.49 | -2.904% | True | active | True | 0 | acceleration_warning, brake_watch | 첫 제동 관찰 |
| 2026-01-31 | 78,741.09 | -3.618% | True | active | False | 0 | 없음 | 신호 없음 |
| 2026-02-01 | 76,968.21 | -4.526% | True | active | True | 0 | acceleration_warning | 신호 없음 |
| 2026-02-02 | 78,738.61 | -0.002% | True | active | False | 1 | 없음 | 신호 없음 |
| 2026-02-03 | 75,770.21 | -0.784% | True | active | False | 0 | 없음 | 신호 없음 |
| 2026-02-04 | 73,165.83 | -3.670% | True | active | True | 0 | acceleration_warning | 신호 없음 |
| 2026-02-05 | 62,909.86 | -9.300% | True | active | True | 0 | acceleration_warning | 신호 없음 |
| 2026-02-06 | 70,580.26 | -1.799% | True | active | False | 0 | 없음 | 신호 없음 |
| 2026-02-07 | 69,289.38 | 4.829% | True | active | False | 1 | 없음 | 신호 없음 |
| 2026-02-08 | 70,330.38 | -0.177% | False | active | False | 2 | 없음 | 신호 없음 |
| 2026-02-09 | 70,138.00 | 0.609% | False | eased | False | 3 | 없음 | 신호 없음 |
| 2026-02-10 | 68,841.29 | -1.070% | False | eased | False | 3 | 없음 | 신호 없음 |
| 2026-06-01 | 71,408.90 | -1.704% | False | eased | False | 3 | 없음 | 신호 없음 |
| 2026-06-02 | 66,760.83 | -4.927% | True | active | True | 0 | acceleration_warning | 신호 없음 |
| 2026-06-03 | 64,142.75 | -5.366% | True | active | True | 0 | acceleration_warning | 신호 없음 |
| 2026-06-04 | 63,885.99 | -2.201% | True | active | False | 0 | brake_watch | 첫 제동 관찰 |
| 2026-06-05 | 61,056.47 | -2.466% | True | active | False | 0 | 없음 | 신호 없음 |
| 2026-06-06 | 60,884.62 | -2.406% | False | active | False | 0 | brake_watch | 첫 제동 관찰 |
| 2026-06-07 | 63,332.01 | 1.830% | False | active | False | 1 | 없음 | 신호 없음 |
| 2026-06-08 | 63,085.99 | 1.776% | False | active | False | 2 | brake_watch | 첫 제동 관찰 |
| 2026-06-09 | 61,730.00 | -1.281% | False | active | False | 0 | 없음 | 신호 없음 |
| 2026-06-10 | 61,510.99 | -1.264% | False | active | False | 0 | brake_watch | 첫 제동 관찰 |

전체 날짜·추가/삭제/분류변경과 이유는 `daily_comparison.csv`, `signal_diff.csv`, `raw_event_diff.csv`에 있다. 신규/유지 후보는 `new_signals.csv`의 발행 기록과 daily CSV의 maintained 목록을 따로 본다.

## 불변성·중복 및 제한

검사 결과: `{'prefixes': 1762, 'historical_state_comparisons': 1553203, 'history_prefix_tips_checked': 1762, 'shape_recomputed_each_prefix': True, 'future_days': 32, 'future_support_injected': True, 'mismatches': 0}`. 독립 상태식 검사: `{'rows': 1762, 'mismatches': 0, 'close_low_compared_before_update': True, 'recovery_uses_strict_speed_comparison': True, 'recovery_requires_both_conditions': True}`. 중복·후보 연결 검사: `{'history_ids': 260, 'candidate_keys': 1, 'duplicate_ids': 0, 'reissued_candidates': 0, 'invalid_candidate_links': 0}`.

접두 구간마다 기존 모양 함수부터 재계산했다. 미래 32봉과 미래에 처음 알려진 지지를 추가해도 과거 phase·summary·raw_events·신호 ID·발행 이력·유지 상태가 같았다.

실제 수동 지지 이력이 없으므로 첫 지지 반응과 수동 지지 회복의 실제 시장 검증은 하지 않았다. 합성 지지 검사는 따로 기록한다. 실제 후보의 진입 가능성·체결·수익성도 검증하지 않았다.

이번 runner는 SQLite 연결과 외부 요청을 금지하며 실제 DB를 읽거나 기록하지 않는다. 과거 D44→F046 DB 해시 불일치와 사고 증거를 복구·덮어쓰기하지 않았다. 기존 baseline/사고 로그/과거 결과 파일의 바이트 해시가 실행 전후 동일함만 확인했다.
