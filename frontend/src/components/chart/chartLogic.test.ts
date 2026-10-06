import { describe, expect, it } from "vitest";
import {
  cornerPoint, hitTestShapes, hitTestTrendHandle, hitTestZoneHandle, nearestOnSegment, oppositeCorner,
  otherTrendHandle, sameTrend, sameZone, toDateString, trendFromPoints, trendHandlePoints, trendPoint,
  trendSegmentPixels, trendVisibleGeom, zoneColorKind, zoneFromCorners, zoneHorizontalSpan, zoneIsDegenerate,
  zoneRectPixels, type HitCoords, type ShapeLine, type ZoneGeom,
} from "./chartLogic";
import { createTimeAxis, makeBarIndex } from "./timeAxis";

// 테스트용 시간축: 캔들 2026-01-05 ~ 2026-01-25(21개, 인덱스 0..20), 논리 인덱스 k의 x = 50 + 10*k.
// 그래서 1월 날짜는 x = 일(DD) * 10 이고, 마지막 캔들(01-25) 오른쪽 미래 날짜도 같은 식으로 이어진다
// (01-30 -> 300, 02-01 -> 320, 02-03 -> 340). timeToCoordinate였다면 미래는 null이었을 구간이다.
const BAR_DATES = Array.from({ length: 21 }, (_, i) => `2026-01-${String(i + 5).padStart(2, "0")}`);
const axis = createTimeAxis(makeBarIndex(BAR_DATES), {
  logicalToCoordinate: (l) => 50 + 10 * l,
  coordinateToLogical: (x) => (x - 50) / 10,
});
// 가격 -> y: 가격 1당 1px 위로(y = 1000 - price)
const coords: HitCoords = {
  priceToY: (p) => 1000 - p,
  dateToX: axis.dateToX,
  firstTime: axis.firstDate,
};

describe("zoneColorKind (종가 위치 기준 색, 신호 방향과 무관)", () => {
  it("종가가 존 위면 below(초록), 존 아래면 above(빨강), 안이면 inside(노랑)", () => {
    expect(zoneColorKind(100, 90, 120)).toBe("below");
    expect(zoneColorKind(100, 90, 80)).toBe("above");
    expect(zoneColorKind(100, 90, 95)).toBe("inside");
  });
  it("경계 값과 종가 모름은 inside", () => {
    expect(zoneColorKind(100, 90, 100)).toBe("inside");
    expect(zoneColorKind(100, 90, 90)).toBe("inside");
    expect(zoneColorKind(100, 90, null)).toBe("inside");
  });
});

describe("zoneHorizontalSpan (왼쪽만 자르고 미래는 계산한 좌표)", () => {
  const first = axis.firstDate;

  it("범위 안이면 두 날짜의 좌표를 그대로 쓴다", () => {
    expect(zoneHorizontalSpan("2026-01-10", "2026-01-20", first, axis.dateToX)).toEqual([100, 200]);
  });
  it("시작이 첫 캔들보다 앞(데이터 이전)이면 왼쪽 끝(0)에서 자른다", () => {
    expect(zoneHorizontalSpan("2025-12-01", "2026-01-20", first, axis.dateToX)).toEqual([0, 200]);
  });
  it("끝이 마지막 캔들 뒤(미래)여도 오른쪽 끝으로 자르지 않고 계산한 좌표를 쓴다", () => {
    expect(zoneHorizontalSpan("2026-01-10", "2026-02-01", first, axis.dateToX)).toEqual([100, 320]);
    expect(zoneHorizontalSpan("2026-01-10", "2026-03-01", first, axis.dateToX)).toEqual([100, 600]);
  });
  it("존 전체가 미래여도 그려진다", () => {
    expect(zoneHorizontalSpan("2026-01-28", "2026-02-03", first, axis.dateToX)).toEqual([280, 340]);
    expect(zoneHorizontalSpan("2026-01-26", "2026-01-27", first, axis.dateToX)).toEqual([260, 270]); // 마지막 캔들 +1, +2일
  });
  it("시작은 데이터 이전, 끝은 미래면 왼쪽만 자른다", () => {
    expect(zoneHorizontalSpan("2025-12-01", "2026-03-01", first, axis.dateToX)).toEqual([0, 600]);
  });
  it("존 전체가 첫 캔들보다 앞(데이터 이전)이면 그리지 않는다", () => {
    expect(zoneHorizontalSpan("2025-11-01", "2025-12-01", first, axis.dateToX)).toBeNull();
  });
  it("첫 캔들 날짜가 없거나 좌표를 못 구하면 그리지 않는다", () => {
    expect(zoneHorizontalSpan("2026-01-10", "2026-01-20", null, axis.dateToX)).toBeNull();
    expect(zoneHorizontalSpan("2026-01-10", "2026-01-20", first, () => null)).toBeNull();
  });
});

