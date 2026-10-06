// 날짜(YYYY-MM-DD, UTC) <-> lightweight-charts 논리 인덱스 <-> 화면 x 좌표 변환 - 한 곳에 모아서
// 그리기 클릭, 미리보기, 존/추세선 렌더링, 핸들 드래그, 도형 선택(히트 테스트)이 전부 같이 쓴다.
//
// lightweight-charts의 시간축은 "캔들 개수" 단위(논리 인덱스)다. 캔들이 있는 구간은 그 캔들의
// 날짜를 그대로 쓰고, 마지막 캔들 오른쪽(미래)은 "한 칸 = 하루"로 보고 마지막 캔들 날짜에 일 단위로
// 더한다. 일봉이라는 가정에 기대는 부분은 미래 구간뿐이다(캔들 구간은 날짜 조회라 빠진 날이 있어도
// 맞다). timeToCoordinate는 미래 날짜에 null을 주므로 logicalToCoordinate로 계산한다.

const DAY_MS = 86_400_000;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

// "YYYY-MM-DD" -> 1970-01-01부터의 일수(UTC). 형식이 틀리거나 없는 날짜(2026-02-30 등)면 null.
export function dateToDayNumber(date: string): number | null {
  const m = DATE_RE.exec(date);
  if (!m) return null;
  const ms = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const back = new Date(ms);
  if (
    back.getUTCFullYear() !== Number(m[1]) || back.getUTCMonth() !== Number(m[2]) - 1 ||
    back.getUTCDate() !== Number(m[3])
  ) {
    return null;
  }
  return Math.round(ms / DAY_MS);
}

export function dayNumberToDate(dayNumber: number): string {
  return new Date(dayNumber * DAY_MS).toISOString().slice(0, 10);
}

// 날짜에 일 단위로 더한다(월말/연말/윤일 넘김은 UTC 달력대로).
export function addDays(date: string, days: number): string | null {
  const n = dateToDayNumber(date);
  return n === null ? null : dayNumberToDate(n + days);
}

// 표시 중인 캔들 날짜(오름차순)와 일수 배열.
export interface BarIndex {
  dates: string[];
  dayNumbers: number[];
}

export function makeBarIndex(dates: string[]): BarIndex {
  return { dates, dayNumbers: dates.map((d) => dateToDayNumber(d) ?? NaN) };
}

// 날짜 -> 논리 인덱스.
//   캔들 날짜: 그 캔들의 인덱스
//   마지막 캔들 이후(미래): 마지막 인덱스 + 일수
//   첫 캔들 이전: 0에서 일수만큼 뺀 음수 (예: 첫 캔들 하루 전 = -1)
//   캔들 사이에 빠진 날: 앞뒤 캔들 사이를 일수로 보간한 소수 인덱스
// 캔들이 없거나 날짜 형식이 틀리면 null.
export function dateToLogical(index: BarIndex, date: string): number | null {
  const n = index.dates.length;
  const d = dateToDayNumber(date);
  if (n === 0 || d === null) return null;

  const { dayNumbers } = index;
  const last = n - 1;
  if (d >= dayNumbers[last]) return last + (d - dayNumbers[last]);
  if (d <= dayNumbers[0]) return d - dayNumbers[0]; // 첫 캔들이면 0(-0이 아니라), 그 이전이면 음수

  // dayNumbers[lo] <= d < dayNumbers[hi] 인 lo를 이분 탐색
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (dayNumbers[mid] <= d) lo = mid;
    else hi = mid;
  }
  if (dayNumbers[lo] === d) return lo;
  return lo + (d - dayNumbers[lo]) / (dayNumbers[lo + 1] - dayNumbers[lo]);
}

// 논리 인덱스 -> 날짜. 가장 가까운 칸(반올림)으로 정한다.
//   캔들 구간: 그 캔들의 날짜 / 마지막 이후: 마지막 캔들 날짜 + 일수 / 첫 캔들 이전(k<0): null
export function logicalToDate(index: BarIndex, logical: number): string | null {
  const n = index.dates.length;
  if (n === 0 || !Number.isFinite(logical)) return null;
  const k = Math.round(logical);
  if (k < 0) return null;
  const last = n - 1;
  if (k <= last) return index.dates[k];
  return addDays(index.dates[last], k - last);
}

// 차트 timeScale에서 쓰는 두 함수만 뽑은 인터페이스(테스트에서 가짜로 바꿔 끼우기 위함).
export interface TimeScaleLike {
  logicalToCoordinate: (logical: number) => number | null;
  coordinateToLogical: (x: number) => number | null;
}

export interface TimeAxis {
  firstDate: string | null;  // 표시 중인 첫/마지막 캔들 날짜
  lastDate: string | null;
  dateToX: (date: string) => number | null;
  xToDate: (x: number) => string | null;
}

export function createTimeAxis(index: BarIndex, scale: TimeScaleLike): TimeAxis {
  const n = index.dates.length;
  return {
    firstDate: n > 0 ? index.dates[0] : null,
    lastDate: n > 0 ? index.dates[n - 1] : null,
    dateToX: (date) => {
      const logical = dateToLogical(index, date);
      return logical === null ? null : scale.logicalToCoordinate(logical);
    },
    xToDate: (x) => {
      const logical = scale.coordinateToLogical(x);
      return logical === null ? null : logicalToDate(index, logical);
    },
  };
}
