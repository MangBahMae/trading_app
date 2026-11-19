// 실제 SignalScanner → API 어댑터 → 기존 SignalPanel의 연결을 합성 응답으로 검사한다.
// 실제 캔버스와 라이브 API 화면 검증은 개발 서버에서 별도로 수행한다.
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SignalScanner from "./SignalScanner";
import { getDashboard } from "../api/dashboard";
import { getRapidDrop } from "../api/rapidDrop";
import { rapidResponse } from "../test-fixtures/rapidDrop";
import type { DashboardResponse } from "../types";
import type { RapidDropResponse } from "../types/rapidDrop";

vi.mock("../api/dashboard", () => ({ getDashboard: vi.fn(), addHorizontalLine: vi.fn(),
  addTrendLine: vi.fn(), addZone: vi.fn(), deleteLine: vi.fn(), updateTrend: vi.fn(), updateZone: vi.fn() }));
vi.mock("../api/rapidDrop", () => ({ getRapidDrop: vi.fn() }));
vi.mock("../components/chart/TvChart", () => ({
  default: ({ onSelectDate }: { onSelectDate?: (date: string) => void }) => (
    <div><button onClick={() => onSelectDate?.("2022-01-05")}>합성 차트 1월 5일 선택</button>
      <button onClick={() => onSelectDate?.("2022-01-06")}>합성 차트 1월 6일 선택</button></div>
  ),
}));

const dashboard: DashboardResponse = {
  candles: ["2022-01-05", "2022-01-06"].map((date) => ({ date, open: 97, high: 99, low: 94, close: 97, volume: 300,
    ema9: null, ema20: null, ema50: null, ema200: null, rsi: null })),
  date_range: { min: "2022-01-05", max: "2022-01-06" },
  signals: { "2022-01-06": [{ text: "기존 독립 롱", direction: "long" }] },
  manual_lines: [], divergence_markers: [],
};
const dashboardMock = vi.mocked(getDashboard);
const rapidMock = vi.mocked(getRapidDrop);

describe("기존 신호 스캐너의 급락 대응 연결", () => {
  beforeEach(() => {
    dashboardMock.mockReset().mockImplementation(async () => ({ ...dashboard }));
    rapidMock.mockReset().mockImplementation(async (date) => rapidResponse({ date }));
  });

  async function loaded() {
    render(<SignalScanner nav={<span>테스트</span>} />);
    await screen.findByText(/데이터 범위:/);
  }

  it("기본 OFF는 요청·실험 패널을 만들지 않고 켜면 선택일의 결과를 연결한다", async () => {
    const user = userEvent.setup();
    await loaded();
    expect(screen.getByRole("checkbox", { name: "급락 대응 · 실험" })).not.toBeChecked();
    expect(rapidMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("rapid-drop-panel")).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "급락 대응 · 실험" }));
    await screen.findByText("롱 후보 · 첫 제동 반응");
    expect(rapidMock).toHaveBeenCalledWith("2022-01-06", expect.any(AbortSignal));
    expect(screen.getByTestId("rapid-drop-panel")).toHaveTextContent("합성 데이터 · 검증용");
    const label = screen.getAllByText("롱").find((node) => node.tagName !== "BUTTON");
    expect(label?.parentElement).toHaveTextContent("롱1");
  });

  it("주봉에서는 토글·실험 결과가 사라지고 급락 API를 부르지 않는다", async () => {
    const user = userEvent.setup();
    await loaded();
    await user.click(screen.getByRole("checkbox", { name: "급락 대응 · 실험" }));
    await screen.findByText("롱 후보 · 첫 제동 반응");
    const before = rapidMock.mock.calls.length;
    await user.click(screen.getByRole("radio", { name: "1W" }));
    await waitFor(() => expect(screen.getByRole("radio", { name: "1W" })).toBeChecked());
    expect(screen.queryByRole("checkbox", { name: "급락 대응 · 실험" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("rapid-drop-panel")).not.toBeInTheDocument();
    expect(rapidMock).toHaveBeenCalledTimes(before);
  });

  it("선택일 변경 후 늦게 온 이전 날짜 응답을 표시하지 않는다", async () => {
    const user = userEvent.setup();
    let resolveOld!: (data: RapidDropResponse) => void;
    rapidMock.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    await loaded();
    await user.click(screen.getByRole("checkbox", { name: "급락 대응 · 실험" }));
    await user.click(screen.getByRole("button", { name: "합성 차트 1월 5일 선택" }));
    await waitFor(() => expect(rapidMock).toHaveBeenCalledTimes(2));
    await screen.findByText("롱 후보 · 첫 제동 반응");
    await act(async () => resolveOld(rapidResponse({ signals: [{ ...rapidResponse().signals[0], title: "오래된 응답" }] })));
    expect(screen.queryByText("오래된 응답")).not.toBeInTheDocument();
  });

  it("데이터 새로고침으로 같은 날짜의 실험 결과도 재조회한다", async () => {
    const user = userEvent.setup();
    await loaded();
    await user.click(screen.getByRole("checkbox", { name: "급락 대응 · 실험" }));
    await screen.findByText("롱 후보 · 첫 제동 반응");
    const before = rapidMock.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "데이터 새로고침" }));
    await waitFor(() => expect(rapidMock).toHaveBeenCalledTimes(before + 1));
    expect(dashboardMock).toHaveBeenLastCalledWith(true, "1D");
  });
});
