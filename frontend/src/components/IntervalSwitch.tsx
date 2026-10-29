import type { Timeframe } from "../types";
import styles from "./IntervalSwitch.module.css";

const OPTIONS: Timeframe[] = ["1D", "1W"];

interface Props {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
}

// 상단 바의 봉 간격 전환(1D 일봉 / 1W 주봉) - 하나만 활성인 라디오 버튼 그룹.
export default function IntervalSwitch({ value, onChange }: Props) {
  return (
    <div className={styles.group} role="radiogroup" aria-label="봉 간격">
      {OPTIONS.map((tf) => (
        <button
          key={tf}
          type="button"
          role="radio"
          aria-checked={value === tf}
          aria-label={tf}
          className={value === tf ? styles.buttonActive : styles.button}
          onClick={() => onChange(tf)}
        >
          {tf}
        </button>
      ))}
    </div>
  );
}
