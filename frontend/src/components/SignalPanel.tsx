import { useState } from "react";
import type { Candle, SignalItem } from "../types";
import styles from "./SignalPanel.module.css";

interface Props {
  candle: Candle | null;
  signals: SignalItem[];
}

type Tab = "all" | "long" | "short";

// app.py 우측 "신호" 패널(통합/롱/숏 탭 + 참고 지표)을 그대로 재현.
// day_all(그날의 전체 신호)은 이미 백엔드 /api/dashboard 응답의 signals[date]에
// pipeline + 수동 선 + 캔들패턴이 전부 합쳐져서 내려오므로, 여기서는 그걸
// direction별로 나누기만 한다.
export default function SignalPanel({ candle, signals }: Props) {
  const [tab, setTab] = useState<Tab>("all");

  if (!candle) {
    return (
      <div className={styles.panel}>
        <h2>신호</h2>
        <p className={styles.empty}>{"왼쪽 차트에서 캔들을 클릭하면\n그 날짜의 신호가 여기 표시됩니다."}</p>
      </div>
    );
  }

  const longSignals = signals.filter((s) => s.direction === "long").map((s) => s.text);
  const shortSignals = signals.filter((s) => s.direction === "short").map((s) => s.text);
  const referenceTexts = signals.filter((s) => s.direction === "reference").map((s) => s.text);

  return (
    <div className={styles.panel}>
      <h2>신호</h2>
      <div><strong>{candle.date}</strong></div>
      <div className={styles.ohlc}>
        시가 {candle.open.toLocaleString("en-US")} · 고가 {candle.high.toLocaleString("en-US")} ·
        {" "}저가 {candle.low.toLocaleString("en-US")} · 종가 {candle.close.toLocaleString("en-US")}
      </div>
      <hr className={styles.divider} />

      <div className={styles.tabs}>
        <button
          type="button"
          className={tab === "all" ? styles.tabButtonActive : styles.tabButton}
          onClick={() => setTab("all")}
        >
          통합
        </button>
        <button
          type="button"
          className={tab === "long" ? styles.tabButtonActive : styles.tabButton}
          onClick={() => setTab("long")}
        >
          롱
        </button>
        <button
          type="button"
          className={tab === "short" ? styles.tabButtonActive : styles.tabButton}
          onClick={() => setTab("short")}
        >
          숏
        </button>
      </div>

      {tab === "all" && (
        <div className={styles.metrics}>
          <div className={styles.metric}>
            <div className={styles.metricLabel}>롱</div>
            <div className={styles.metricValue}>{longSignals.length}</div>
          </div>
          <div className={styles.metric}>
            <div className={styles.metricLabel}>숏</div>
            <div className={styles.metricValue}>{shortSignals.length}</div>
          </div>
        </div>
      )}

      {tab === "long" && (
        longSignals.length > 0 ? (
          <ul className={styles.signalList}>
            {longSignals.map((s, i) => <li key={i}>- {s}</li>)}
          </ul>
        ) : (
          <p className={styles.empty}>이 날짜에 롱 신호가 없습니다.</p>
        )
      )}

      {tab === "short" && (
        shortSignals.length > 0 ? (
          <ul className={styles.signalList}>
            {shortSignals.map((s, i) => <li key={i}>- {s}</li>)}
          </ul>
        ) : (
          <p className={styles.empty}>이 날짜에 숏 신호가 없습니다.</p>
        )
      )}

      {referenceTexts.length > 0 && (
        <div className={styles.referenceSection}>
          <hr className={styles.divider} />
          <div className={styles.referenceLabel}>참고 지표 (카운트 제외)</div>
          <ul className={styles.signalList}>
            {referenceTexts.map((s, i) => <li key={i}>- {s}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
