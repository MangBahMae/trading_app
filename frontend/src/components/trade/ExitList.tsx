import { useEffect, useRef, useState } from "react";
import NumberInput from "../NumberInput";
import type { ExitItem } from "../../types";
import styles from "../PriceWeightList.module.css";

interface Row extends ExitItem {
  id: number;
}

interface Props {
  onChange: (rows: ExitItem[]) => void;
}

/**
 * 청산 기록용 동적 리스트 - 가격+비중%+실현손익(직접 입력) 3개 필드.
 * PriceWeightList와 같은 id-안정 패턴이지만 realized_pnl 칸이 하나 더 있어서
 * 별도 컴포넌트로 분리했다(기획서: "청산가/실현손익 배열" - 각 분할 청산마다
 * 실현손익을 직접 입력받고, 가격에서 역산하지 않는다 - 수수료/슬리피지 등으로
 * 실제 손익이 순수 가격差와 다를 수 있어서 기록의 정확성을 우선).
 */
export default function ExitList({ onChange }: Props) {
  const nextId = useRef(1);
  const [rows, setRows] = useState<Row[]>([{ id: 0, price: 0, weight: 100, realized_pnl: 0 }]);

  useEffect(() => {
    if (rows.length === 1 && rows[0].weight !== 100) {
      setRows([{ ...rows[0], weight: 100 }]);
      return;
    }
    onChange(rows.map(({ price, weight, realized_pnl }) => ({ price, weight, realized_pnl })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const updateRow = (id: number, patch: Partial<Row>) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };
  const deleteRow = (id: number) => setRows((prev) => prev.filter((r) => r.id !== id));
  const addRow = () => {
    const id = nextId.current++;
    setRows((prev) => [...prev, { id, price: 0, weight: 0, realized_pnl: 0 }]);
  };

  const weightSum = rows.reduce((sum, r) => sum + r.weight, 0);
  const weightSumInvalid = rows.length > 1 && Math.abs(weightSum - 100) > 0.01;
  const totalPnl = rows.reduce((sum, r) => sum + r.realized_pnl, 0);

  return (
    <div className={styles.list}>
      {rows.map((row, idx) => (
        <div key={row.id} className={styles.row} style={{ gridTemplateColumns: "2fr 1.3fr 2fr auto" }}>
          <div className={styles.priceCell}>
            <label className={styles.smallLabel} htmlFor={`exit-${row.id}-price`}>청산 {idx + 1} 가격</label>
            <NumberInput
              id={`exit-${row.id}-price`} min={0} step={1} value={row.price}
              onChange={(v) => updateRow(row.id, { price: v })}
            />
          </div>
          <div className={styles.weightCell}>
            <label className={styles.smallLabel} htmlFor={`exit-${row.id}-weight`}>비중%</label>
            {rows.length === 1 ? (
              <NumberInput id={`exit-${row.id}-weight`} value={100} onChange={() => {}} disabled />
            ) : (
              <NumberInput
                id={`exit-${row.id}-weight`} min={0} max={100} step={1} value={row.weight}
                onChange={(v) => updateRow(row.id, { weight: v })}
              />
            )}
          </div>
          <div className={styles.priceCell}>
            <label className={styles.smallLabel} htmlFor={`exit-${row.id}-pnl`}>실현손익</label>
            <NumberInput
              id={`exit-${row.id}-pnl`} step={1} value={row.realized_pnl}
              onChange={(v) => updateRow(row.id, { realized_pnl: v })}
            />
          </div>
          <div className={styles.deleteCell}>
            {rows.length > 1 && (
              <button type="button" onClick={() => deleteRow(row.id)}>삭제</button>
            )}
          </div>
        </div>
      ))}

      {rows.length > 1 && (
        <div className={weightSumInvalid ? styles.weightWarning : styles.weightOk}>
          비중 합계: {weightSum.toFixed(2)}%{weightSumInvalid ? " (100%가 아닙니다)" : ""}
        </div>
      )}
      <div className={styles.weightOk}>실현손익 합계: {totalPnl.toLocaleString("en-US")}</div>

      <button type="button" className={styles.addButton} onClick={addRow}>+ 청산 추가</button>
    </div>
  );
}
