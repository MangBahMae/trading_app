import { useState } from "react";
import type { ComponentProps, ReactNode } from "react";
import type { Candle } from "../types";
import TvChart from "./chart/TvChart";
import ChartLegend, { pickLegendCandle } from "./ChartLegend";
import type { LegendToggle } from "./ChartLegend";
import styles from "./ChartArea.module.css";

type ChartProps = Omit<ComponentProps<typeof TvChart>, "height" | "onCrosshairDate">;

interface Props {
  chartProps: ChartProps;
  candles: Candle[];          // 범례가 값을 찾는 캔들들 (전체)
  selectedDate: string | null;
  toggles: LegendToggle[];
  legendExtra?: ReactNode;
}

// 차트 + 왼쪽 위 오버레이 범례. crosshair 날짜 상태를 여기에 가둬서 마우스를 움직일 때
// 페이지(SignalScanner) 전체가 다시 그려지지 않게 한다.
export default function ChartArea({ chartProps, candles, selectedDate, toggles, legendExtra }: Props) {
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  return (
    <div className={styles.area}>
      <TvChart {...chartProps} onCrosshairDate={setHoverDate} />
      <ChartLegend candle={pickLegendCandle(candles, hoverDate, selectedDate)} toggles={toggles} extra={legendExtra} />
    </div>
  );
}
