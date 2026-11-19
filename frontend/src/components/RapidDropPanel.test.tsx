import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import RapidDropPanel from "./RapidDropPanel";
import SignalPanel from "./SignalPanel";
import { rapidResponse, rapidSignal } from "../test-fixtures/rapidDrop";
import type { Candle } from "../types";

const candle: Candle = { date: "2022-01-06", open: 97, high: 99, low: 94, close: 97, volume: 300,
  ema9: null, ema20: null, ema50: null, ema200: null, rsi: null };

describe("급락 대응 실험 패널", () => {
  it("합성 배지·현재 가속·관찰 구간과 새 후보를 함께 표시한다", async () => {
    render(<RapidDropPanel data={rapidResponse()} loading={false} error={null} />);
    const panel = screen.getByTestId("rapid-drop-panel");
    expect(panel).toHaveTextContent("합성 데이터 · 검증용");
    expect(panel).toHaveTextContent("현재 하락 가속");
    expect(panel).toHaveTextContent("최근 급락 이후 관찰 구간");
    expect(panel).toHaveTextContent("롱 후보 · 첫 제동 반응");
    expect(panel).toHaveTextContent("새 발생");
    expect(panel).toHaveTextContent("지지 반응 봉 종가 · 자동 기준");
    await userEvent.click(screen.getByText("근거·주의사항·참조 보기"));
    expect(panel).toHaveTextContent("확정 2022-01-07T00:00:00+00:00 (UTC)");
    expect(panel).toHaveTextContent("최근 평균 대비 거래량 3배");
    expect(panel).toHaveTextContent("실험 후보이며 주문이 아닙니다.");
  });

  it("유지 후보와 무효 사건을 별도로 표시하고 이전 후보 연결을 보존한다", async () => {
    const old = rapidSignal({ id: "earlier", occurred_on: "2022-01-05" });
    const invalid = rapidSignal({ id: "invalid", type: "candidate_invalidated", title: "기존 롱 후보 무효",
      direction: "reference", previous_candidate_ids: [old.id] });
    render(<RapidDropPanel data={rapidResponse({ signals: [invalid], maintained_candidates: [old] })} loading={false} error={null} />);
    expect(screen.getByText("기존 롱 후보 무효")).toBeInTheDocument();
    expect(screen.getByText("유지")).toBeInTheDocument();
    const invalidCard = document.querySelector('[data-signal-id="invalid"]') as HTMLElement;
    await userEvent.click(within(invalidCard).getByText("근거·주의사항·참조 보기"));
    expect(invalidCard).toHaveTextContent("연결된 이전 후보 ID: earlier");
  });

  it("실험 후보는 기존 롱·숏 숫자에 합산하지 않는다", () => {
    render(<SignalPanel candle={candle} signals={[{ text: "기존 롱", direction: "long" }]}
      rapidDropEnabled rapidDrop={rapidResponse()} />);
    const label = screen.getAllByText("롱").find((node) => node.tagName !== "BUTTON");
    expect(label?.parentElement).toHaveTextContent("롱1");
    expect(screen.getByTestId("rapid-drop-panel")).toHaveTextContent("별도");
  });

  it("기본 OFF에서는 실험 섹션이 없고 서버 OFF·미확인·오류를 구분한다", () => {
    const { rerender } = render(<SignalPanel candle={candle} signals={[]} rapidDrop={rapidResponse()} />);
    expect(screen.queryByTestId("rapid-drop-panel")).not.toBeInTheDocument();
    rerender(<RapidDropPanel data={rapidResponse({ enabled: false, signals: [] })} loading={false} error={null} />);
    expect(screen.getByText(/서버에서 급락 대응 실험 기능이 꺼져/)).toBeInTheDocument();
    rerender(<RapidDropPanel data={rapidResponse({ support: { status: "unconfirmed", known_versions: 0,
      recording_started_at: null, unsupported_line_ids: [], warnings: [] } })} loading={false} error={null} />);
    expect(screen.getByText("지지 미확인")).toBeInTheDocument();
    rerender(<RapidDropPanel data={null} loading={false} error="급락 대응 조회 실패: 500" />);
    expect(screen.getByRole("alert")).toHaveTextContent("500");
  });

  it("고정 일봉 안내와 규칙 출처를 표시한다", async () => {
    render(<RapidDropPanel data={rapidResponse({ data_source: "fixed_fixture" })} loading={false} error={null} />);
    expect(screen.getByText("고정 마감 일봉 데이터")).toBeInTheDocument();
    expect(screen.queryByText("합성 데이터 · 검증용")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("적용 규칙 출처"));
    expect(screen.getByText("급락 대응 v0.3 검증용 초안")).toBeInTheDocument();
  });
});
