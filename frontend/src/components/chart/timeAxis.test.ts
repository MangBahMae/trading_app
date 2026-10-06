import { describe, expect, it } from "vitest";
import {
  addDays, createTimeAxis, dateToDayNumber, dateToLogical, dayNumberToDate, logicalToDate, makeBarIndex,
  type TimeScaleLike,
} from "./timeAxis";

// 캔들: 2025-12-29 ~ 2026-01-02 (5개, 연말/연초를 걸침). 인덱스 0..4, 마지막 = 2026-01-02
const DATES = ["2025-12-29", "2025-12-30", "2025-12-31", "2026-01-01", "2026-01-02"];
const index = makeBarIndex(DATES);
const LAST = DATES.length - 1;

describe("날짜 계산 (UTC 달력)", () => {
  it("dateToDayNumber / dayNumberToDate 왕복", () => {
    for (const d of ["1970-01-01", "2024-02-29", "2025-12-31", "2026-10-05"]) {
      expect(dayNumberToDate(dateToDayNumber(d)!)).toBe(d);
    }
    expect(dateToDayNumber("1970-01-02")).toBe(1);
  });

  it("형식이 틀리거나 없는 날짜는 null", () => {
    for (const bad of ["", "2026/01/01", "20260101", "2026-1-1", "2026-02-30", "2026-13-01", "2025-02-29", "abc"]) {
      expect(dateToDayNumber(bad)).toBeNull();
    }
  });

  it("월말을 넘긴다", () => {
    expect(addDays("2026-01-31", 1)).toBe("2026-02-01");
    expect(addDays("2026-04-30", 1)).toBe("2026-05-01");
    expect(addDays("2026-02-28", 1)).toBe("2026-03-01");   // 평년 2월
  });

  it("연말을 넘긴다", () => {
    expect(addDays("2025-12-31", 1)).toBe("2026-01-01");
    expect(addDays("2025-12-31", 366)).toBe("2027-01-01");
    expect(addDays("2025-12-30", 3)).toBe("2026-01-02");
  });

  it("윤일(2월 29일)을 넘긴다", () => {
    expect(addDays("2024-02-28", 1)).toBe("2024-02-29");
    expect(addDays("2024-02-28", 2)).toBe("2024-03-01");
    expect(addDays("2024-02-29", 365)).toBe("2025-02-28");
  });

  it("음수 일수와 잘못된 날짜", () => {
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(addDays("nope", 1)).toBeNull();
  });
});

describe("logicalToDate (화면 -> 날짜)", () => {
  it("캔들 구간은 그 캔들의 날짜를 그대로 쓴다", () => {
    DATES.forEach((d, k) => expect(logicalToDate(index, k)).toBe(d));
  });

  it("마지막 캔들 = 마지막 날짜, 마지막+1 = 하루 뒤", () => {
    expect(logicalToDate(index, LAST)).toBe("2026-01-02");
    expect(logicalToDate(index, LAST + 1)).toBe("2026-01-03");
    expect(logicalToDate(index, LAST + 30)).toBe("2026-02-01");
  });

  it("미래가 월말/연말을 넘어가도 달력대로", () => {
    const yearEnd = makeBarIndex(["2025-12-30", "2025-12-31"]);
    expect(logicalToDate(yearEnd, 2)).toBe("2026-01-01");
    const monthEnd = makeBarIndex(["2026-01-30", "2026-01-31"]);
    expect(logicalToDate(monthEnd, 2)).toBe("2026-02-01");
    const leap = makeBarIndex(["2024-02-27", "2024-02-28"]);
    expect(logicalToDate(leap, 2)).toBe("2024-02-29");   // 윤일
    expect(logicalToDate(leap, 3)).toBe("2024-03-01");   // 윤일 다음 날은 3월 1일
  });

  it("첫 캔들 이전(k<0)은 null", () => {
    expect(logicalToDate(index, -1)).toBeNull();
    expect(logicalToDate(index, -5)).toBeNull();
    expect(logicalToDate(index, -0.6)).toBeNull(); // 반올림하면 -1
  });

  it("반올림: 칸의 절반 미만은 그 칸, 절반 이상은 다음 칸", () => {
    expect(logicalToDate(index, 2.49)).toBe("2025-12-31");
    expect(logicalToDate(index, 2.5)).toBe("2026-01-01");
    expect(logicalToDate(index, 1.51)).toBe("2025-12-31");
    expect(logicalToDate(index, LAST + 0.49)).toBe("2026-01-02");
    expect(logicalToDate(index, LAST + 0.5)).toBe("2026-01-03");
    expect(logicalToDate(index, LAST + 2.4)).toBe("2026-01-04");
    expect(logicalToDate(index, -0.4)).toBe("2025-12-29");  // 첫 캔들로 반올림(-0)
  });

  it("캔들이 없거나 NaN/Infinity면 null", () => {
    expect(logicalToDate(makeBarIndex([]), 0)).toBeNull();
    expect(logicalToDate(index, NaN)).toBeNull();
    expect(logicalToDate(index, Infinity)).toBeNull();
  });
});

