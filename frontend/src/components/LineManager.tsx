import type { ManualLine } from "../types";
import styles from "./LineManager.module.css";

interface Props {
  lines: ManualLine[];
  onDelete: (lineId: number) => void;
  // true면 목록만 보여주고 삭제 버튼은 없다(1W: 일봉에서 그린 선/존은 1D에서만 편집)
  readOnly?: boolean;
}

// app.py의 "그은 선 관리" expander(목록 + 삭제 버튼)를 그대로 재현.
export default function LineManager({ lines, onDelete, readOnly = false }: Props) {
  if (lines.length === 0) return null;

  return (
    <details className={styles.details} open={false}>
      <summary>{readOnly ? `그은 선 (${lines.length}개) · 편집은 1D에서` : `그은 선 관리 (${lines.length}개)`}</summary>
      <ul className={styles.list}>
        {lines.map((line) => (
          <li key={line.id} className={styles.row}>
            <span>{line.label}</span>
            {!readOnly && <button type="button" onClick={() => onDelete(line.id)}>삭제</button>}
          </li>
        ))}
      </ul>
    </details>
  );
}
