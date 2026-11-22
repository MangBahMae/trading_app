# 급락 대응 v0.2 구현·전체 실행 결과

실제 지지는 0개다. 사건 수는 거래 수나 수익성이 아니다. 모든 사건의 진입 상태는 `not_evaluated`다.

기준 커밋: `38d3f59685e577da2991323d97b448e72b66dd54`. 작업 브랜치: `feat/rapid-drop-v02`.

프로젝트 Python 3.13.2에서 테스트 46개 통과. 고정 2022-01-01~2026-10-28 일봉 1,762개를 원본 캔들 모양 함수로 재실행했다.

| 사건 | 건수 | UTC 봉 날짜 |
|---|---:|---|
| `volume_red_watch_only` | 22 | 2022-01-21, 2022-04-11, 2022-05-09, 2022-06-13, 2022-09-06, 2022-11-08, 2023-06-05, 2023-08-17, 2023-12-11, 2024-01-22, 2024-04-02, 2024-06-24, 2024-07-04, 2024-08-05, 2024-08-27, 2025-10-10, 2025-11-04, 2025-12-01, 2026-01-20, 2026-01-29, 2026-02-05, 2026-06-02 |
| `first_support_reaction` | 0 | 없음 |
| `support_reaction_while_tracking` | 0 | 없음 |
| `support_reaction_after_invalidation` | 0 | 없음 |
| `reversal_observed` | 71 | 2022-01-08, 2022-01-24, 2022-02-12, 2022-02-19, 2022-03-12, 2022-04-20, 2022-04-24, 2022-05-02, 2022-05-12, 2022-06-14, 2022-06-15, 2022-06-17, 2022-07-26, 2022-08-22, 2022-09-08, 2022-09-14, 2022-09-23, 2023-03-04, 2023-03-06, 2023-03-10, 2023-05-09, 2023-05-10, 2023-06-09, 2023-06-11, 2023-06-12, 2023-06-13, 2023-08-19, 2023-11-23, 2023-12-14, 2024-01-13, 2024-01-20, 2024-01-28, 2024-03-23, 2024-04-05, 2024-04-07, 2024-07-01, 2024-07-05, 2024-08-10, 2024-08-29, 2024-08-30, 2024-10-02, 2024-10-03, 2024-11-02, 2024-11-03, 2024-11-28, 2024-12-20, 2025-01-11, 2025-02-06, 2025-02-07, 2025-02-27, 2025-02-28, 2025-03-04, 2025-03-06, 2025-03-30, 2025-03-31, 2025-04-07, 2025-06-13, 2025-08-16, 2025-08-17, 2025-10-13, 2025-11-21, 2025-12-06, 2025-12-08, 2026-01-22, 2026-01-23, 2026-01-30, 2026-02-09, 2026-03-28, 2026-06-04, 2026-06-26, 2026-06-27 |
| `bounce_observed` | 12 | 2022-04-13, 2022-05-10, 2022-09-09, 2023-06-06, 2023-12-13, 2024-01-26, 2024-04-04, 2024-06-30, 2024-08-06, 2025-11-09, 2025-12-02, 2026-02-06 |
| `retest_observed` | 17 | 2022-04-14, 2022-04-15, 2022-04-17, 2022-04-18, 2022-05-11, 2023-06-10, 2023-06-11, 2023-06-12, 2023-06-13, 2023-12-14, 2023-12-16, 2023-12-17, 2023-12-18, 2024-04-05, 2024-08-07, 2025-11-11, 2025-11-12 |
| `anchor_lost_on_close` | 11 | 2022-01-22, 2022-05-11, 2022-06-14, 2022-11-09, 2023-08-18, 2024-07-07, 2024-09-01, 2025-10-11, 2026-01-25, 2026-01-31, 2026-06-03 |
| `anchor_expired` | 11 | 2022-04-20, 2022-09-15, 2023-06-14, 2023-12-20, 2024-01-31, 2024-04-11, 2024-07-03, 2024-08-14, 2025-11-13, 2025-12-10, 2026-02-14 |
| `support_break_observed` | 0 | 없음 |
| `support_recovery_trap_watch` | 0 | 없음 |
| `support_reclaim_without_observed_break` | 0 | 없음 |

## v0.1 대비 차이

기준 커밋의 엔진을 Git에서 읽어 메모리에서 다시 실행했다. v0.1 110개 사건, v0.2 144개 사실이다. 이전 결과의 모든 사건별 날짜도 다시 일치했다.

비교 상태: `{'preserved': 57, 'reclassified': 53, 'added': 35, 'removed': 0}`. 여러 이전 사건이 한 새 사건의 속성으로 합쳐질 수 있으므로 단순 건수 차이를 추가 사건 수로 해석하지 않는다.

110개 이전 사건 중 57개는 분류 유지, 53개는 분류·속성 변경, 삭제 0개다. 새 사실 35개의 종류별 건수는 `{'retest_observed': 10, 'reversal_observed': 22, 'anchor_expired': 3}`다. 이전 별도 사건 1개를 재시험 속성으로 합쳤다. 110 + 35 - 0 - 1 = 144개 사실이다.

