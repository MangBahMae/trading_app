import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import RapidDropPanel from "./RapidDropPanel";
import SignalPanel from "./SignalPanel";
import { rapidResponse, rapidSignal } from "../test-fixtures/rapidDrop";
import type { Candle } from "../types";
import type { RapidDropPhase } from "../types/rapidDrop";

const candle: Candle = { date: "2022-01-06", open: 97, high: 99, low: 94, close: 97, volume: 300,
  ema9: null, ema20: null, ema50: null, ema200: null, rsi: null };
const summary = () => screen.getByTestId("rapid-drop-summary");
async function expand() {
  await userEvent.click(screen.getByText("전체 사건·근거·기록 보기"));
  await screen.findByText("시장 판정 상세");
}

describe("급락 대응 실험 패널의 대표 요약과 전체 상세", () => {
  it("기본은 서버 대표 문구·배지·주의 한 줄이며 근거와 ID는 펼치기 전 만들지 않는다", () => {
    render(<RapidDropPanel data={rapidResponse()} loading={false} error={null} />);
    expect(summary()).toHaveTextContent("급락 지속·가속");
    expect(summary()).toHaveTextContent("롱 후보 · 첫 제동");
    expect(summary()).toHaveTextContent("새 발생");
    expect(summary()).toHaveTextContent("급락 경고가 남아 있습니다.");
    expect(screen.getByText("합성 데이터 · 검증용")).toBeVisible();
    expect(document.querySelector("[data-signal-id]")).toBeNull();
    expect(screen.queryByText("최근 평균 대비 거래량 3배")).not.toBeInTheDocument();
    expect(screen.queryByText(/신호 ID/)).not.toBeInTheDocument();
  });

  it("추가 가속이 멈춰도 phase=active이면 급락 지속으로 표시한다", () => {
    const data = rapidResponse();
    render(<RapidDropPanel data={{ ...data, market: { ...data.market, phase: "active", accelerating_now: false,
      accelerating_down: false, observation_window: false } }} loading={false} error={null} />);
    expect(summary()).toHaveTextContent("급락 지속");
    expect(summary()).not.toHaveTextContent("급락 지속·가속");
    expect(summary()).not.toHaveTextContent("급락 구간 아님");
  });

  const phases: Array<[RapidDropPhase, string]> = [
    ["insufficient", "데이터 부족"], ["normal", "급락 구간 아님"], ["eased", "급락 완화"],
  ];
  for (const [phase, title] of phases) {
    it(`서버 ${phase} 상태를 '${title}'로 표시한다`, () => {
      const data = rapidResponse();
      render(<RapidDropPanel data={{ ...data, market: { ...data.market, phase, accelerating_now: false } }} loading={false} error={null} />);
      expect(summary()).toHaveTextContent(title);
    });
  }

  it("같은 날 종료와 새 후보·접촉이 있어도 대표 배지 하나와 모든 상세를 보존한다", async () => {
    const invalid = rapidSignal({ id: "invalid", type: "candidate_invalidated", title: "기존 후보 무효",
      direction: "reference", previous_candidate_ids: ["old-first", "old-retest"] });
    const fresh = rapidSignal({ id: "fresh", title: "새 하단 첫 제동" });
    const contact = rapidSignal({ id: "contact", type: "retest_watch", title: "재시험 접촉 관찰", direction: "reference" });
    const kept = rapidSignal({ id: "kept", title: "별도 기준 유지 후보", occurred_on: "2022-01-05" });
    render(<RapidDropPanel data={rapidResponse({
      summary: { title: "후보 무효 → 롱 후보 · 첫 제동", badge: "new", caution: "서로 다른 기준의 사건입니다." },
      signals: [invalid, fresh, contact], maintained_candidates: [kept],
    })} loading={false} error={null} />);
    expect(summary()).toHaveTextContent("후보 무효 → 롱 후보 · 첫 제동");
    expect(within(summary()).getAllByText("새 발생")).toHaveLength(1);
    expect(document.querySelectorAll("[data-signal-id]")).toHaveLength(0);
    await expand();
    expect(document.querySelectorAll("[data-signal-id]")).toHaveLength(4);
    for (const signal of [invalid, fresh, contact, kept]) {
      expect(document.querySelector(`[data-signal-id="${signal.id}"]`)).toHaveTextContent(signal.title);
    }
    const invalidCard = document.querySelector('[data-signal-id="invalid"]') as HTMLElement;
    expect(invalidCard).toHaveTextContent("연결된 이전 후보 ID: old-first, old-retest");
    expect(invalidCard).toHaveTextContent("확정 2022-01-07T00:00:00+00:00 (UTC)");
    expect(invalidCard).toHaveTextContent("최근 평균 대비 거래량 3배");
    expect(invalidCard).toHaveTextContent("실험 후보이며 주문이 아닙니다.");
    expect(invalidCard).toHaveTextContent("근거 사건 ID synthetic-event");
  });

  it("당일 모든 원시 사건 종류·ID·추가 속성도 상세에 남긴다", async () => {
    render(<RapidDropPanel data={rapidResponse({ raw_events: [
      { id: "raw-first", kind: "first_support_reaction", day: "2022-01-06", custom_note: "전체 속성 유지", reference_price: 97 },
      { id: "raw-loss", kind: "anchor_lost_on_close", day: "2022-01-06", previous_anchor_id: "earlier-anchor" },
    ] })} loading={false} error={null} />);
    expect(document.querySelector("[data-event-id]")).toBeNull();
    await expand();
    expect(document.querySelectorAll("[data-event-id]")).toHaveLength(2);
    const raw = document.querySelector('[data-event-id="raw-first"]') as HTMLElement;
    expect(raw).toHaveTextContent("사건 종류 first_support_reaction");
    expect(raw).toHaveTextContent("사건 ID raw-first");
    await userEvent.click(within(raw).getByText("원시 사건 전체 속성"));
    expect(within(raw).getByText(/"custom_note": "전체 속성 유지"/)).toBeVisible();
    expect(document.querySelector('[data-event-id="raw-loss"]')).toHaveTextContent("earlier-anchor");
  });

  it("전체 history는 상세에서 다시 펼칠 때만 렌더하며 이전 신호를 바꾸지 않는다", async () => {
    const historic = rapidSignal({ id: "historic", occurred_on: "2022-01-01", title: "보존된 이전 발생" });
    render(<RapidDropPanel data={rapidResponse({ history: [historic] })} loading={false} error={null} />);
    expect(document.querySelector('[data-signal-id="historic"]')).toBeNull();
    await expand();
    expect(document.querySelector('[data-signal-id="historic"]')).toBeNull();
    await userEvent.click(screen.getByText("선택일까지의 전체 발생 기록 (1개)"));
    await waitFor(() => expect(document.querySelector('[data-signal-id="historic"]')).not.toBeNull());
    expect(document.querySelector('[data-signal-id="historic"]')).toHaveTextContent("발생 2022-01-01");
  });

  it("선택일이 바뀌어도 유지 배지는 서버 요약을 따르고 같은 후보를 새 발생으로 복제하지 않는다", async () => {
    const old = rapidSignal();
    const { rerender } = render(<RapidDropPanel data={rapidResponse()} loading={false} error={null} />);
    await expand();
    rerender(<RapidDropPanel data={rapidResponse({ date: "2022-01-07", signals: [], maintained_candidates: [old],
      summary: { title: "롱 후보 · 첫 제동", badge: "maintained", caution: null } })} loading={false} error={null} />);
    expect(within(summary()).getByText("유지")).toBeVisible();
    expect(within(summary()).queryByText("새 발생")).not.toBeInTheDocument();
    expect(document.querySelectorAll(`[data-signal-id="${old.id}"]`)).toHaveLength(1);
    expect(document.querySelector(`[data-signal-id="${old.id}"]`)).toHaveTextContent("발생 2022-01-06");
    expect(screen.getByText("당일 새 급락 대응 신호가 없습니다.")).toBeVisible();
  });

  it("실험 후보는 기존 롱·숏 숫자에 합산하지 않는다", () => {
    render(<SignalPanel candle={candle} signals={[{ text: "기존 롱", direction: "long" }]}
      rapidDropEnabled rapidDrop={rapidResponse()} />);
    const label = screen.getAllByText("롱").find((node) => node.tagName !== "BUTTON");
    expect(label?.parentElement).toHaveTextContent("롱1");
    expect(screen.getByTestId("rapid-drop-panel")).toHaveTextContent("별도");
  });

  it("기본 OFF·서버 OFF·오류를 구분하고 disabled의 null 기준값도 허용한다", () => {
    const { rerender } = render(<SignalPanel candle={candle} signals={[]} rapidDrop={rapidResponse()} />);
    expect(screen.queryByTestId("rapid-drop-panel")).not.toBeInTheDocument();
    const disabled = rapidResponse({ enabled: false, signals: [] });
    rerender(<RapidDropPanel data={{ ...disabled, market: { ...disabled.market, stable_bars_required: null,
      strong_speed_threshold: null, ease_speed_threshold: null, acceleration_delta: null } }} loading={false} error={null} />);
    expect(screen.getByText(/서버에서 급락 대응 실험 기능이 꺼져/)).toBeInTheDocument();
    rerender(<RapidDropPanel data={null} loading={false} error="급락 대응 조회 실패: 500" />);
    expect(screen.getByRole("alert")).toHaveTextContent("500");
  });

  it("지지 주의는 서버 한 줄로 표시하고 상세에서 지원 상태·규칙을 확인한다", async () => {
    render(<RapidDropPanel data={rapidResponse({ data_source: "fixed_fixture", summary: {
      title: "새 후보 없음", badge: null, caution: "지지 미확인 · 첫 제동 판단은 보류합니다." },
      support: { status: "unconfirmed", known_versions: 0, recording_started_at: null, unsupported_line_ids: [7], warnings: ["상세 지지 경고"] },
    })} loading={false} error={null} />);
    expect(summary()).toHaveTextContent("지지 미확인 · 첫 제동 판단은 보류합니다.");
    expect(screen.queryByText("상세 지지 경고")).not.toBeInTheDocument();
    expect(screen.getByText("고정 마감 일봉 데이터")).toBeVisible();
    expect(screen.queryByText("합성 데이터 · 검증용")).not.toBeInTheDocument();
    await expand();
    expect(screen.getByText("지지 미확인")).toBeVisible();
    expect(screen.getByText("미지원 도형 ID 7")).toBeVisible();
    expect(screen.getByText("상세 지지 경고")).toBeVisible();
    expect(screen.getByText("급락 대응 v0.3 검증용 초안")).toBeVisible();
  });
});
