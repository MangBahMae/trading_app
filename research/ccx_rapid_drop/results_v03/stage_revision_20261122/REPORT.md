# 11/22 급락·관찰·일반 전후 평가

기준 `04e4ad9a52e78e1de3c718925cf5525f49c99d00`의 Git 계산과 새 단일 엔진/API를 고정 마감 일봉 1,762개로 비교했다. 실제 지지 입력은 0개다.

## 정의와 분모

- old_native: 원래 active 전체가 경고였다. eased/normal을 경보 해제의 일반 복귀 **대응값**으로 묶었으며 실제 구안 관찰 단계는 없었다.
- old_speed_mapping: 비교용 진단 분할이다. active+strong을 강한 경고, active+비strong을 관찰 대응, eased/normal을 일반 대응으로 묶었다. 구안에 이 3단계 UI가 있었다는 뜻이 아니다.
- new_native: 실제 sharp_drop/post_drop/normal. 추가 가속은 strong과 별도이므로 독립 집계한다.
- 연속 경고 run과 첫 경고부터 일반 복귀까지 episode를 구분한다. 한 episode 안의 관찰→재급락은 같은 episode에 포함한다.
- 관찰/일반 복귀까지 봉수는 첫 경고 봉을 제외한 인덱스 차이다. 초기 상태가 이미 구간 안이면 left-censored, 데이터 끝까지 미복귀면 right-censored로 별도 표시한다.
- 3봉 비율은 전환일을 제외한 **다음 3개 봉**을 모두 가진 전환만 분모에 넣는다. 관찰 재악화는 중간 NORMAL 전까지의 재급락만 세며 NORMAL 이후 새 급락은 일반 복귀 지표에만 넣는다. 불완전 표본의 조기 재발도 본 분자/분모에서 제외하고 별도 표시한다.
- P90은 정렬된 표본의 ceil(0.9×N)번째인 empirical nearest-rank다. N=0은 0%가 아니라 NA다.
- 실제 강한 하락일은 old/new 각각 169/169일, 추가 가속일은 148/148일이다. 경고 일수 감소는 상태 표시 구분의 효과이며 강한 하락 판정일이 줄었다는 뜻이 아니다.

| 모델 | 경고 일수 | 관찰 일수 | 일반 대응 일수 | 완료 경고 run N / median / P90 | episode 경고일 median/P90 | 관찰까지 median/P90 | 일반까지 median/P90 |
|---|---:|---:|---:|---|---|---|---|
| old_native | 504 | 0 | 1256 | 79 / 5 / 12 | 5/12 | NA/NA | 5/12 |
| old_speed_mapping | 169 | 335 | 1256 | 99 / 2 / 3 | 2/5 | 1/3 | 5/12 |
| new_native | 169 | 216 | 1375 | 99 / 2 / 3 | 2.0000/4 | 1.0000/3 | 4.0000/7 |

| 모델 | 관찰 후 다음3봉 재급락 분자/분모 | 비율 | 일반 복귀 후 다음3봉 새 급락 분자/분모 | 비율 |
|---|---|---|---|---|
| old_native | NA | NA | 17/79 | 21.52% |
| old_speed_mapping | 13/99 | 13.13% | 17/79 | 21.52% |
| new_native | 11/99 | 11.11% | 19/88 | 21.59% |

검열 건수와 각 날짜의 분모 포함 여부는 summary.json 및 metrics_* 표에 있다. 구안 active 속도 분할은 가상 대응이므로 native 변경 효과와 혼동하지 않는다.

## 후보 평가 — 미래는 평가에만 사용

발행 봉의 종가는 체결가가 아니다. 다음5봉 최대 고가/최저 저가의 발행종가 대비 가격거리를 보여줄 뿐 손익·실현 수익률·비중·비용 모델이 아니다. 발행 봉 자체의 high/low는 제외했다.