describe("dateToLogical (날짜 -> 화면)", () => {
  it("캔들 날짜는 그 캔들의 인덱스", () => {
    DATES.forEach((d, k) => expect(dateToLogical(index, d)).toBe(k));
  });

  it("마지막 캔들 이후는 마지막 인덱스 + 일수", () => {
    expect(dateToLogical(index, "2026-01-02")).toBe(LAST);
    expect(dateToLogical(index, "2026-01-03")).toBe(LAST + 1);
    expect(dateToLogical(index, "2026-02-01")).toBe(LAST + 30);
    expect(dateToLogical(index, "2027-01-02")).toBe(LAST + 365);
  });

  it("첫 캔들 이전은 음수", () => {
    expect(dateToLogical(index, "2025-12-28")).toBe(-1);
    expect(dateToLogical(index, "2025-12-19")).toBe(-10);
  });

  it("캔들 사이에 빠진 날은 앞뒤 캔들 사이를 일수로 보간한다", () => {
    const gappy = makeBarIndex(["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]);
    expect(dateToLogical(gappy, "2026-01-03")).toBeCloseTo(1 + 1 / 3, 10);
    expect(dateToLogical(gappy, "2026-01-04")).toBeCloseTo(1 + 2 / 3, 10);
    expect(dateToLogical(gappy, "2026-01-05")).toBe(2);
  });

  it("캔들이 없거나 날짜 형식이 틀리면 null", () => {
    expect(dateToLogical(makeBarIndex([]), "2026-01-01")).toBeNull();
    expect(dateToLogical(index, "2026/01/01")).toBeNull();
    expect(dateToLogical(index, "")).toBeNull();
  });

  it("logicalToDate와 왕복 일치(첫 캔들 ~ 미래 400일)", () => {
    for (let k = 0; k <= LAST + 400; k++) {
      const date = logicalToDate(index, k)!;
      expect(dateToLogical(index, date)).toBe(k);
    }
  });
});

describe("createTimeAxis (x 좌표 연결)", () => {
  // 가짜 시간축: 논리 인덱스 k의 중심이 x = 100 + 10*k
  const scale: TimeScaleLike = {
    logicalToCoordinate: (l) => 100 + 10 * l,
    coordinateToLogical: (x) => (x - 100) / 10,
  };
  const axis = createTimeAxis(index, scale);

  it("첫/마지막 날짜", () => {
    expect(axis.firstDate).toBe("2025-12-29");
    expect(axis.lastDate).toBe("2026-01-02");
    expect(createTimeAxis(makeBarIndex([]), scale).firstDate).toBeNull();
  });

  it("dateToX: 캔들, 마지막+1일, 미래, 첫 캔들 이전", () => {
    expect(axis.dateToX("2025-12-29")).toBe(100);
    expect(axis.dateToX("2026-01-02")).toBe(140);
    expect(axis.dateToX("2026-01-03")).toBe(150);   // timeToCoordinate가 null을 주는 미래도 좌표가 나온다
    expect(axis.dateToX("2026-02-01")).toBe(440);
    expect(axis.dateToX("2025-12-28")).toBe(90);
    expect(axis.dateToX("garbage")).toBeNull();
  });

  it("xToDate: 봉 중심, 반올림 경계, 미래, 데이터 이전", () => {
    expect(axis.xToDate(140)).toBe("2026-01-02");
    expect(axis.xToDate(144)).toBe("2026-01-02");  // 0.4칸
    expect(axis.xToDate(146)).toBe("2026-01-03");  // 0.6칸 -> 다음 칸
    expect(axis.xToDate(150)).toBe("2026-01-03");
    expect(axis.xToDate(440)).toBe("2026-02-01");
    expect(axis.xToDate(95)).toBe("2025-12-29");   // -0.5칸 -> 첫 캔들(-0)
    expect(axis.xToDate(85)).toBeNull();           // -1.5칸 -> 데이터 이전
  });

  it("scale이 null을 주면(차트에 데이터가 없을 때) null", () => {
    const empty = createTimeAxis(index, { logicalToCoordinate: () => null, coordinateToLogical: () => null });
    expect(empty.dateToX("2026-01-01")).toBeNull();
    expect(empty.xToDate(100)).toBeNull();
  });
});
