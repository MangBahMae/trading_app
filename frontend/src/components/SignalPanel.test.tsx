// 시장 상태(신호 아님) 박스 표시 단위 테스트 - props만으로 렌더하므로 백엔드가 필요 없다.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SignalPanel from "./SignalPanel";
import type { Candle, MarketStateRow, SignalItem } from "../types";

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

describe("SignalPanel near_zone 표시 (캔들 패턴 신호)", () => {
  const sig = (text: string, near_zone: boolean | null | undefined, direction: SignalItem["direction"] = "long"): SignalItem =>
    ({ text, direction, near_zone });

  it("near_zone=true는 '존 근처' 배지, false는 흐리게, null/undefined는 그대로 표시한다", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    render(
      <SignalPanel
        candle={candle}
        signals={[sig("도지 - 롱 후보", true), sig("망치형 - 롱 후보", false), sig("EMA50 지지", null), sig("기타", undefined)]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "롱" }));

    const near = screen.getByText(/도지 - 롱 후보/).closest("li")!;
    expect(near).toHaveAttribute("data-near-zone", "true");
    expect(near).toHaveTextContent("존 근처");

    const alone = screen.getByText(/망치형 - 롱 후보/).closest("li")!;
    expect(alone).toHaveAttribute("data-near-zone", "false");
    expect(alone).not.toHaveTextContent("존 근처");

    for (const t of [/EMA50 지지/, /기타/]) {
      const li = screen.getByText(t).closest("li")!;
      expect(li).not.toHaveAttribute("data-near-zone");
      expect(li).not.toHaveTextContent("존 근처");
    }
  });

  it("참고 지표 목록에도 같은 규칙이 적용되고, 롱/숏 개수는 near_zone과 무관하다", () => {
    render(
      <SignalPanel
        candle={candle}
        signals={[sig("도지 - 참고", true, "reference"), sig("도지 - 참고", false, "reference"),
          sig("도지 - 숏 후보", false, "short"), sig("도지 - 롱 후보", true, "long")]}
      />,
    );
    const items = screen.getAllByText(/도지 - 참고/).map((n) => n.closest("li")!);
    expect(items.map((li) => li.getAttribute("data-near-zone"))).toEqual(["true", "false"]);
    const metrics = (label: string) =>
      screen.getAllByText(label).map((el) => el.parentElement!.textContent);
    expect(metrics("롱")).toContain("롱1");   // 통합 탭의 롱 카운트 (후보 1건)
    expect(metrics("숏")).toContain("숏1");
  });
});
