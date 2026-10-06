import { addDays } from "./timeAxis";

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

// --- 존(가격 구간 직사각형) - 색/좌표 결정 순수 로직 (캔버스 없이 테스트 가능) ---

export type ZoneColorKind = "below" | "above" | "inside";

// 마지막 종가 기준 색 구분 - 보기용이고 신호 방향과 무관하다.
//   종가가 존 위(존이 종가보다 완전히 아래) -> "below"  (초록)
//   종가가 존 아래(존이 종가보다 완전히 위) -> "above"  (빨강)
//   종가가 존 안(경계 포함)이거나 종가를 모를 때 -> "inside" (노랑/중립)
export function zoneColorKind(top: number, bottom: number, lastClose: number | null): ZoneColorKind {
  if (lastClose === null) return "inside";
  if (lastClose > top) return "below";
  if (lastClose < bottom) return "above";
  return "inside";
}

export const ZONE_COLORS: Record<ZoneColorKind, { fill: string; border: string }> = {
  below: { fill: "rgba(38, 166, 154, 0.18)", border: "rgba(38, 166, 154, 0.85)" },
  above: { fill: "rgba(239, 83, 80, 0.18)", border: "rgba(239, 83, 80, 0.85)" },
  inside: { fill: "rgba(245, 190, 40, 0.22)", border: "rgba(214, 158, 0, 0.9)" },
};

// 존의 가로 범위(x1~x2, 화면 좌표)를 구한다. dateToX는 timeAxis의 날짜 -> x 변환이라 마지막 캔들
// 오른쪽(미래) 날짜도 정확한 좌표가 나온다.
//   시작이 표시 중인 첫 캔들보다 앞(데이터 이전) -> 왼쪽 끝(0)에서 자른다
//   끝/시작이 미래 -> 계산한 좌표를 그대로 쓴다(오른쪽 끝으로 자르지 않는다)
//   존 전체가 첫 캔들보다 앞(데이터 이전)이면 그리지 않는다(null)
export function zoneHorizontalSpan(
  time1: string, time2: string, firstTime: string | null, dateToX: (date: string) => number | null,
): [number, number] | null {
  if (firstTime === null) return null;
  if (time2 < firstTime) return null;

  const x1 = time1 < firstTime ? 0 : dateToX(time1);
  const x2 = dateToX(time2);
  if (x1 === null || x2 === null) return null;
  return [Math.min(x1, x2), Math.max(x1, x2)];
}

// --- 그려진 도형 클릭 판정 (lightweight-charts에는 선 클릭 이벤트가 없어서 직접 계산) ---

export const HIT_TOLERANCE_PX = 6;

export interface ShapeLine {
  id: number;
  line_type: "horizontal" | "trend" | "zone";
  time1: string | null;
  price1: number;
  time2: string | null;
  price2: number | null;
}

export interface HitCoords {
  priceToY: (price: number) => number | null;
  dateToX: (date: string) => number | null;  // timeAxis 기반 - 미래 날짜도 좌표가 나온다
  firstTime: string | null;                  // 표시 중인 첫 캔들 날짜(데이터 이전 처리용)
}

export interface ShapeHit {
  id: number;
  anchor: { x: number; y: number }; // 삭제 툴바를 띄울 기준점(클릭 근처)
}

// 점 (px,py)에서 선분 (x1,y1)-(x2,y2)까지의 최단 거리와 그 선분 위 가장 가까운 점.
export function nearestOnSegment(
  px: number, py: number, x1: number, y1: number, x2: number, y2: number,
): { dist: number; x: number; y: number } {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  const x = x1 + t * dx;
  const y = y1 + t * dy;
  return { dist: Math.hypot(px - x, py - y), x, y };
}

