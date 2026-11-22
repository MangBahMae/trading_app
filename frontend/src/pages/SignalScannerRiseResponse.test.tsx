import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getDashboard } from "../api/dashboard";
import type { RiseResponse } from "../api/riseResponse";
import type { DashboardResponse } from "../types";
import SignalScanner from "./SignalScanner";

vi.mock("../api/dashboard", () => ({ getDashboard: vi.fn() }));
vi.mock("../components/chart/TvChart", () => ({
  default: ({ onSelectDate }: { onSelectDate: (day: string) => void }) =>
    <button onClick={() => onSelectDate("2022-01-05")}>5일 봉 선택</button>,
}));

const dashboard: DashboardResponse = {
  candles: ["2022-01-05", "2022-01-06"].map((date) => ({
    date, open: 110, high: 112, low: 108, close: 110, volume: 120,
    ema9: null, ema20: null, ema50: null, ema200: null, rsi: null,
  })),
  date_range: { min: "2022-01-05", max: "2022-01-06" },
  signals: { "2022-01-06": [{ text: "추세선 하향 이탈", direction: "short" }] },
  manual_lines: [], divergence_markers: [],
};

function result(date: string, fields: Partial<RiseResponse> = {}): RiseResponse {
  return {
    date, enabled: true, symbol: "BTCUSDT", interval: "1d", data_source: "synthetic_demo",
    market: "상승 추세 유지", long_exit: "기존 롱 종료 검토 · 상승 추세선 이탈", short_signal: "없음",
    events: [{
      id: "trend-3-break-1", date, kind: "trend_break", label: "추세선 이탈",
      evidence: ["당일 선 가격 111, 종가 110"],
    }],
    details: { market: { candle_shape: "도지", surge_sources: [], first_peak: 113 },
      drawings: { trendline_status: "우상향 추세선 확인", support_status: "수동 지지 미확인" } },
    ...fields,
  };
}

const fetchApi = vi.fn<typeof fetch>();
const toggleName = "상승·급등 대응 · 실험";
const dashboardApi = vi.mocked(getDashboard);
const panel = () => screen.getByRole("region", { name: toggleName });

async function load() {
  const user = userEvent.setup();
  render(<SignalScanner nav={null} />);
  await screen.findByRole("checkbox", { name: toggleName });
  return user;
}

describe("선택한 일봉과 상승 대응 실험", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchApi.mockReset());
    dashboardApi.mockReset().mockImplementation(async () => ({ ...dashboard }));
    fetchApi.mockImplementation(async (url) => {
      const day = new URL(String(url), "http://localhost").searchParams.get("date")!;
      return Response.json(result(day));
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("기본 OFF에서 요청을 만들지 않고, 켜면 기존 롱·숏 집계와 독립된 세 판단을 표시한다", async () => {
    const user = await load();
    const toggle = screen.getByRole("checkbox", { name: toggleName });
    expect(toggle).not.toBeChecked();
    expect(fetchApi).not.toHaveBeenCalled();
    await user.click(toggle);
    await screen.findByText("상승 추세 유지");
    expect(fetchApi).toHaveBeenCalledTimes(1);
    expect(fetchApi).toHaveBeenCalledWith(`${import.meta.env.VITE_API_BASE_URL ?? ""}/api/rise-response?date=2022-01-06`,
      { signal: expect.any(AbortSignal) });
    expect([...panel().querySelectorAll("dd")].map((node) => node.textContent))
      .toEqual(["상승 추세 유지", "기존 롱 종료 검토 · 상승 추세선 이탈", "없음"]);
    expect(panel()).toHaveTextContent("합성 데이터 · 검증용");
    expect(screen.getByRole("checkbox", { name: "급락 대응 · 실험" })).not.toBeChecked();
    const count = screen.getAllByText("숏").find((node) => node.tagName !== "BUTTON");
    expect(count?.parentElement).toHaveTextContent("숏1");
    await user.click(within(panel()).getByText("판정 근거와 당일 사건"));
    expect(within(panel()).getByText("캔들 모양 · 도지")).toBeVisible();
    expect(within(panel()).getByText("당일 선 가격 111, 종가 110")).toBeVisible();
    expect(within(panel()).getByText("우상향 추세선 확인 · 수동 지지 미확인")).toBeVisible();
  });

  it("이전 날짜의 늦은 응답을 취소하고 새 날짜의 API 문구를 표시한다", async () => {
    let finish!: (response: Response) => void;
    fetchApi.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await user.click(screen.getByRole("button", { name: "5일 봉 선택" }));
    await screen.findByText("상승 추세 유지");
    expect(panel()).toHaveAttribute("data-date", "2022-01-05");
    expect(fetchApi.mock.calls[0][1]?.signal?.aborted).toBe(true);
    await act(async () => finish(Response.json(result("2022-01-06", { short_signal: "이전 날짜" }))));
    expect(screen.queryByText("이전 날짜")).not.toBeInTheDocument();
  });

  it("주봉 전환 때 결과를 숨기고 추가 요청을 만들지 않는다", async () => {
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await screen.findByText("상승 추세 유지");
    await user.click(screen.getByRole("radio", { name: "1W" }));
    await waitFor(() => expect(screen.getByRole("radio", { name: "1W" })).toBeChecked());
    expect(screen.queryByRole("checkbox", { name: toggleName })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: toggleName })).not.toBeInTheDocument();
    expect(fetchApi).toHaveBeenCalledTimes(1);
  });

  it("서버 OFF와 날짜 불일치를 신호 없음과 구분한다", async () => {
    fetchApi.mockResolvedValueOnce(Response.json(result("2022-01-06", { enabled: false })));
    fetchApi.mockResolvedValueOnce(Response.json(result("2022-01-06")));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await screen.findByText("서버에서 상승 대응 실험 기능이 꺼져 있습니다.");
    expect(panel().querySelector("dl")).toBeNull();
    await user.click(screen.getByRole("button", { name: "5일 봉 선택" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("선택한 BTCUSDT 일봉");
    expect(panel().querySelector("dl")).toBeNull();
  });
});