| 상태 | UTC 봉 날짜 | 이전 분류 / 기준 | 새 분류 / 기준 | 이유 |
|---|---|---|---|---|
| reclassified | 2022-01-08 | shape_observed_only / — | reversal_observed / 2022-01-08 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-01-24 | shape_observed_only / — | reversal_observed / 2022-01-24 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-02-12 | shape_observed_only / — | reversal_observed / 2022-02-12 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-02-19 | shape_observed_only / — | reversal_observed / 2022-02-19 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-03-12 | shape_observed_only / — | reversal_observed / 2022-03-12 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-04-24 | shape_observed_only / — | reversal_observed / 2022-04-24 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-05-02 | shape_observed_only / — | reversal_observed / 2022-05-02 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-05-12 | shape_observed_only / — | reversal_observed / 2022-05-12 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-06-14 | shape_observed_only / 2022-06-13 | reversal_observed / 2022-06-14 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-06-15 | shape_observed_only / — | reversal_observed / 2022-06-15 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-06-17 | shape_observed_only / — | reversal_observed / 2022-06-17 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-07-26 | shape_observed_only / — | reversal_observed / 2022-07-26 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-08-22 | shape_observed_only / — | reversal_observed / 2022-08-22 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2022-09-23 | shape_observed_only / — | reversal_observed / 2022-09-23 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-03-04 | shape_observed_only / — | reversal_observed / 2023-03-04 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-03-06 | shape_observed_only / — | reversal_observed / 2023-03-06 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-03-10 | shape_observed_only / — | reversal_observed / 2023-03-10 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-05-09 | shape_observed_only / — | reversal_observed / 2023-05-09 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-05-10 | shape_observed_only / — | reversal_observed / 2023-05-10 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-06-10 | first_wick_undercut_recovered / 2023-06-05 | retest_observed / 2023-06-05 | 별도 사건을 같은 재시험 사건의 꼬리 하회·회복 속성으로 통합 |
| reclassified | 2023-06-11 | retest_preferred / 2023-06-05 | retest_observed / 2023-06-05 | 선호 진입 의미를 제거하고 모양·종가 위치·진입 미평가를 분리 |
| reclassified | 2023-08-19 | shape_observed_only / — | reversal_observed / 2023-08-19 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-11-23 | shape_observed_only / — | reversal_observed / 2023-11-23 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2023-12-14 | retest_preferred / 2023-12-11 | retest_observed / 2023-12-11 | 선호 진입 의미를 제거하고 모양·종가 위치·진입 미평가를 분리 |
| reclassified | 2024-01-13 | shape_observed_only / — | reversal_observed / 2024-01-13 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-01-20 | shape_observed_only / — | reversal_observed / 2024-01-20 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-03-23 | shape_observed_only / — | reversal_observed / 2024-03-23 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-04-05 | retest_preferred / 2024-04-02 | retest_observed / 2024-04-02 | 선호 진입 의미를 제거하고 모양·종가 위치·진입 미평가를 분리 |
| reclassified | 2024-10-02 | shape_observed_only / — | reversal_observed / 2024-10-02 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-10-03 | shape_observed_only / — | reversal_observed / 2024-10-03 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-11-02 | shape_observed_only / — | reversal_observed / 2024-11-02 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-11-03 | shape_observed_only / — | reversal_observed / 2024-11-03 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-11-28 | shape_observed_only / — | reversal_observed / 2024-11-28 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2024-12-20 | shape_observed_only / — | reversal_observed / 2024-12-20 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-01-11 | shape_observed_only / — | reversal_observed / 2025-01-11 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-02-06 | shape_observed_only / — | reversal_observed / 2025-02-06 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-02-07 | shape_observed_only / — | reversal_observed / 2025-02-07 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-02-27 | shape_observed_only / — | reversal_observed / 2025-02-27 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-02-28 | shape_observed_only / — | reversal_observed / 2025-02-28 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-03-04 | shape_observed_only / — | reversal_observed / 2025-03-04 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-03-06 | shape_observed_only / — | reversal_observed / 2025-03-06 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-03-30 | shape_observed_only / — | reversal_observed / 2025-03-30 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-03-31 | shape_observed_only / — | reversal_observed / 2025-03-31 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-04-07 | shape_observed_only / — | reversal_observed / 2025-04-07 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-06-13 | shape_observed_only / — | reversal_observed / 2025-06-13 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-08-16 | shape_observed_only / — | reversal_observed / 2025-08-16 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-08-17 | shape_observed_only / — | reversal_observed / 2025-08-17 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-10-13 | shape_observed_only / — | reversal_observed / 2025-10-13 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2025-11-21 | shape_observed_only / — | reversal_observed / 2025-11-21 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2026-03-28 | shape_observed_only / — | reversal_observed / 2026-03-28 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2026-06-04 | shape_observed_only / — | reversal_observed / 2026-06-04 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2026-06-26 | shape_observed_only / — | reversal_observed / 2026-06-26 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| reclassified | 2026-06-27 | shape_observed_only / — | reversal_observed / 2026-06-27 | 지지 미확인/확인된 지지 무반응을 구분하는 반전 사실로 명칭 변경 |
| added | 2022-04-15 | — / — | retest_observed / 2022-04-11 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2022-04-17 | — / — | retest_observed / 2022-04-11 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2022-04-18 | — / — | retest_observed / 2022-04-11 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2022-04-20 | — / — | reversal_observed / 2022-04-20 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2022-05-11 | — / — | retest_observed / 2022-05-09 | 종가 이탈일에도 재시험 접촉 사실을 보존 |
| added | 2022-09-08 | — / — | reversal_observed / 2022-09-06 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2022-09-14 | — / — | reversal_observed / 2022-09-06 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2023-06-09 | — / — | reversal_observed / 2023-06-05 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2023-06-11 | — / — | reversal_observed / 2023-06-05 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2023-06-12 | — / — | retest_observed / 2023-06-05 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2023-06-12 | — / — | reversal_observed / 2023-06-05 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2023-06-13 | — / — | retest_observed / 2023-06-05 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2023-06-13 | — / — | reversal_observed / 2023-06-05 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2023-06-14 | — / — | anchor_expired / 2023-06-05 | 반전 모양 재시험 이후에도 기준을 유지하여 수명 종료 기록 |
| added | 2023-12-14 | — / — | reversal_observed / 2023-12-11 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2023-12-16 | — / — | retest_observed / 2023-12-11 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2023-12-17 | — / — | retest_observed / 2023-12-11 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2023-12-18 | — / — | retest_observed / 2023-12-11 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2023-12-20 | — / — | anchor_expired / 2023-12-11 | 반전 모양 재시험 이후에도 기준을 유지하여 수명 종료 기록 |
| added | 2024-01-28 | — / — | reversal_observed / 2024-01-22 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2024-04-05 | — / — | reversal_observed / 2024-04-02 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2024-04-07 | — / — | reversal_observed / 2024-04-02 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2024-04-11 | — / — | anchor_expired / 2024-04-02 | 반전 모양 재시험 이후에도 기준을 유지하여 수명 종료 기록 |
| added | 2024-07-01 | — / — | reversal_observed / 2024-06-24 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2024-07-05 | — / — | reversal_observed / 2024-07-04 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2024-08-10 | — / — | reversal_observed / 2024-08-05 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2024-08-29 | — / — | reversal_observed / 2024-08-27 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2024-08-30 | — / — | reversal_observed / 2024-08-27 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2025-11-12 | — / — | retest_observed / 2025-11-04 | 반전 모양으로 기준을 소진하거나 반복 접촉을 진입 중복으로 지우지 않음 |
| added | 2025-12-06 | — / — | reversal_observed / 2025-12-01 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2025-12-08 | — / — | reversal_observed / 2025-12-01 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2026-01-22 | — / — | reversal_observed / 2026-01-20 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2026-01-23 | — / — | reversal_observed / 2026-01-20 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2026-01-30 | — / — | reversal_observed / 2026-01-29 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |
| added | 2026-02-09 | — / — | reversal_observed / 2026-02-05 | 기존 기준 추적 중 또는 다른 사건과 겹친 반전 모양도 독립 기록 |

