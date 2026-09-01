"""신호 표시 문자열과 방향(long/short/reference)을 함께 들고 다니는 구조.

방향은 "이 신호가 롱/숏 카운트에 들어가는지"를 결정하는 유일한 기준 - 화면 표시
문구가 바뀌어도 이 값은 안 바뀌므로, 카운트 로직이 문자열을 파싱할 필요가 없다.
"""
from collections import namedtuple

Signal = namedtuple("Signal", ["text", "direction"])  # direction: "long" | "short" | "reference"
