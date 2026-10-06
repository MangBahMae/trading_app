"""신호 표시 문자열과 방향(long/short/reference)을 함께 들고 다니는 구조.

방향은 "이 신호가 롱/숏 카운트에 들어가는지"를 결정하는 유일한 기준 - 화면 표시
문구가 바뀌어도 이 값은 안 바뀌므로, 카운트 로직이 문자열을 파싱할 필요가 없다.

source/tier/evidence는 신호에 "자리/등급/근거"를 붙이기 위한 확장 필드. 지금은 존
신호만 source를 채우고 나머지는 비어 있다. ref_id/ref_created_at은 그 신호를 만든
도형(지금은 존)의 lines.id / lines.created_at - 사후적으로 그린 도형이 형성 시점
이전 캔들에도 신호를 내므로, 백테스트가 생성일 이후 신호만 골라낼 수 있게 남긴다.
기존 위치 인자 호출 Signal(text, direction)이 그대로 돌도록 전부 뒤에 두고 기본값을
준다. evidence 기본값은 인스턴스 간에 공유되므로 가변 리스트 대신 튜플을 쓴다(API
직렬화 때 list로 변환).
"""
from typing import NamedTuple


class Signal(NamedTuple):
    text: str
    direction: str  # "long" | "short" | "reference"
    source: str | None = None  # "zone" | "line" | "ema" | None
    tier: str | None = None  # "strong" | "mid" | "weak" | None
    evidence: tuple[str, ...] = ()
    ref_id: int | None = None  # 신호를 만든 도형(존)의 lines.id
    ref_created_at: str | None = None  # 그 도형의 lines.created_at (ISO 문자열)
