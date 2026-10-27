"""기능 1(신호 스캐너) 개별 기능 on/off 플래그.

코드를 지우지 않고 끄기만 한다 - 나중에 True로 바꾸면 그대로 되살아난다
(rsi_overbought_oversold.py / divergence.py 등 계산 모듈은 그대로 있고, pipeline.py가
이 플래그를 보고 호출 여부만 정한다). 플래그를 켠 결과가 원본(scripts/)과 같은지는
tests/test_regression_pipeline.py의 "플래그 복원" 테스트가 확인한다.

pipeline.py는 `feature_flags.ENABLE_X`처럼 모듈 속성으로 읽는다(from import 금지) -
테스트가 값을 바꿔 켜 볼 수 있게 하기 위함.

다우 라벨(HH/HL/LH/LL)과 RSI 과매수는 커밋 7c0e6c0에서 이미 삭제됐고(복원하지 않기로 결정),
그래서 이 파일에 플래그가 없다.
"""

# RSI 과매도 신호 ("RSI 과매도 진입/유지 중", 롱 카운트)
ENABLE_RSI_OVERSOLD_SIGNAL = False

# RSI 다이버전스 차트 마커 (카운트 신호는 아니고 차트 참고 표시)
ENABLE_DIVERGENCE_MARKERS = False
