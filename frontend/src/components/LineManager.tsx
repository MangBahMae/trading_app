import type { ManualLine } from "../types";
import styles from "./LineManager.module.css";

interface Props {
  lines: ManualLine[];
  onDelete: (lineId: number) => void;
}

// app.py의 "그은 선 관리" expander(목록 + 삭제 버튼)를 그대로 재현.
export default function LineManager({ lines, onDelete }: Props) {
  if (lines.length === 0) return null;

  return (
    <details className={styles.details} open={false}>
      <summary>그은 선 관리 ({lines.length}개)</summary>
      <ul className={styles.list}>
        {lines.map((line) => (
          <li key={line.id} className={styles.row}>
            <span>{line.label}</span>
            <button type="button" onClick={() => onDelete(line.id)}>삭제</button>
          </li>
        ))}
      </ul>
    </details>
  );
}