| 버전 | 날짜 | 원래 유형 | 대응 계열 | 발행 종가 | 다음5봉 수 | 최대 고가 거리% | 최저 저가 거리% |
|---|---|---|---|---:|---:|---:|---:|
| old | 2023-06-11 | retest_long | auto_retest_long | 25925.55 | 5 | 2.2852 | -4.3415 |
| new | 2023-06-11 | auto_retest_long | auto_retest_long | 25925.55 | 5 | 2.2852 | -4.3415 |

유형별 요약에서 거리 값은 `median / P90 / 전체 최대(고가) 또는 전체 최저(저가)` 순서다. 미표본은 —이며 유지 후보는 새 발행으로 세지 않았다.

| 버전 | 후보 계열 | 발행 | 고유 ID | ID 중복 | 의미키 중복 | 5봉 완전/검열 | 고가 거리% med/P90/max | 저가 거리% med/P90/min |
|---|---|---:|---:|---:|---:|---|---|---|
| old | manual_first_long | 0 | 0 | 0 | 0 | 0/0 | — | — |
| old | manual_retest_long | 0 | 0 | 0 | 0 | 0/0 | — | — |
| old | auto_retest_long | 1 | 1 | 0 | 0 | 1/0 | 2.2852 / 2.2852 / 2.2852 | -4.3415 / -4.3415 / -4.3415 |
| new | manual_first_long | 0 | 0 | 0 | 0 | 0/0 | — | — |
| new | manual_retest_long | 0 | 0 | 0 | 0 | 0/0 | — | — |
| new | auto_retest_long | 1 | 1 | 0 | 0 | 1/0 | 2.2852 / 2.2852 / 2.2852 | -4.3415 / -4.3415 / -4.3415 |

과거 retest_long은 실데이터에 수동 지지가 없다는 확인 범위에서 auto_retest_long 대응으로만 비교한다. 수동 두 계열의 0개는 성공·실패 평가가 아니라 실제 지지 이력이 없는 미표본이다.

## 검증과 한계

원시 사건 전후: `{'retained': 73, 'added': 26, 'removed': 23, 'reclassified': 0, 'reference_updated': 73}`. API 발행 전후: `{'retained': 154, 'added': 14, 'removed': 32, 'reclassified': 1, 'reference_updated': 73}`.
원시 ID 체계가 바뀌어도 같은 유형·날짜·실질 기준이 대응되면 삭제/추가로 부풀리지 않았다. ID 교체 수와 참조 갱신은 summary.json/changes.csv에 별도로 남겼다.
불변성: `{'prefixes': 1762, 'historical_state_comparisons': 1553203, 'history_prefix_tips_checked': 1762, 'shape_recomputed_each_prefix': True, 'future_days': 32, 'future_support_injected': True, 'mismatches': 0}`. 중복·후보 연결: `{'history_ids': 242, 'candidate_keys': 1, 'duplicate_ids': 0, 'reissued_candidates': 0, 'invalid_candidate_links': 0}`. 상태 독립식: `{'rows': 1762, 'mismatches': 0, 'recovery_anchor': 'A=C[h-2]', 'strong_bar_cannot_end_warning': True, 'price_end': 'C>=A on two consecutive bars after h', 'speed_end': 't-h>=3 and today v>-.01 and at least two of latest three v>-.01', 'new_closing_low_not_required': True}`.
모든 접두 구간에서 기존 모양부터 재계산했고, 미래 봉/미래 지지 추가 뒤 과거 market·summary·유지·history·신호 ID를 비교했다. 미래5봉 평가값은 이 판정 경로에 입력하지 않았다.
수동 첫 반응·재시험과 지지 이탈 후 회복의 실제 경로는 지지 이력이 없어 검증 불가다. 합성 지지 결과는 별도 표시한다. 임계값은 최적화하지 않았다.
SQLite 연결과 외부 요청은 runner에서 금지했다. 과거 D44→F046 DB 해시 불일치와 기존 사고 증거는 보존하며, 이번 계산으로 사고 전 보존 성공을 주장하지 않는다.
