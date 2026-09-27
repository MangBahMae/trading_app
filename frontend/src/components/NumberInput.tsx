import { useEffect, useState } from "react";

interface Props {
  id?: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  className?: string;
}

/**
 * 숫자 입력을 문자열 버퍼로 감싼 컨트롤드 <input type="number">.
 *
 * 흔한 버그(전부 지워도 "0"이 남고, 그 상태에서 이어 타이핑하면 "0100"처럼
 * 붙어버림)의 원인: value={상태값(숫자)} + onChange={(e) =>
 * setState(parseFloat(e.target.value) || 0)} 패턴은, 사용자가 필드를 비우는
 * 순간(e.target.value === "") parseFloat("")가 NaN이라 즉시 0으로 되돌아가고
 * 리렌더 때 DOM에 "0"이 다시 박힌다 - 그 뒤로는 커서가 그 "0" 뒤에 있는 채로
 * 계속 타이핑되니 "0100"이 만들어진다.
 *
 * 해결: DOM에 실제로 보이는 텍스트를 별도 문자열 state로 그대로 들고 있다가
 * (비어있으면 비어있는 채로 둠 - 강제로 "0"을 채워넣지 않음), 파싱 가능할
 * 때만 부모에 숫자로 알려준다. 부모 쪽 value가 "외부에서"(예: 계산기로
 * 채우기, 다른 필드 변경에 따른 프로그래밍적 갱신) 바뀐 경우에만 텍스트를
 * 그 값으로 동기화하고, 이 컴포넌트 자신의 onChange로 인한 되먹임에는
 * 손대지 않는다(그래야 타이핑 중간에 커서가 안 튐).
 */
export default function NumberInput({ id, value, onChange, min, max, step, disabled, className }: Props) {
  const [text, setText] = useState(String(value));

  useEffect(() => {
    const parsed = parseFloat(text);
    const alreadyInSync = parsed === value || (text === "" && value === 0);
    if (!alreadyInSync) {
      setText(String(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <input
      id={id}
      type="number"
      className={className}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      value={text}
      onChange={(e) => {
        const next = e.target.value;
        setText(next);
        const parsed = parseFloat(next);
        onChange(Number.isNaN(parsed) ? 0 : parsed);
      }}
    />
  );
}
