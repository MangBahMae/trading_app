import type { Trade } from "../../types";
import styles from "./TradeDetail.module.css";

const EXIT_REASON_LABEL: Record<string, string> = {
  tp: "TP 도달", sl: "SL 도달", invalidation: "무효화 도달", manual: "계획 외 임의 청산",
};

interface Props {
  trade: Trade;
  onBack: () => void;
  onClose: () => void; // "청산 기록" 버튼
  onDelete: () => void;
}

// 기획서 "3. 계획 대비 실제 비교" - 화면 형태는 미정이라 명시돼있어서, 이번
// phase에서는 계획 필드 전체 표시 + (closed면) 실제 청산 내역을 나란히 보여주는
// 단순한 형태로 구현. 정식 비교 UI는 나중에 다시 다룰 예정.
export default function TradeDetail({ trade, onBack, onClose, onDelete }: Props) {
  return (
    <div className={styles.detail}>
      <div className={styles.header}>
        <button type="button" onClick={onBack}>← 목록으로</button>
        <div className={styles.headerActions}>
          {trade.status === "open" && (
            <button type="button" className={styles.primaryButton} onClick={onClose}>청산 기록 작성</button>
          )}
          <button type="button" className={styles.dangerButton} onClick={onDelete}>삭제</button>
        </div>
      </div>

      <h2>#{trade.id} · {trade.direction === "long" ? "롱" : "숏"} · {trade.status === "closed" ? "완료" : trade.status === "open" ? "진행중" : "임시저장"}</h2>

      <section className={styles.section}>
        <h3>진입 전 계획</h3>
        <dl className={styles.dl}>
          <dt>진입 근거</dt><dd>{trade.entry_rationale || "-"}</dd>
          <dt>기능1 신호</dt><dd>{trade.signal_tags.length ? trade.signal_tags.join(", ") : "-"}</dd>
          <dt>무효화 지점</dt><dd>{trade.invalidation_note || "-"} ({trade.invalidation_price?.toLocaleString("en-US") ?? "-"})</dd>
          <dt>SL</dt><dd>{trade.stop_loss?.toLocaleString("en-US") ?? "-"}</dd>
          <dt>진입가</dt>
          <dd>{trade.entries.map((e) => `${e.price.toLocaleString("en-US")} (${e.weight}%)`).join(", ")}</dd>
          <dt>TP</dt>
          <dd>{trade.take_profits.map((t) => `${t.price.toLocaleString("en-US")} (${t.weight}%)`).join(", ")}</dd>
          <dt>평단</dt><dd>{trade.avg_entry?.toLocaleString("en-US") ?? "-"}</dd>
          <dt>증거금 / 레버리지</dt><dd>{trade.margin?.toLocaleString("en-US") ?? "-"} / {trade.leverage ?? "-"}배</dd>
          <dt>수량 (환산)</dt><dd>{trade.quantity?.toFixed(6) ?? "-"}</dd>
          <dt>1R (통화)</dt><dd>{trade.risk_amount?.toLocaleString("en-US", { maximumFractionDigits: 0 }) ?? "-"}</dd>
          <dt>작성 시각</dt><dd>{new Date(trade.planned_at).toLocaleString("ko-KR")}</dd>
        </dl>
      </section>

      {trade.status === "closed" && (
        <section className={styles.section}>
          <h3>청산 후 기록 (계획 대비 실제)</h3>
          <dl className={styles.dl}>
            <dt>청산가 / 실현손익</dt>
            <dd>
              {(trade.exits ?? []).map((e, i) => (
                <div key={i}>{e.price.toLocaleString("en-US")} ({e.weight}%) → {e.realized_pnl.toLocaleString("en-US")}</div>
              ))}
            </dd>
            <dt>청산 사유</dt><dd>{trade.exit_reason ? EXIT_REASON_LABEL[trade.exit_reason] : "-"}</dd>
            <dt>자유 메모</dt><dd>{trade.exit_memo || "-"}</dd>
            <dt>실현손익 합계</dt><dd>{trade.realized_pnl_total?.toLocaleString("en-US") ?? "-"}</dd>
            <dt className={styles.highlight}>실현 R</dt>
            <dd className={trade.realized_r !== null && (trade.realized_r ?? 0) < 0 ? styles.negativeR : styles.positiveR}>
              {trade.realized_r !== null && trade.realized_r !== undefined ? `${trade.realized_r.toFixed(2)}R` : "-"}
            </dd>
            <dt>청산 시각</dt><dd>{trade.closed_at ? new Date(trade.closed_at).toLocaleString("ko-KR") : "-"}</dd>
          </dl>

          <div className={styles.comparisonNote}>
            계획: {trade.direction === "long" ? "SL" : "SL"} {trade.stop_loss?.toLocaleString("en-US")} /
            {" "}TP {trade.take_profits.map((t) => t.price.toLocaleString("en-US")).join(", ")} /
            {" "}무효화 {trade.invalidation_price?.toLocaleString("en-US")}
            {" "}→ 실제: {trade.exit_reason ? EXIT_REASON_LABEL[trade.exit_reason] : "-"}로 청산
          </div>
        </section>
      )}
    </div>
  );
}
