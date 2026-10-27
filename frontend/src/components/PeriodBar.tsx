import type { ReactNode } from "react";
import styles from "./PeriodBar.module.css";

export interface PeriodOption {
  value: string;   // 접근성 이름이자 값 (예: "최근 1년")
  short: string;   // 화면 글자 (예: "1Y")
}

interface Props {
  options: PeriodOption[];
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode; // 오른쪽 안내문 (그리기 모드 설명)
}

// 차트 아래 기간 바 - 3M / 6M / 1Y / 전체 (예전 라디오 대체). 하나만 활성.
export default function PeriodBar({ options, value, onChange, hint }: Props) {
  return (
    <div className={styles.bar}>
      <div className={styles.group} role="radiogroup" aria-label="표시 기간">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={value === opt.value}
            aria-label={opt.value}
            className={value === opt.value ? styles.buttonActive : styles.button}
            onClick={() => onChange(opt.value)}
          >
            {opt.short}
          </button>
        ))}
      </div>
      {hint && <div className={styles.hint}>{hint}</div>}
    </div>
  );
}
