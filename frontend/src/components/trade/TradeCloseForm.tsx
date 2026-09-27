import { useState } from "react";
import ExitList from "./ExitList";
import { closeTrade, TradeApiError } from "../../api/trades";
import type { ExitItem, ExitReason, Trade } from "../../types";
import styles from "./TradeForm.module.css";

const WARNING_MESSAGES_KR: Record<string, string> = {
  exits_empty: "청산 내역을 최소 1건 입력해주세요",
  exits_price_invalid: "청산가는 0보다 커야 합니다",
  exits_weight_sum_invalid: "청산 비중 합이 100%가 아닙니다",
  invalid_exit_reason: "청산 사유를 선택해주세요",
  trade_already_closed: "이미 청산 완료된 매매입니다",
  trade_not_open: "진행중 상태가 아닌 매매는 청산 기록을 남길 수 없습니다",
};

const EXIT_REASON_OPTIONS: { value: ExitReason; label: string }[] = [
  { value: "tp", label: "TP 도달" },
  { value: "sl", label: "SL 도달" },
  { value: "invalidation", label: "무효화 도달" },
  { value: "manual", label: "계획 외 임의 청산" },
];

interface Props {
  trade: Trade;
  onSaved: (trade: Trade) => void;
  onCancel: () => void;
}

// 기획서 "2. 청산 후 기록" 폼.
export default function TradeCloseForm({ trade, onSaved, onCancel }: Props) {
  const [exits, setExits] = useState<ExitItem[]>([]);
  const [exitReason, setExitReason] = useState<ExitReason | "">("");
  const [exitMemo, setExitMemo] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!exitReason) {
      setErrors(["invalid_exit_reason"]);
      return;
    }
    setSaving(true);
    setErrors([]);
    try {
      const updated = await closeTrade(trade.id, { exits, exit_reason: exitReason, exit_memo: exitMemo || null });
      onSaved(updated);
    } catch (err) {
      setErrors(err instanceof TradeApiError ? err.errors : [String(err)]);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.form}>
      <h2>청산 후 기록 - #{trade.id}</h2>
      <p style={{ fontSize: "0.85rem", color: "var(--muted-color)" }}>
        {trade.direction === "long" ? "롱" : "숏"} · 평단 {trade.avg_entry?.toLocaleString("en-US")} · SL {trade.stop_loss?.toLocaleString("en-US")}
      </p>

      <h3>청산가 / 실현손익</h3>
      <ExitList onChange={setExits} />

      <label className={styles.fieldLabel}>청산 사유 (필수)</label>
      <div className={styles.radioGroup}>
        {EXIT_REASON_OPTIONS.map((opt) => (
          <label key={opt.value}>
            <input
              type="radio" checked={exitReason === opt.value}
              onChange={() => setExitReason(opt.value)}
            />
            {opt.label}
          </label>
        ))}
      </div>

      <label className={styles.fieldLabel} htmlFor="exit-memo">자유 메모 (선택)</label>
      <textarea id="exit-memo" rows={3} value={exitMemo} onChange={(e) => setExitMemo(e.target.value)} />

      {errors.length > 0 && (
        <div className={styles.errorBox}>
          {errors.map((e, i) => <div key={i}>{WARNING_MESSAGES_KR[e] || e}</div>)}
        </div>
      )}

      <div className={styles.actions}>
        <button type="button" onClick={onCancel} disabled={saving}>취소</button>
        <button type="button" className={styles.primaryButton} onClick={handleSave} disabled={saving}>
          청산 기록 저장 (완료로 전환)
        </button>
      </div>
    </div>
  );
}
