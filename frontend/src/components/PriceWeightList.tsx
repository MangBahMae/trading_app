import { useEffect, useRef, useState } from "react";
import type { PriceWeightRow } from "../types";
import { formatUsdtKrw } from "../utils/krwFormat";
import styles from "./PriceWeightList.module.css";

interface Props {
  label: string; // "진입" | "TP"
  minItems: number; // 진입=1, TP=0 (기존 scripts/position_sizing.py와 동일)
  defaultPrice?: number;
  exchangeRate: number;
  onChange: (rows: { price: number; weight: number }[]) => void;
}

/**
 * 가격+비중% 행을 추가/삭제할 수 있는 동적 리스트.
 *
 * scripts/position_sizing.py의 _render_price_weight_list()를 그대로 재현:
 * - 행이 1개뿐이면 비중은 무조건 100%로 고정 표시(수정 불가)
 * - 행마다 안정적인 id(추가 순서 기반, 삭제돼도 재사용 안 함)를 key로 써서
 *   중간 행 삭제 시 나머지 행들의 값이 꼬이지 않게 함
 * - 가격 옆에 USDT->원화 환산 캡션 표시
 */
export default function PriceWeightList({
  label,
  minItems,
  defaultPrice = 0,
  exchangeRate,
  onChange,
}: Props) {
  const nextId = useRef(minItems);
  const [rows, setRows] = useState<PriceWeightRow[]>(() =>
    Array.from({ length: minItems }, (_, i) => ({
      id: i,
      price: defaultPrice,
      weight: minItems === 1 ? 100 : 0,
    })),
  );

  useEffect(() => {
    // 행이 1개로 줄어들면(또는 처음부터 1개면) 비중을 무조건 100%로 정정한다
    // (Streamlit 버전과 동일 - 아래 렌더링에서도 이 경우 입력을 비활성화한다).
    if (rows.length === 1 && rows[0].weight !== 100) {
      setRows([{ ...rows[0], weight: 100 }]);
      return;
    }
    onChange(rows.map((r) => ({ price: r.price, weight: r.weight })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const updateRow = (id: number, patch: Partial<PriceWeightRow>) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const deleteRow = (id: number) => {
    setRows((prev) => prev.filter((r) => r.id !== id));
  };

  const addRow = () => {
    const id = nextId.current++;
    setRows((prev) => [...prev, { id, price: defaultPrice, weight: 0 }]);
  };

  const weightSum = rows.reduce((sum, r) => sum + r.weight, 0);
  const weightSumInvalid = rows.length > 1 && Math.abs(weightSum - 100) > 0.01;

  return (
    <div className={styles.list}>
      {rows.map((row, idx) => {
        const priceId = `${label}-${row.id}-price`;
        const weightId = `${label}-${row.id}-weight`;
        return (
        <div key={row.id} className={styles.row}>
          <div className={styles.priceCell}>
            <label className={styles.smallLabel} htmlFor={priceId}>
              {label} {idx + 1} 가격
            </label>
            <input
              id={priceId}
              type="number"
              value={row.price}
              min={0}
              step={1}
              onChange={(e) => updateRow(row.id, { price: parseFloat(e.target.value) || 0 })}
            />
            {row.price > 0 && exchangeRate > 0 && (
              <div className={styles.caption}>
                {row.price.toLocaleString("en-US")} USDT {formatUsdtKrw(row.price, exchangeRate)}
              </div>
            )}
          </div>

          <div className={styles.weightCell}>
            <label className={styles.smallLabel} htmlFor={weightId}>
              {label} {idx + 1} 비중%
            </label>
            {rows.length === 1 ? (
              <input id={weightId} type="number" value={100} disabled />
            ) : (
              <input
                id={weightId}
                type="number"
                value={row.weight}
                min={0}
                max={100}
                step={1}
                onChange={(e) => updateRow(row.id, { weight: parseFloat(e.target.value) || 0 })}
              />
            )}
          </div>

          <div className={styles.deleteCell}>
            {rows.length > minItems && (
              <button type="button" onClick={() => deleteRow(row.id)}>
                삭제
              </button>
            )}
          </div>
        </div>
        );
      })}

      {rows.length > 1 && (
        <div className={weightSumInvalid ? styles.weightWarning : styles.weightOk}>
          비중 합계: {weightSum.toFixed(2)}%{weightSumInvalid ? " (100%가 아닙니다)" : ""}
        </div>
      )}

      {rows.length === 0 && <div className={styles.caption}>{label} 없음</div>}

      <button type="button" className={styles.addButton} onClick={addRow}>
        + {label} 추가
      </button>
    </div>
  );
}
