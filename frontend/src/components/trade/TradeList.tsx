import type { Trade, TradeStatus } from "../../types";
import styles from "./TradeList.module.css";

const STATUS_LABEL: Record<TradeStatus, string> = { draft: "임시저장", open: "진행중", closed: "완료" };

interface Props {
  trades: Trade[];
  statusFilter: TradeStatus | "all";
  onFilterChange: (status: TradeStatus | "all") => void;
  onSelect: (id: number) => void;
  onNew: () => void;
}

export default function TradeList({ trades, statusFilter, onFilterChange, onSelect, onNew }: Props) {
  return (
    <div>
      <div className={styles.toolbar}>
        <div className={styles.filters}>
          {(["all", "draft", "open", "closed"] as const).map((s) => (
            <button
              key={s}
              type="button"
              className={statusFilter === s ? styles.filterActive : styles.filter}
              onClick={() => onFilterChange(s)}
            >
              {s === "all" ? "전체" : STATUS_LABEL[s]}
            </button>
          ))}
        </div>
        <button type="button" className={styles.newButton} onClick={onNew}>+ 새 계획 작성</button>
      </div>

      {trades.length === 0 ? (
        <p className={styles.empty}>매매 기록이 없습니다.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>ID</th><th>상태</th><th>방향</th><th>평단</th><th>SL</th>
              <th>1R</th><th>실현 R</th><th>작성 시각</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} onClick={() => onSelect(t.id)} className={styles.row}>
                <td>{t.id}</td>
                <td><span className={styles[`badge_${t.status}`]}>{STATUS_LABEL[t.status]}</span></td>
                <td>{t.direction === "long" ? "롱" : "숏"}</td>
                <td>{t.avg_entry?.toLocaleString("en-US") ?? "-"}</td>
                <td>{t.stop_loss?.toLocaleString("en-US") ?? "-"}</td>
                <td>{t.risk_amount ? t.risk_amount.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "-"}</td>
                <td className={t.realized_r !== null && t.realized_r < 0 ? styles.negativeR : styles.positiveR}>
                  {t.realized_r !== null && t.realized_r !== undefined ? `${t.realized_r.toFixed(2)}R` : "-"}
                </td>
                <td>{new Date(t.planned_at).toLocaleString("ko-KR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