// 추세선이 화면에 그려지는 모양: 두 점 사이 선분만(양쪽 연장 없음). 백엔드 신호도 같은 구간
// (time1 <= 날짜 <= time2)만 평가한다. 두 점이 같은 날이면 백엔드(_trend_line_price가 price1 고정)와
// 같이 price1 높이의 수평 선분으로 그린다 - 길이는 그 날 캔들 한 칸 폭(최소 SAME_DAY_MIN_HALF_PX*2)이다.
export interface TrendSpec {
  time1: string;
  price1: number;
  time2: string;
  price2: number;
}

export type TrendHandle = "p1" | "p2"; // 1번 점 / 2번 점(끝점 핸들)

export const SAME_DAY_MIN_HALF_PX = 4;

export function trendSegmentPixels(
  t: TrendSpec, dateToX: (date: string) => number | null, priceToY: (price: number) => number | null,
): { x1: number; y1: number; x2: number; y2: number } | null {
  const xa = dateToX(t.time1);
  const ya = priceToY(t.price1);
  if (xa === null || ya === null) return null;
  if (t.time1 === t.time2) {
    const next = addDays(t.time1, 1);
    const xn = next === null ? null : dateToX(next);
    const half = Math.max(xn === null ? 0 : Math.abs(xn - xa) / 2, SAME_DAY_MIN_HALF_PX);
    return { x1: xa - half, y1: ya, x2: xa + half, y2: ya };
  }
  const xb = dateToX(t.time2);
  const yb = priceToY(t.price2);
  if (xb === null || yb === null) return null;
  return { x1: xa, y1: ya, x2: xb, y2: yb };
}

// 같은 날 추세선은 화면에서 price1 높이의 수평 선분이므로, 편집 대상 모양도 price2 = price1로 본다
// (보이지 않는 price2가 드래그 때 갑자기 튀어나오지 않게).
export function trendVisibleGeom(t: TrendSpec): TrendSpec {
  return t.time1 === t.time2 ? { ...t, price2: t.price1 } : t;
}

// 끝점 핸들 위치. 같은 날이면 두 핸들이 같은 점(그 날, price1 높이)이다.
export function trendHandlePoints(
  t: TrendSpec, dateToX: (date: string) => number | null, priceToY: (price: number) => number | null,
): { p1: { x: number; y: number }; p2: { x: number; y: number } } | null {
  const xa = dateToX(t.time1);
  const ya = priceToY(t.price1);
  if (xa === null || ya === null) return null;
  if (t.time1 === t.time2) return { p1: { x: xa, y: ya }, p2: { x: xa, y: ya } };
  const xb = dateToX(t.time2);
  const yb = priceToY(t.price2);
  if (xb === null || yb === null) return null;
  return { p1: { x: xa, y: ya }, p2: { x: xb, y: yb } };
}

// 클릭 지점에서 tolerance 안에 있는 가장 가까운 끝점(같은 거리면 1번 점).
export function hitTestTrendHandle(
  p: { x: number; y: number },
  pts: { p1: { x: number; y: number }; p2: { x: number; y: number } },
  tolerance = HANDLE_HIT_PX,
): TrendHandle | null {
  const d1 = Math.hypot(p.x - pts.p1.x, p.y - pts.p1.y);
  const d2 = Math.hypot(p.x - pts.p2.x, p.y - pts.p2.y);
  if (d1 > tolerance && d2 > tolerance) return null;
  return d1 <= d2 ? "p1" : "p2";
}

export function trendPoint(t: TrendSpec, handle: TrendHandle): { time: string; price: number } {
  return handle === "p1" ? { time: t.time1, price: t.price1 } : { time: t.time2, price: t.price2 };
}

export function otherTrendHandle(handle: TrendHandle): TrendHandle {
  return handle === "p1" ? "p2" : "p1";
}

// 두 점을 time1 <= time2 순서로 정규화한다(저장/전송 전). 순서가 뒤바뀌면 가격도 점과 함께 바뀐다.
// 같은 날이면 first가 1번 점으로 남는다(POST가 클릭 순서대로 저장하던 것과 같다).
export function trendFromPoints(
  first: { time: string; price: number }, second: { time: string; price: number },
): TrendSpec {
  return first.time <= second.time
    ? { time1: first.time, price1: first.price, time2: second.time, price2: second.price }
    : { time1: second.time, price1: second.price, time2: first.time, price2: first.price };
}