describe("nearestOnSegment", () => {
  it("선분 안의 수선의 발과 거리를 구한다", () => {
    expect(nearestOnSegment(5, 3, 0, 0, 10, 0)).toEqual({ dist: 3, x: 5, y: 0 });
  });
  it("선분 밖은 가장 가까운 끝점으로 계산한다", () => {
    expect(nearestOnSegment(13, 4, 0, 0, 10, 0)).toEqual({ dist: 5, x: 10, y: 0 });
  });
  it("길이 0인 선분도 처리한다", () => {
    expect(nearestOnSegment(3, 4, 0, 0, 0, 0).dist).toBe(5);
  });
});

describe("trendSegmentPixels (두 점 사이 선분만, 연장 없음)", () => {
  const priceToY = (p: number) => 1000 - p;
  // (01-10, 500)=(x100,y500), (01-20, 600)=(x200,y400)
  const spec = { time1: "2026-01-10", price1: 500, time2: "2026-01-20", price2: 600 };

  it("두 점 사이 선분만 돌려준다(왼쪽/오른쪽으로 연장하지 않는다)", () => {
    expect(trendSegmentPixels(spec, axis.dateToX, priceToY)).toEqual({ x1: 100, y1: 500, x2: 200, y2: 400 });
  });
  it("미래 날짜로 끝나는 선분도 계산한 좌표 그대로", () => {
    const future = { time1: "2026-01-10", price1: 500, time2: "2026-02-03", price2: 400 }; // x100 -> x340
    expect(trendSegmentPixels(future, axis.dateToX, priceToY)).toEqual({ x1: 100, y1: 500, x2: 340, y2: 600 });
  });
  it("시간 순서가 뒤바뀐 옛 행도 같은 선분(점 두 개를 그대로 잇는다)", () => {
    const reversed = { time1: "2026-01-20", price1: 600, time2: "2026-01-10", price2: 500 };
    expect(trendSegmentPixels(reversed, axis.dateToX, priceToY)).toEqual({ x1: 200, y1: 400, x2: 100, y2: 500 });
  });
  it("두 점이 같은 날이면 price1 높이의 수평 선분(그 날 캔들 한 칸 폭, 백엔드는 price1 고정)", () => {
    const sameDay = { time1: "2026-01-10", price1: 500, time2: "2026-01-10", price2: 700 };
    // 한 칸 = 10px -> 좌우 5px
    expect(trendSegmentPixels(sameDay, axis.dateToX, priceToY)).toEqual({ x1: 95, y1: 500, x2: 105, y2: 500 });
  });
  it("같은 날 선분은 칸이 아주 좁아도 최소 길이를 유지한다", () => {
    const narrow = createTimeAxis(makeBarIndex(BAR_DATES), {
      logicalToCoordinate: (l) => 50 + 1 * l, coordinateToLogical: (x) => x - 50,   // 한 칸 = 1px
    });
    const sameDay = { time1: "2026-01-10", price1: 500, time2: "2026-01-10", price2: 700 };
    const seg = trendSegmentPixels(sameDay, narrow.dateToX, priceToY)!;
    expect(seg.x2 - seg.x1).toBe(8); // SAME_DAY_MIN_HALF_PX(4) * 2
  });
  it("좌표를 못 구하면 null", () => {
    expect(trendSegmentPixels(spec, () => null, priceToY)).toBeNull();
    expect(trendSegmentPixels(spec, axis.dateToX, () => null)).toBeNull();
  });
});

