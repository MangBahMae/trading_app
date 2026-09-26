// components/tv_chart/frontend/index.html(Streamlit 커스텀 컴포넌트)의 순수 로직
// 함수들을 그대로 옮긴 것 - 캔들/거래량 색상, 날짜 포맷, 추세선 보간만 다룬다
// (lightweight-charts 인스턴스를 직접 만지는 부분은 TvChart.tsx에 있음).

export interface Bar {
  time: string; // "YYYY-MM-DD"
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const WEEKDAYS_KR = ["일", "월", "화", "수", "목", "금", "토"];

// 차트 시간축/크로스헤어에 쓰는 날짜 포맷 - "요일 YYYY-MM-DD" (예: "금 2026-03-10").
export function formatDateWithWeekday(time: unknown): string {
  let d: Date;
  if (typeof time === "string") {
    d = new Date(time + "T00:00:00Z");
  } else if (time && typeof time === "object" && "year" in (time as Record<string, unknown>)) {
    const t = time as { year: number; month: number; day: number };
    d = new Date(Date.UTC(t.year, t.month - 1, t.day));
  } else {
    d = new Date((time as number) * 1000);
  }
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${WEEKDAYS_KR[d.getUTCDay()]} ${y}-${m}-${day}`;
}

export const DIM_UP = "#a8ddb8";
export const DIM_DOWN = "#f2b8b6";
export const VIVID_UP = "#26a69a";
export const VIVID_DOWN = "#ef5350";
export const VOL_DIM_UP = "rgba(168, 221, 184, 0.5)";
export const VOL_DIM_DOWN = "rgba(242, 184, 182, 0.5)";
export const VOL_VIVID_UP = "rgba(38, 166, 154, 0.8)";
export const VOL_VIVID_DOWN = "rgba(239, 83, 80, 0.8)";

export function buildCandleData(bars: Bar[], selectedDate: string | null) {
  return bars.map((bar) => {
    const isUp = bar.close >= bar.open;
    const isSelected = selectedDate !== null && bar.time === selectedDate;
    const color = isSelected ? (isUp ? VIVID_UP : VIVID_DOWN) : isUp ? DIM_UP : DIM_DOWN;
    return {
      time: bar.time, open: bar.open, high: bar.high, low: bar.low, close: bar.close,
      color, wickColor: color, borderColor: color,
    };
  });
}

export function buildVolumeData(bars: Bar[], selectedDate: string | null) {
  return bars.map((bar) => {
    const isUp = bar.close >= bar.open;
    const isSelected = selectedDate !== null && bar.time === selectedDate;
    const color = isSelected
      ? isUp ? VOL_VIVID_UP : VOL_VIVID_DOWN
      : isUp ? VOL_DIM_UP : VOL_DIM_DOWN;
    return { time: bar.time, value: bar.volume || 0, color };
  });
}

// 파이썬 manual_lines.py의 _trend_line_price와 동일한 선형 보간/외삽 공식.
export function trendPriceAt(
  time1: string, price1: number, time2: string, price2: number, targetTime: string,
): number {
  const t1 = new Date(time1).getTime();
  const t2 = new Date(time2).getTime();
  const t = new Date(targetTime).getTime();
  if (t2 === t1) return price1;
  const frac = (t - t1) / (t2 - t1);
  return price1 + frac * (price2 - price1);
}
