import { useState } from "react";
import NumberInput from "../NumberInput";
import PriceWeightList from "../PriceWeightList";
import { createTrade, TradeApiError } from "../../api/trades";
import type { Direction, PriceWeightItem, Trade } from "../../types";
import styles from "./TradeForm.module.css";

const WARNING_MESSAGES_KR: Record<string, string> = {
  invalid_direction: "방향이 올바르지 않습니다",
  entry_rationale_required: "진입 근거를 입력해주세요",
  invalidation_note_required: "무효화 지점 서술을 입력해주세요",
  invalidation_price_required: "무효화 지점 가격을 입력해주세요",
  stop_loss_required: "손절가(SL)를 입력해주세요",
  margin_required: "증거금을 입력해주세요",
  leverage_required: "레버리지를 입력해주세요",
  entries_empty: "진입가를 최소 1건 입력해주세요",
  entries_price_invalid: "진입가는 0보다 커야 합니다",
  entries_weight_sum_invalid: "진입가 비중 합이 100%가 아닙니다",
  take_profits_empty: "TP를 최소 1건 입력해주세요",
  take_profits_price_invalid: "TP 가격은 0보다 커야 합니다",
  take_profits_weight_sum_invalid: "TP 비중 합이 100%가 아닙니다",
  invalid_price_order: "가격 순서가 방향과 맞지 않습니다 (롱: SL < 진입가 < TP, 숏: 반대)",
};

interface Props {
  signalTags: string[];
  onSaved: (trade: Trade) => void;
  onCancel: () => void;
  onOpenCalculator: () => void;
}

// 기획서 "1. 진입 전 계획" 폼. 진입가/TP는 각각 최소 1건 필수(PriceWeightList의
// minItems=1) - 기능3 포지션 사이징과 달리 TP도 필수인 점이 다르다.
export default function TradePlanForm({ signalTags, onSaved, onCancel, onOpenCalculator }: Props) {
  const [direction, setDirection] = useState<Direction>("long");
  const [entryRationale, setEntryRationale] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [invalidationNote, setInvalidationNote] = useState("");
  const [invalidationPrice, setInvalidationPrice] = useState(0);
  const [stopLoss, setStopLoss] = useState(0);
  const [entries, setEntries] = useState<PriceWeightItem[]>([{ price: 0, weight: 100 }]);
  const [takeProfits, setTakeProfits] = useState<PriceWeightItem[]>([{ price: 0, weight: 100 }]);
  const [margin, setMargin] = useState(0);
  const [leverage, setLeverage] = useState(1);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]));
  };

  const buildPayload = () => ({
    direction,
    entry_rationale: entryRationale,
    signal_tags: selectedTags,
    invalidation_note: invalidationNote,
    invalidation_price: invalidationPrice,
    stop_loss: stopLoss,
    entries,
    take_profits: takeProfits,
    margin,
    leverage,
  });

  const handleSave = async (draft: boolean) => {
    setSaving(true);
    setErrors([]);
    try {
      const trade = await createTrade(buildPayload(), draft);
      onSaved(trade);
    } catch (err) {
      if (err instanceof TradeApiError) {
        setErrors(err.errors);
      } else {
        setErrors([String(err)]);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.form}>
      <h2>진입 전 계획</h2>

      <label className={styles.fieldLabel}>방향</label>
      <div className={styles.radioGroup}>
        <label><input type="radio" checked={direction === "long"} onChange={() => setDirection("long")} /> 롱</label>
        <label><input type="radio" checked={direction === "short"} onChange={() => setDirection("short")} /> 숏</label>
      </div>

      <label className={styles.fieldLabel} htmlFor="entry-rationale">진입 근거 (필수)</label>
      <textarea
        id="entry-rationale" rows={3} value={entryRationale}
        onChange={(e) => setEntryRationale(e.target.value)}
        placeholder="시그널 기반이든 재량이든 항상 작성"
      />

      <label className={styles.fieldLabel}>기능1 신호 체크 (선택, 다중 선택 가능)</label>
      <div className={styles.tagGrid}>
        {signalTags.map((tag) => (
          <label key={tag} className={styles.checkLabel}>
            <input type="checkbox" checked={selectedTags.includes(tag)} onChange={() => toggleTag(tag)} />
            {tag}
          </label>
        ))}
      </div>

      <label className={styles.fieldLabel} htmlFor="invalidation-note">무효화 지점 서술 (필수)</label>
      <textarea
        id="invalidation-note" rows={2} value={invalidationNote}
        onChange={(e) => setInvalidationNote(e.target.value)}
        placeholder="왜 여기서 진입 근거가 사라지는가"
      />
      <label className={styles.fieldLabel} htmlFor="invalidation-price">무효화 지점 가격 (필수)</label>
      <NumberInput id="invalidation-price" value={invalidationPrice} onChange={setInvalidationPrice} />

      <label className={styles.fieldLabel} htmlFor="stop-loss">SL (필수, 실제 손절 실행가)</label>
      <NumberInput id="stop-loss" value={stopLoss} onChange={setStopLoss} />

      <h3>진입가</h3>
      <PriceWeightList label="진입" minItems={1} exchangeRate={0} onChange={setEntries} />

      <h3>TP</h3>
      <PriceWeightList label="TP" minItems={1} exchangeRate={0} onChange={setTakeProfits} />

      <h3>포지션 사이즈</h3>
      <div className={styles.row2col}>
        <div>
          <label className={styles.fieldLabel} htmlFor="margin">증거금 (필수)</label>
          <NumberInput id="margin" value={margin} onChange={setMargin} />
        </div>
        <div>
          <label className={styles.fieldLabel} htmlFor="leverage">레버리지 (필수)</label>
          <NumberInput id="leverage" value={leverage} onChange={setLeverage} />
        </div>
      </div>
      <button type="button" className={styles.linkButton} onClick={onOpenCalculator}>
        계산기로 채우기 (포지션 사이징 화면 열기)
      </button>

      {errors.length > 0 && (
        <div className={styles.errorBox}>
          {errors.map((e, i) => <div key={i}>{WARNING_MESSAGES_KR[e] || e}</div>)}
        </div>
      )}

      <div className={styles.actions}>
        <button type="button" onClick={onCancel} disabled={saving}>취소</button>
        <button type="button" onClick={() => handleSave(true)} disabled={saving}>임시저장</button>
        <button type="button" className={styles.primaryButton} onClick={() => handleSave(false)} disabled={saving}>
          계획 확정 (진행중으로 전환)
        </button>
      </div>
    </div>
  );
}
