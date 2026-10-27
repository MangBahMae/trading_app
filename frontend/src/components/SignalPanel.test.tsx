// 시장 상태(신호 아님) 박스 표시 단위 테스트 - props만으로 렌더하므로 백엔드가 필요 없다.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SignalPanel from "./SignalPanel";
import type { Candle, MarketStateRow } from "../types";

const candle: Candle = {
  date: "2026-03-10", open: 100, high: 110, low: 90, close: 105, volume: 1,
  ema9: null, ema20: null, ema50: null, ema200: null, rsi: null,
};

const row = (patch: Partial<MarketStateRow>): MarketStateRow => ({
  date: "2026-03-10", state: "횡보", reason: "BC", a: false, b: true, c: true,
  gap_now: 12.34, gap_prev: 18.1, cross_count: 5, ...patch,
});

describe("SignalPanel 시장 상태 박스", () => {
  it("횡보(BC)면 상태, 사유, B 간격값, C 교차 횟수와 기준을 보여준다", () => {
    render(<SignalPanel candle={candle} signals={[]} marketState={row({})} marketStateParams={{ n: 10, k: 4 }} />);
    const box = screen.getByTestId("market-state-box");
    expect(box).toHaveTextContent("시장 상태 횡보 · 사유 BC");
    expect(box).toHaveTextContent("A 꼬임: 아님");
    expect(box).toHaveTextContent("B 간격 축소: 해당 (|EMA9-EMA50| 12.3 ← 10봉 전 18.1)");
    expect(box).toHaveTextContent("C 9 교차: 해당 (최근 10봉 교차 5회, 기준 4회 이상)");
  });

  it("횡보 사유 A면 A만 해당으로 표시된다", () => {
    render(
      <SignalPanel
        candle={candle} signals={[]} marketStateParams={{ n: 10, k: 4 }}
        marketState={row({ reason: "A", a: true, b: false, c: false, gap_prev: null, cross_count: 1 })}
      />,
    );
    const box = screen.getByTestId("market-state-box");
    expect(box).toHaveTextContent("사유 A");
    expect(box).toHaveTextContent("A 꼬임: 해당");
    expect(box).toHaveTextContent("B 간격 축소: 아님");
    expect(box).toHaveTextContent("10봉 전 -");
  });

  it("상승/하락이면 사유는 '없음'", () => {
    render(
      <SignalPanel
        candle={candle} signals={[]} marketStateParams={{ n: 10, k: 4 }}
        marketState={row({ state: "상승", reason: "없음", b: false, c: false })}
      />,
    );
    expect(screen.getByTestId("market-state-box")).toHaveTextContent("시장 상태 상승 · 사유 없음");
  });

  it("EMA50이 없는 앞 구간은 '데이터 부족'", () => {
    render(
      <SignalPanel
        candle={candle} signals={[]}
        marketState={row({ state: null, reason: null, a: false, b: false, c: false, gap_now: null, gap_prev: null, cross_count: null })}
      />,
    );
    expect(screen.getByTestId("market-state-box")).toHaveTextContent("데이터 부족");
  });

  it("시장 상태를 아직 못 받았으면 박스를 그리지 않는다", () => {
    render(<SignalPanel candle={candle} signals={[]} />);
    expect(screen.queryByTestId("market-state-box")).not.toBeInTheDocument();
  });
});
