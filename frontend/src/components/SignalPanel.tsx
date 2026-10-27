import { useState } from "react";
import type { Candle, MarketStateRow, SignalItem } from "../types";
import styles from "./SignalPanel.module.css";

interface Props {
  candle: Candle | null;
  signals: SignalItem[];
  // 그날의 시장 상태(신호 아님, 차트 음영과 같은 판정). 아직 못 받았으면 null.
  marketState?: MarketStateRow | null;
  marketStateParams?: { n: number; k: number } | null;
}

const fmt1 = (v: number | null) => (v === null ? "-" : v.toLocaleString("en-US", { maximumFractionDigits: 1 }));

// 시장 상태 요약 - 횡보면 어떤 조건(A / B+C) 때문인지, B 간격값과 C 교차 횟수를 같이 보여준다.
function MarketStateBox({ row, params }: { row: MarketStateRow; params: { n: number; k: number } | null }) {
  if (row.state === null) {
    return (
      <div className={styles.marketState} data-testid="market-state-box">
        <div className={styles.marketStateTitle}>시장 상태 <strong>데이터 부족</strong></div>
        <div className={styles.marketStateLine}>EMA50이 아직 계산되지 않은 구간입니다.</div>
      </div>
    );
  }
  const n = params?.n ?? "N";
  const k = params?.k ?? "K";
  return (
    <div className={styles.marketState} data-testid="market-state-box">
      <div className={styles.marketStateTitle}>
        시장 상태 <strong>{row.state}</strong> · 사유 <strong>{row.reason}</strong>
      </div>
      <div className={styles.marketStateLine}>
        A 꼬임: {row.a ? "해당" : "아님"}
      </div>
      <div className={styles.marketStateLine}>
        B 간격 축소: {row.b ? "해당" : "아님"} (|EMA9-EMA50| {fmt1(row.gap_now)} ← {n}봉 전 {fmt1(row.gap_prev)})
      </div>
      <div className={styles.marketStateLine}>
        C 9 교차: {row.c ? "해당" : "아님"} (최근 {n}봉 교차 {row.cross_count === null ? "-" : `${row.cross_count}회`}, 기준 {k}회 이상)
      </div>
    </div>
  );
}

type Tab = "all" | "long" | "short";

// app.py 우측 "신호" 패널(통합/롱/숏 탭 + 참고 지표)을 그대로 재현.
// day_all(그날의 전체 신호)은 이미 백엔드 /api/dashboard 응답의 signals[date]에
// pipeline + 수동 선 + 캔들패턴이 전부 합쳐져서 내려오므로, 여기서는 그걸
// direction별로 나누기만 한다.
export default function SignalPanel({ candle, signals, marketState = null, marketStateParams = null }: Props) {
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

      {marketState && <MarketStateBox row={marketState} params={marketStateParams} />}

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
