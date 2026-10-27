import type { ReactNode } from "react";
import type { Candle } from "../types";
import styles from "./ChartLegend.module.css";

export interface LegendToggle {
  key: string;
  label: string;       // 접근성 이름이자 화면 글자 (예: "EMA20")
  color: string;
  active: boolean;
  onToggle: () => void;
}

// 범례에 보여줄 캔들: crosshair가 가리키는 캔들 -> 없으면 선택한 캔들 -> 없으면 마지막 캔들.
export function pickLegendCandle(
  candles: Candle[], hoverDate: string | null, selectedDate: string | null,
): Candle | null {
  const byDate = (d: string | null) => (d === null ? undefined : candles.find((c) => c.date === d));
  return byDate(hoverDate) ?? byDate(selectedDate) ?? candles[candles.length - 1] ?? null;
}

const fmt = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 2 });

function Eye({ open }: { open: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 10s3.2-5.5 8-5.5S18 10 18 10s-3.2 5.5-8 5.5S2 10 2 10z" />
      {open ? <circle cx="10" cy="10" r="2.4" /> : <line x1="3.5" y1="16.5" x2="16.5" y2="3.5" />}
    </svg>
  );
}

interface Props {
  candle: Candle | null;
  toggles: LegendToggle[];
  extra?: ReactNode; // 토글 줄 끝에 붙는 추가 컨트롤 (횡보 음영의 N/K 입력칸 등)
}

// 차트 왼쪽 위에 겹쳐 놓는 범례: 1줄 시/고/저/종, 2줄 지표 토글(색 + 눈 아이콘).
// 겹침 영역은 마우스를 통과시키고(차트 조작을 막지 않도록) 토글/입력칸만 클릭을 받는다.
export default function ChartLegend({ candle, toggles, extra }: Props) {
  const up = candle ? candle.close >= candle.open : true;
  return (
    <div className={styles.legend}>
      <div className={styles.ohlc} data-testid="chart-legend-ohlc">
        {candle ? (
          <>
            <span className={styles.date}>{candle.date}</span>
            {([["시", candle.open], ["고", candle.high], ["저", candle.low], ["종", candle.close]] as const).map(
              ([label, value]) => (
                <span key={label} className={styles.field}>
                  <span className={styles.fieldLabel}>{label}</span>
                  <span className={up ? styles.up : styles.down}>{fmt(value)}</span>
                </span>
              ),
            )}
          </>
        ) : (
          <span className={styles.fieldLabel}>-</span>
        )}
      </div>
      <div className={styles.toggles}>
        {toggles.map((t) => (
          <button
            key={t.key}
            type="button"
            role="checkbox"
            aria-checked={t.active}
            aria-label={t.label}
            className={t.active ? styles.toggleOn : styles.toggleOff}
            onClick={t.onToggle}
          >
            <span className={styles.swatch} style={{ background: t.color }} />
            <span className={styles.toggleText}>{t.label}</span>
            <Eye open={t.active} />
          </button>
        ))}
        {extra}
      </div>
    </div>
  );
}