describe("추세선 끝점 핸들 로직", () => {
  const priceToY = (p: number) => 1000 - p;
  const t = { time1: "2026-01-10", price1: 500, time2: "2026-01-20", price2: 600 }; // 점1 (100,500) 점2 (200,400)

  it("trendHandlePoints - 양 끝점 위치(미래 끝점 포함)", () => {
    expect(trendHandlePoints(t, axis.dateToX, priceToY)).toEqual({ p1: { x: 100, y: 500 }, p2: { x: 200, y: 400 } });
    const future = { ...t, time2: "2026-02-03", price2: 400 };
    expect(trendHandlePoints(future, axis.dateToX, priceToY)!.p2).toEqual({ x: 340, y: 600 });
  });

  it("trendHandlePoints - 같은 날이면 두 핸들이 같은 점(price1 높이)", () => {
    const sameDay = { time1: "2026-01-10", price1: 500, time2: "2026-01-10", price2: 700 };
    expect(trendHandlePoints(sameDay, axis.dateToX, priceToY)).toEqual({ p1: { x: 100, y: 500 }, p2: { x: 100, y: 500 } });
  });

  it("hitTestTrendHandle - 9px 이내의 가까운 끝점, 멀면 null, 선 가운데는 핸들이 아니다", () => {
    const pts = trendHandlePoints(t, axis.dateToX, priceToY)!;
    expect(hitTestTrendHandle({ x: 103, y: 503 }, pts)).toBe("p1");
    expect(hitTestTrendHandle({ x: 198, y: 402 }, pts)).toBe("p2");
    expect(hitTestTrendHandle({ x: 91, y: 500 }, pts)).toBe("p1");     // 9px 경계
    expect(hitTestTrendHandle({ x: 90, y: 500 }, pts)).toBeNull();     // 10px
    expect(hitTestTrendHandle({ x: 150, y: 450 }, pts)).toBeNull();    // 선 한가운데
  });

  it("hitTestTrendHandle - 같은 점이면 1번 점", () => {
    const same = { p1: { x: 100, y: 500 }, p2: { x: 100, y: 500 } };
    expect(hitTestTrendHandle({ x: 101, y: 501 }, same)).toBe("p1");
  });

  it("trendPoint / otherTrendHandle", () => {
    expect(trendPoint(t, "p1")).toEqual({ time: "2026-01-10", price: 500 });
    expect(trendPoint(t, "p2")).toEqual({ time: "2026-01-20", price: 600 });
    expect(otherTrendHandle("p1")).toBe("p2");
    expect(otherTrendHandle("p2")).toBe("p1");
  });

  it("trendFromPoints - 시간순이면 그대로", () => {
    expect(trendFromPoints({ time: "2026-01-10", price: 500 }, { time: "2026-01-20", price: 600 })).toEqual(t);
  });

  it("trendFromPoints - 끝점을 반대편 너머로 끌면 점 순서가 바뀌고 가격도 점과 함께 바뀐다", () => {
    // 2번 점(01-20, 600)을 1번 점(01-10, 500)의 왼쪽(01-05, 450)으로 끌었다
    expect(trendFromPoints({ time: "2026-01-10", price: 500 }, { time: "2026-01-05", price: 450 })).toEqual(
      { time1: "2026-01-05", price1: 450, time2: "2026-01-10", price2: 500 });
    // 1번 점을 2번 점의 오른쪽(미래 02-03, 700)으로 끌었다: first=움직인 점
    expect(trendFromPoints({ time: "2026-02-03", price: 700 }, { time: "2026-01-20", price: 600 })).toEqual(
      { time1: "2026-01-20", price1: 600, time2: "2026-02-03", price2: 700 });
  });

  it("trendFromPoints - 같은 날이면 first가 1번 점으로 남는다(POST가 클릭 순서대로 저장하던 것과 같다)", () => {
    expect(trendFromPoints({ time: "2026-01-10", price: 500 }, { time: "2026-01-10", price: 700 })).toEqual(
      { time1: "2026-01-10", price1: 500, time2: "2026-01-10", price2: 700 });
  });

  it("trendVisibleGeom - 같은 날이면 price2를 price1로 본다(보이지 않는 값이 드래그 때 튀지 않게)", () => {
    const sameDay = { time1: "2026-01-10", price1: 500, time2: "2026-01-10", price2: 700 };
    expect(trendVisibleGeom(sameDay)).toEqual({ ...sameDay, price2: 500 });
    expect(trendVisibleGeom(t)).toBe(t);
  });

  it("sameTrend", () => {
    expect(sameTrend(t, { ...t })).toBe(true);
    expect(sameTrend(t, { ...t, price2: 601 })).toBe(false);
    expect(sameTrend(t, { ...t, time1: "2026-01-11" })).toBe(false);
  });
});