## 검사 범위와 미검증

기존 모양 함수를 매 접두 구간에서 다시 실행한 1,762개 구간, 1,553,203개 과거 관찰 비교에서 불일치가 없었다. 합성 미래 32일과 미래에 처음 알려지는 지지를 추가해도 과거의 사건 ID와 모든 필드가 같았다.

실제 지지 경로와 분리한 합성 13개 시나리오에서 89개 접두 구간과 각 32일 확장도 일치했다. 세 반전 모양, 기존 기준 중 새 반응, 겹친 장대음봉, 새 하단 반응, 지지 이탈 후 회복을 포함한다.

보호 파일 232개는 실행 전후 해시가 같다. 기존 앱 코드·사용자 DB·Streamlit·골든값과 기존 실험 설정을 수정하지 않았다. 운영 앱 회귀 검사는 실행하지 않았다.

실제 지지에서의 반응과 트랩 후보는 지지 이력이 없어서 검증 불가다. 현재 도형이나 스냅샷을 과거에 소급 적용하지 않았다. 합성 지지의 성공은 실제 시장 경로나 성과 검증을 뜻하지 않는다.

재시험 세부 분류: `{'by_shape': {'none': 12, 'doji': 4, 'hammer': 1}, 'by_close_location': {'above_reference_band': 9, 'within_reference_band': 7, 'below_reference_band': 1}, 'far_rebounded': 4, 'lower_wick_contact': 16}`. 높게 마감한 접촉과 가격대 안 마감은 분리되며, 가격대 아래 마감한 접촉도 무효화 사건과 함께 남긴다.

`results_v02/events.csv`는 사건별 모든 참조와 가격·모양·거래량을, `v01_diff.csv`는 유지 항목까지 포함한 비교를 제공한다. 전체 봉 JSONL은 로컬 생성물이며 Git에 넣지 않는다. 새 사건 스키마와 재현·기기 인계는 README 및 HANDOFF_V02.md를 참고한다.