export function sameTrend(a: TrendSpec, b: TrendSpec): boolean {
  return a.time1 === b.time1 && a.price1 === b.price1 && a.time2 === b.time2 && a.price2 === b.price2;
}

// 클릭 지점에서 가장 가까운 도형 하나를 고른다(없으면 null).
//   수평선: 클릭 y와 선 y의 거리 <= tolerance
//   추세선: 화면에 실제로 그려진 선분(두 점 사이)과의 거리 <= tolerance - 선분 밖(연장선)은 제외
//   존: 클릭이 직사각형 안. 선(수평선/추세선)이 tolerance 안에 있으면 선이 우선하고,
//       존끼리 겹치면 더 작은 존이 우선한다.
export function hitTestShapes(
  lines: ShapeLine[], click: { x: number; y: number }, c: HitCoords, tolerance = HIT_TOLERANCE_PX,
): ShapeHit | null {
  let bestScore = Infinity;
  let best: ShapeHit | null = null;

  for (const line of lines) {
    let score: number | null = null;
    let anchor = { x: click.x, y: click.y };

    if (line.line_type === "horizontal") {
      const y = c.priceToY(line.price1);
      if (y === null) continue;
      const d = Math.abs(click.y - y);
      if (d <= tolerance) { score = d; anchor = { x: click.x, y }; }
    } else if (line.line_type === "trend") {
      if (!line.time1 || !line.time2 || line.price2 === null) continue;
      const seg = trendSegmentPixels(
        { time1: line.time1, price1: line.price1, time2: line.time2, price2: line.price2 },
        c.dateToX, c.priceToY,
      );
      if (!seg) continue;
      const near = nearestOnSegment(click.x, click.y, seg.x1, seg.y1, seg.x2, seg.y2);
      if (near.dist <= tolerance) { score = near.dist; anchor = { x: near.x, y: near.y }; }
    } else {
      if (!line.time1 || !line.time2 || line.price2 === null) continue;
      const span = zoneHorizontalSpan(line.time1, line.time2, c.firstTime, c.dateToX);
      const yTop = c.priceToY(line.price1);
      const yBottom = c.priceToY(line.price2);
      if (!span || yTop === null || yBottom === null) continue;
      const [x1, x2] = span;
      const top = Math.min(yTop, yBottom);
      const bottom = Math.max(yTop, yBottom);
      if (click.x >= x1 && click.x <= x2 && click.y >= top && click.y <= bottom) {
        score = tolerance + 0.5 + (x2 - x1) * (bottom - top) * 1e-9;
        anchor = { x: click.x, y: top };
      }
    }

    if (score !== null && score < bestScore) {
      bestScore = score;
      best = { id: line.id, anchor };
    }
  }
  return best;
}

// --- 존 꼭지점 핸들 드래그 ---

// 존 모양: time1<time2(시작/끝), price1>price2(상단/하단) - 서버에 저장되는 정규화된 형태.
export interface ZoneGeom {
  time1: string;
  time2: string;
  price1: number;
  price2: number;
}

// tl=(시작,상단) tr=(끝,상단) bl=(시작,하단) br=(끝,하단)
export type ZoneCorner = "tl" | "tr" | "bl" | "br";

export const HANDLE_HIT_PX = 9;
export const ZONE_DRAG_MIN_PX = 3; // 이 이하로 움직인 건 클릭이지 수정이 아니다

export const CORNER_CURSOR: Record<ZoneCorner, string> = {
  tl: "nwse-resize", br: "nwse-resize", tr: "nesw-resize", bl: "nesw-resize",
};

export interface ZoneRectPx {
  x1: number;
  x2: number;
  yTop: number;
  yBottom: number;
  leftClipped: boolean;   // 시작이 표시 중인 첫 캔들보다 앞(데이터 이전)이라 왼쪽 끝에서 잘림(왼쪽 핸들 없음)
}