describe("hitTestShapes", () => {
  const hline = (id: number, price: number): ShapeLine =>
    ({ id, line_type: "horizontal", time1: null, price1: price, time2: null, price2: null });
  // 추세선: (01-10,500) -> (01-20,600). 화면 선분: (x100,y500) -> (x200,y400)
  const trend = (id: number): ShapeLine =>
    ({ id, line_type: "trend", time1: "2026-01-10", price1: 500, time2: "2026-01-20", price2: 600 });
  const zone = (id: number, top: number, bottom: number, t1 = "2026-01-10", t2 = "2026-01-20"): ShapeLine =>
    ({ id, line_type: "zone", time1: t1, price1: top, time2: t2, price2: bottom });

  it("수평선은 6px 이내만 잡힌다", () => {
    expect(hitTestShapes([hline(1, 500)], { x: 50, y: 500 + 6 }, coords)?.id).toBe(1);   // y=500 선에서 6px
    expect(hitTestShapes([hline(1, 500)], { x: 50, y: 500 + 7 }, coords)).toBeNull();
  });

  it("수평선 anchor는 클릭 x, 선의 y", () => {
    expect(hitTestShapes([hline(1, 500)], { x: 77, y: 503 }, coords)?.anchor).toEqual({ x: 77, y: 500 });
  });

  it("추세선은 두 점 사이 선분 위를 클릭하면 잡힌다", () => {
    expect(hitTestShapes([trend(2)], { x: 150, y: 450 }, coords)?.id).toBe(2);   // 선분 한가운데
    expect(hitTestShapes([trend(2)], { x: 103, y: 497 }, coords)?.id).toBe(2);   // 1번 점 근처
    expect(hitTestShapes([trend(2)], { x: 198, y: 402 }, coords)?.id).toBe(2);   // 2번 점 근처
  });

  it("선분 밖(두 점 밖의 연장선, 마지막 캔들 오른쪽 빈 공간, 첫 캔들 왼쪽)은 선 위여도 안 잡힌다", () => {
    // 직선 y = 500 - (x - 100)의 연장선 위 점들 - 예전(전체 폭 직선)에는 잡혔지만 이제는 선분 밖
    expect(hitTestShapes([trend(2)], { x: 350, y: 250 }, coords)).toBeNull();    // 2번 점 오른쪽 연장선
    expect(hitTestShapes([trend(2)], { x: 30, y: 570 }, coords)).toBeNull();     // 1번 점 왼쪽 연장선
    expect(hitTestShapes([trend(2)], { x: 230, y: 370 }, coords)).toBeNull();    // 끝점(200,400)에서 ~42px
    // 끝점 바로 바깥 6px 이내는 끝점까지의 거리로 잡힌다(선분 끝 근처)
    expect(hitTestShapes([trend(2)], { x: 204, y: 396 }, coords)?.id).toBe(2);
  });

  it("미래(마지막 캔들 오른쪽 빈 공간)로 이어진 추세선 선분은 그 위를 클릭하면 잡힌다", () => {
    // (01-10,500) -> (02-03,400): x100~340. 중간 x=220에서 y = 500 + (220-100)*(100/240) = 550
    const future: ShapeLine = { id: 8, line_type: "trend", time1: "2026-01-10", price1: 500, time2: "2026-02-03", price2: 400 };
    expect(hitTestShapes([future], { x: 220, y: 550 }, coords)?.id).toBe(8);
    expect(hitTestShapes([future], { x: 335, y: 600 - 3 }, coords)?.id).toBe(8); // 미래 쪽 끝점 근처
    expect(hitTestShapes([future], { x: 360, y: 610 }, coords)).toBeNull();      // 끝점 오른쪽(연장선)
  });

  it("추세선에서 6px 넘게 떨어지면 안 잡힌다", () => {
    expect(hitTestShapes([trend(2)], { x: 150, y: 450 + 20 }, coords)).toBeNull();
  });

  it("추세선 anchor는 클릭에서 가장 가까운 선분 위의 점", () => {
    const anchor = hitTestShapes([trend(2)], { x: 150, y: 453 }, coords)!.anchor;
    expect(Math.abs(anchor.y - (500 - (anchor.x - 100)))).toBeLessThan(1e-9);   // 선분(직선) 위
    expect(anchor.x).toBeGreaterThanOrEqual(100);
    expect(anchor.x).toBeLessThanOrEqual(200);
  });

  it("두 점이 같은 날인 추세선은 그 날의 짧은 수평 선분처럼 잡힌다", () => {
    const flat: ShapeLine = { id: 5, line_type: "trend", time1: "2026-01-10", price1: 500, time2: "2026-01-10", price2: 700 };
    expect(hitTestShapes([flat], { x: 100, y: 503 }, coords)?.id).toBe(5);       // 그 날(x=100), price1 높이
    expect(hitTestShapes([flat], { x: 100, y: 520 }, coords)).toBeNull();
    expect(hitTestShapes([flat], { x: 300, y: 503 }, coords)).toBeNull();        // 다른 날 - 더는 전체 폭 수평선이 아니다
  });

  it("존은 직사각형 안쪽을 클릭하면 잡히고 밖은 안 잡힌다", () => {
    // 존: x 100~200, y 1000-600=400 ~ 1000-500=500
    expect(hitTestShapes([zone(3, 600, 500)], { x: 150, y: 450 }, coords)?.id).toBe(3);
    expect(hitTestShapes([zone(3, 600, 500)], { x: 150, y: 520 }, coords)).toBeNull();
    expect(hitTestShapes([zone(3, 600, 500)], { x: 90, y: 450 }, coords)).toBeNull();
  });

  it("미래(마지막 캔들 오른쪽)에 있는 존도 안쪽을 클릭하면 잡힌다", () => {
    const future = zone(6, 600, 500, "2026-01-28", "2026-02-03"); // x 280~340 (마지막 캔들 x=250 오른쪽)
    expect(hitTestShapes([future], { x: 300, y: 450 }, coords)?.id).toBe(6);
    expect(hitTestShapes([future], { x: 270, y: 450 }, coords)).toBeNull();
    expect(hitTestShapes([future], { x: 345, y: 450 }, coords)).toBeNull();
  });

  it("데이터 이전으로 잘린 존은 보이는 부분(왼쪽 끝부터)이 잡힌다", () => {
    const wide = zone(3, 600, 500, "2025-12-01", "2026-03-01"); // 0 ~ 600
    expect(hitTestShapes([wide], { x: 5, y: 450 }, coords)?.id).toBe(3);
    expect(hitTestShapes([wide], { x: 395, y: 450 }, coords)?.id).toBe(3);
  });

  it("겹치면 클릭에 가장 가까운 하나만 고른다(선이 존보다 우선)", () => {
    // 존 y 400~500, 수평선(가격 550) y=450
    const shapes = [zone(3, 600, 500), hline(1, 550)];
    expect(hitTestShapes(shapes, { x: 150, y: 452 }, coords)?.id).toBe(1);   // 선이 2px 거리
    expect(hitTestShapes(shapes, { x: 150, y: 480 }, coords)?.id).toBe(3);   // 선과 멀면 존
  });

  it("두 수평선이 겹치면 더 가까운 선", () => {
    // y=500(가격 500)과 y=496(가격 504), 클릭 y=497 -> 두 번째가 1px, 첫째는 3px
    expect(hitTestShapes([hline(1, 500), hline(2, 504)], { x: 10, y: 497 }, coords)?.id).toBe(2);
    expect(hitTestShapes([hline(1, 500), hline(2, 504)], { x: 10, y: 502 }, coords)?.id).toBe(1);
  });

  it("존끼리 겹치면 더 작은 존", () => {
    const shapes = [zone(3, 700, 400), zone(4, 600, 500, "2026-01-12", "2026-01-18")];
    expect(hitTestShapes(shapes, { x: 150, y: 450 }, coords)?.id).toBe(4);
  });

  it("아무것도 없으면 null", () => {
    expect(hitTestShapes([], { x: 1, y: 1 }, coords)).toBeNull();
    expect(hitTestShapes([hline(1, 500)], { x: 1, y: 1 }, coords)).toBeNull();
  });
});

describe("존 꼭지점 드래그 로직", () => {
  const z: ZoneGeom = { time1: "2026-01-10", time2: "2026-01-20", price1: 600, price2: 500 };
  // 화면: x 100~200, y 400~500

  it("zoneRectPixels - 보이는 존의 사각형과 왼쪽 잘림 여부", () => {
    expect(zoneRectPixels(z, coords)).toEqual({
      x1: 100, x2: 200, yTop: 400, yBottom: 500, leftClipped: false,
    });
    // 시작이 데이터 이전 -> 왼쪽만 잘리고, 끝(미래)은 계산한 좌표
    expect(zoneRectPixels({ ...z, time1: "2025-12-01", time2: "2026-03-01" }, coords)).toEqual({
      x1: 0, x2: 600, yTop: 400, yBottom: 500, leftClipped: true,
    });
    expect(zoneRectPixels({ ...z, time1: "2025-11-01", time2: "2025-12-01" }, coords)).toBeNull(); // 데이터 이전
  });

  it("zoneRectPixels - 미래에 있는 존", () => {
    expect(zoneRectPixels({ ...z, time1: "2026-01-28", time2: "2026-02-03" }, coords)).toEqual({
      x1: 280, x2: 340, yTop: 400, yBottom: 500, leftClipped: false,
    });
  });

  it("hitTestZoneHandle - 네 꼭지점을 각각 잡는다", () => {
    const rect = zoneRectPixels(z, coords)!;
    expect(hitTestZoneHandle({ x: 102, y: 403 }, rect)).toBe("tl");
    expect(hitTestZoneHandle({ x: 198, y: 402 }, rect)).toBe("tr");
    expect(hitTestZoneHandle({ x: 101, y: 497 }, rect)).toBe("bl");
    expect(hitTestZoneHandle({ x: 205, y: 505 }, rect)).toBe("br");
  });

  it("hitTestZoneHandle - 멀면 null이고, 존 한가운데나 변 위는 꼭지점이 아니다", () => {
    const rect = zoneRectPixels(z, coords)!;
    expect(hitTestZoneHandle({ x: 150, y: 450 }, rect)).toBeNull();
    expect(hitTestZoneHandle({ x: 150, y: 400 }, rect)).toBeNull();
    expect(hitTestZoneHandle({ x: 100 - 10, y: 400 }, rect)).toBeNull();   // 9px 초과
    expect(hitTestZoneHandle({ x: 100 - 9, y: 400 }, rect)).toBe("tl");    // 경계(9px)
  });

  it("hitTestZoneHandle - 왼쪽이 데이터 이전으로 잘리면 왼쪽 꼭지점은 잡히지 않고 오른쪽은 잡힌다", () => {
    const rect = zoneRectPixels({ ...z, time1: "2025-12-01" }, coords)!; // 왼쪽이 잘림
    expect(hitTestZoneHandle({ x: 0, y: 400 }, rect)).toBeNull();
    expect(hitTestZoneHandle({ x: 200, y: 400 }, rect)).toBe("tr");
  });

  it("hitTestZoneHandle - 미래에 있는 존의 오른쪽 꼭지점도 잡힌다(더 이상 잘려서 숨겨지지 않는다)", () => {
    const rect = zoneRectPixels({ ...z, time1: "2026-01-28", time2: "2026-02-03" }, coords)!; // x 280~340
    expect(hitTestZoneHandle({ x: 338, y: 402 }, rect)).toBe("tr");
    expect(hitTestZoneHandle({ x: 342, y: 498 }, rect)).toBe("br");
    expect(hitTestZoneHandle({ x: 282, y: 402 }, rect)).toBe("tl");
  });

  it("hitTestZoneHandle - 작은 존에서 두 꼭지점이 다 보이면 더 가까운 쪽", () => {
    const rect = { x1: 100, x2: 106, yTop: 400, yBottom: 500, leftClipped: false };
    expect(hitTestZoneHandle({ x: 101, y: 400 }, rect)).toBe("tl");
    expect(hitTestZoneHandle({ x: 105, y: 400 }, rect)).toBe("tr");
  });

  it("cornerPoint / oppositeCorner", () => {
    expect(cornerPoint(z, "tl")).toEqual({ time: "2026-01-10", price: 600 });
    expect(cornerPoint(z, "tr")).toEqual({ time: "2026-01-20", price: 600 });
    expect(cornerPoint(z, "bl")).toEqual({ time: "2026-01-10", price: 500 });
    expect(cornerPoint(z, "br")).toEqual({ time: "2026-01-20", price: 500 });
    expect(oppositeCorner("tl")).toBe("br");
    expect(oppositeCorner("tr")).toBe("bl");
    expect(oppositeCorner("bl")).toBe("tr");
    expect(oppositeCorner("br")).toBe("tl");
  });

  it("zoneFromCorners - 정상 방향과 반대편을 넘어간 경우 모두 정규화", () => {
    const fixed = cornerPoint(z, "bl");   // 왼쪽 아래 고정, 오른쪽 위(tr)를 움직임
    expect(zoneFromCorners(fixed, { time: "2026-01-25", price: 700 })).toEqual(
      { time1: "2026-01-10", time2: "2026-01-25", price1: 700, price2: 500 });
    // 고정점 왼쪽/아래로 넘어감 -> 시작<끝, 상단>하단 유지
    expect(zoneFromCorners(fixed, { time: "2026-01-06", price: 450 })).toEqual(
      { time1: "2026-01-06", time2: "2026-01-10", price1: 500, price2: 450 });
  });

  it("zoneFromCorners - 미래 날짜로 끌어도 정규화된다(오른쪽 꼭지점을 빈 공간으로 / 미래에서 과거로)", () => {
    const fixed = cornerPoint(z, "bl");
    expect(zoneFromCorners(fixed, { time: "2026-02-03", price: 650 })).toEqual(
      { time1: "2026-01-10", time2: "2026-02-03", price1: 650, price2: 500 });
    const futureFixed = { time: "2026-02-03", price: 500 };
    expect(zoneFromCorners(futureFixed, { time: "2026-01-28", price: 600 })).toEqual(
      { time1: "2026-01-28", time2: "2026-02-03", price1: 600, price2: 500 });
  });

  it("zoneIsDegenerate / sameZone", () => {
    expect(zoneIsDegenerate(z)).toBe(false);
    expect(zoneIsDegenerate({ ...z, time2: z.time1 })).toBe(true);
    expect(zoneIsDegenerate({ ...z, price2: z.price1 })).toBe(true);
    expect(sameZone(z, { ...z })).toBe(true);
    expect(sameZone(z, { ...z, price2: 501 })).toBe(false);
  });

  it("toDateString - 문자열/BusinessDay/타임스탬프/알 수 없는 값", () => {
    expect(toDateString("2026-01-10")).toBe("2026-01-10");
    expect(toDateString({ year: 2026, month: 1, day: 5 })).toBe("2026-01-05");
    expect(toDateString(Date.UTC(2026, 0, 10) / 1000)).toBe("2026-01-10");
    expect(toDateString(null)).toBeNull();
    expect(toDateString(undefined)).toBeNull();
  });
});