// 존의 화면 좌표 사각형. 표시 범위 밖이거나 좌표를 못 구하면 null.
export function zoneRectPixels(z: ZoneGeom, c: HitCoords): ZoneRectPx | null {
  const span = zoneHorizontalSpan(z.time1, z.time2, c.firstTime, c.dateToX);
  const y1 = c.priceToY(z.price1);
  const y2 = c.priceToY(z.price2);
  if (!span || y1 === null || y2 === null) return null;
  return {
    x1: span[0], x2: span[1], yTop: Math.min(y1, y2), yBottom: Math.max(y1, y2),
    leftClipped: c.firstTime !== null && z.time1 < c.firstTime,
  };
}

// 클릭 지점에서 tolerance 안에 있는 가장 가까운 꼭지점. 왼쪽이 데이터 이전으로 잘려서 안 보이는
// 쪽 꼭지점만 제외한다(미래 쪽 꼭지점은 계산한 좌표에 그대로 있다).
export function hitTestZoneHandle(
  p: { x: number; y: number }, rect: ZoneRectPx, tolerance = HANDLE_HIT_PX,
): ZoneCorner | null {
  const corners: { corner: ZoneCorner; x: number; y: number; hidden: boolean }[] = [
    { corner: "tl", x: rect.x1, y: rect.yTop, hidden: rect.leftClipped },
    { corner: "tr", x: rect.x2, y: rect.yTop, hidden: false },
    { corner: "bl", x: rect.x1, y: rect.yBottom, hidden: rect.leftClipped },
    { corner: "br", x: rect.x2, y: rect.yBottom, hidden: false },
  ];
  let best: ZoneCorner | null = null;
  let bestDist = Infinity;
  for (const c of corners) {
    if (c.hidden) continue;
    const d = Math.hypot(p.x - c.x, p.y - c.y);
    if (d <= tolerance && d < bestDist) {
      bestDist = d;
      best = c.corner;
    }
  }
  return best;
}

export function cornerPoint(z: ZoneGeom, corner: ZoneCorner): { time: string; price: number } {
  return {
    time: corner === "tl" || corner === "bl" ? z.time1 : z.time2,
    price: corner === "tl" || corner === "tr" ? z.price1 : z.price2,
  };
}

export function oppositeCorner(corner: ZoneCorner): ZoneCorner {
  return ({ tl: "br", br: "tl", tr: "bl", bl: "tr" } as const)[corner];
}

// 고정 꼭지점과 움직이는 꼭지점으로 존을 만든다. 반대편을 넘어가도 되도록 항상
// 시작<끝, 상단>하단으로 정규화한다(YYYY-MM-DD 문자열은 사전순 = 시간순).
export function zoneFromCorners(
  a: { time: string; price: number }, b: { time: string; price: number },
): ZoneGeom {
  return {
    time1: a.time <= b.time ? a.time : b.time,
    time2: a.time <= b.time ? b.time : a.time,
    price1: Math.max(a.price, b.price),
    price2: Math.min(a.price, b.price),
  };
}

export function zoneIsDegenerate(z: ZoneGeom): boolean {
  return z.time1 === z.time2 || z.price1 === z.price2;
}

export function sameZone(a: ZoneGeom, b: ZoneGeom): boolean {
  return a.time1 === b.time1 && a.time2 === b.time2 && a.price1 === b.price1 && a.price2 === b.price2;
}

// lightweight-charts가 돌려주는 Time(문자열 / {year,month,day} / 초 단위 타임스탬프)을
// "YYYY-MM-DD"로. 못 읽으면 null.
export function toDateString(t: unknown): string | null {
  if (typeof t === "string") return t;
  if (typeof t === "number") return new Date(t * 1000).toISOString().slice(0, 10);
  if (t && typeof t === "object" && "year" in t && "month" in t && "day" in t) {
    const { year, month, day } = t as { year: number; month: number; day: number };
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }
  return null;
}
