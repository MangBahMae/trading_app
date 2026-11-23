import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getDashboard } from "../api/dashboard";
import { breakoutTitle, type BreakoutEvent, type BreakoutResponse } from "../api/breakoutRetest";
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

  it.each([
    { context: "신규 신호 없음", exit: "해당 없음", short: "해당 없음", caution: true },
    { context: "도형 조회 실패", exit: "해당 없음", short: "해당 없음", caution: false, warnings: ["도형 이력 확인 실패"] },
    { context: "롱 종료 검토", exit: "기존 롱 종료 검토 · 상승 추세선 이탈", short: "해당 없음", caution: false },
    { context: "숏 후보 발행", exit: "해당 없음", short: "숏 후보 · 지지 재시험 실패", caution: false },
  ])("같은 상승 추세에서 $context 여부에 따라 숏 진입 주의를 구분한다", async ({ exit, short, caution, warnings }) => {
    const market = "롱 우세 · 정배열 유지";
    fetchApi.mockResolvedValueOnce(Response.json(result("2022-01-06", {
      market, long_exit: exit, short_signal: short, events: [],
      details: { warnings, market: { ema_regime: "bullish", price_direction: "up", price_phase: "상승 추세 유지" } },
    })));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await within(panel()).findByText(market);
    const label = within(panel()).queryByText("숏 진입 주의");
    if (caution) expect(label).toBeVisible();
    else expect(label).not.toBeInTheDocument();
    if (exit !== "해당 없음") expect(within(panel()).getByText(exit)).toBeVisible();
    if (short !== "해당 없음") expect(within(panel()).getByText(short)).toBeVisible();
  });

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

  it("서버가 확정한 구조의 두 날짜와 관찰·후보의 상태, 출처, 기간을 상세에 구분한다", async () => {
    const date = "2022-01-06";
    fetchApi.mockResolvedValueOnce(Response.json(result(date, {
      market: "역배열 속 반등", short_signal: "숏 관찰 · EMA50 거부",
      details: {
        market: {
          ema_regime: "bearish", ema50: 112.5, price_direction: "up",
          swing_highs: [{ date: "2022-01-03", confirmed_on: "2022-01-04", price: 112 }],
          active_watches: [{ id: "watch-2", date: "2022-01-02", watch_breakout: 113.12 }],
        },
        drawings: { levels: [{ kind: "resistance", version: "EMA50", source: "EMA50",
          price: 113, current_price: 112.5, state: "종가 거부 확인", touch_date: "2022-01-05" }] },
        lifecycle: [
          { id: "watch-1", label: "EMA50 거부", source: "EMA50", status: "new", started_on: date, age_days: 1 },
          { id: "watch-2", label: "고점 재시도 실패", source: "고점 재시도", status: "maintained",
            started_on: "2022-01-02", age_days: 5 },
          { id: "watch-3", label: "수동선 거부", source: "수동 저항", status: "released",
            started_on: "2022-01-01", ended_on: date, age_days: 6 },
          { id: "short-4", label: "지지 재시험 실패", source: "수동 지지", status: "invalidated",
            started_on: "2022-01-04", ended_on: date, age_days: 3 },
        ],
      },
    })));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await screen.findByText("역배열 속 반등");
    await user.click(within(panel()).getByText("판정 근거와 당일 사건"));
    for (const text of ["EMA9·20·50 역배열", "가격 구조 · 고점·저점 상승", "EMA50 112.5",
      "고점 112 · 발생 2022-01-03 → 확인 2022-01-04", "고점 재시도 · 시작 2022-01-02 · 5일",
      "접촉 당시 EMA50 113", "당일 EMA50 112.5", "해제 기준 · 종가 113.12 초과",
      "수동 지지 · 시작 2022-01-04 · 종료 2022-01-06 · 3일"]) {
      expect(within(panel()).getByText(text)).toBeVisible();
    }
    const outcomes = panel().querySelector("dl")!;
    for (const badge of ["신규", "유지", "해제", "무효"]) {
      expect(within(outcomes).getByText(badge)).toBeVisible();
      expect(within(within(panel()).getByRole("list")).getByText(badge)).toBeVisible();
    }
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

function breakoutEvent(date: string, fields: Partial<BreakoutEvent> = {}): BreakoutEvent {
  return {
    id: "try-1-long", type: "long_candidate", label: "롱 후보 · 돌파 가격 지지 확인", origin: "breakout_retest",
    status: "new", drawing_id: "지지선 1", version_id: "첫 버전", drawing_kind: "trend",
    attempt_id: "try-1", breakout_date: "2022-01-03", retest_date: date, confirmed_date: date,
    bottom: 100, top: 100, close: 101, candle_shape: "도지", volume: 123, linked_ids: ["try-1-break"],
    evidence: [], steps: [
      { id: "try-1-break", type: "breakout_up", label: "상향 돌파", date: "2022-01-03", bottom: 102, top: 102, close: 103 },
      { id: "try-1-long", type: "long_candidate", label: "지지 확인", date, bottom: 100, top: 100, close: 101 },
    ], ...fields,
  };
}

function breakoutResult(date: string, fields: Partial<BreakoutResponse> = {}): BreakoutResponse {
  return {
    date, enabled: true, symbol: "BTCUSDT", interval: "1d", market_label: "롱 우세 · 정배열 유지",
    market_context: null, data_source: "synthetic_demo", history_status: "recorded",
    remaining_long_exits: [], warnings: [], events: [], active: [], ...fields,
  };
}

describe("일봉 돌파·재시험 실험", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchApi.mockReset());
    dashboardApi.mockReset().mockImplementation(async () => ({ ...dashboard }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("일봉 토글로만 요청하고 선택일 신규·유지와 각 날짜의 추세선 가격을 구분한다", async () => {
    fetchApi.mockImplementation(async (url) => {
      const day = new URL(String(url), "http://localhost").searchParams.get("date")!;
      const event = breakoutEvent("2022-01-05");
      return Response.json(breakoutResult(day, day === "2022-01-05"
        ? { events: [event], active: [event] } : { active: [{ ...event, status: "maintained" }] }));
    });
    const user = await load();
    const toggle = screen.getByRole("checkbox", { name: breakoutTitle });
    expect(toggle).not.toBeChecked();
    expect(fetchApi).not.toHaveBeenCalled();
    await user.click(toggle);
    const b = within(screen.getByRole("region", { name: breakoutTitle }));
    await b.findByText("유지");
    await user.click(screen.getByRole("button", { name: "5일 봉 선택" }));
    await b.findByText("신규");
    expect(b.getByRole("list", { name: "선택일 돌파·재시험" }).children).toHaveLength(1);
    await user.click(b.getByText("도형·가격과 사건 순서"));
    expect(b.getByText("선 가격 102")).toBeVisible();
    expect(b.getByText("선 가격 100")).toBeVisible();
    expect(b.getByText("합성 데이터 · 검증용")).toBeVisible();
    await user.click(screen.getByRole("radio", { name: "1W" }));
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: breakoutTitle })).toBeNull());
    expect(fetchApi).toHaveBeenCalledTimes(2);
  });

  it("공유 사건 ID가 같을 때 신규 숏은 한 곳에서만 강조하고 별개 숏 관찰은 보존한다", async () => {
    const day = "2022-01-06";
    const label = "숏 후보 · 지지 재시험 실패";
    const event = breakoutEvent(day, { id: "legacy-short", type: "short_candidate", label, origin: "rise_response" });
    const watch = "숏 관찰 · 고점 재시도 실패";
    fetchApi.mockImplementation(async (url) => Response.json(String(url).includes("/breakout-retest")
      ? breakoutResult(day, { events: [event] })
      : result(day, { long_exit: "해당 없음", short_signal: label + " / " + watch,
          details: { lifecycle: [
            { id: event.id, label, source: "수동 지지", status: "new", started_on: day, age_days: 1 },
            { id: "watch", label: watch, source: "고점 재시도", status: "new", started_on: day, age_days: 1 },
          ] } })));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await user.click(screen.getByRole("checkbox", { name: breakoutTitle }));
    const lines = await screen.findByRole("list", { name: "선택일 돌파·재시험" });
    expect(within(lines).getByText(label)).toBeVisible();
    expect(panel().querySelector("dl")).toHaveTextContent(watch);
    expect(panel().querySelector("dl")).not.toHaveTextContent(label);
    expect(screen.queryByText("숏 진입 주의")).not.toBeInTheDocument();
    expect(screen.getAllByText("숏").find((node) => node.tagName !== "BUTTON")?.parentElement).toHaveTextContent("숏1");
  });

  it("돌파 실패 관찰일에 다른 패널의 숏 진입 주의가 충돌하지 않는다", async () => {
    const day = "2022-01-06";
    fetchApi.mockImplementation(async (url) => Response.json(String(url).includes("/breakout-retest")
      ? breakoutResult(day, { events: [breakoutEvent(day, { type: "breakout_failed", label: "상향 돌파 실패 관찰" })] })
      : result(day, { market: "롱 우세 · 정배열 유지", long_exit: "해당 없음", short_signal: "해당 없음" })));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await screen.findByText("숏 진입 주의");
    await user.click(screen.getByRole("checkbox", { name: breakoutTitle }));
    await screen.findByRole("list", { name: "선택일 돌파·재시험" });
    expect(screen.queryByText("숏 진입 주의")).not.toBeInTheDocument();
    expect(panel().querySelector("dl")).toHaveTextContent("숏 관찰·후보해당 없음");
  });

  it("같은 날 수동선 종료와 원본 후보 무효만 연결하고, 별개 스윙 저점 이탈은 상승 패널에 남긴다", async () => {
    const day = "2022-01-06";
    const manual = "기존 롱 종료 검토 · 수동 지지 100.00 이탈";
    const swing = "기존 롱 종료 검토 · 확정 스윙 저점 101.00 이탈";
    const ended = "숏 후보 무효 · 지지 회복";
    fetchApi.mockImplementation(async (url) => Response.json(String(url).includes("/breakout-retest")
      ? breakoutResult(day, { remaining_long_exits: [swing], events: [
          breakoutEvent(day, { id: "manual-break", type: "long_exit", label: manual, origin: "rise_response" }),
          breakoutEvent(day, { id: "recovered", type: "invalidated", label: ended, origin: "rise_response", status: "ended" }),
        ] })
      : result(day, { long_exit: manual + " / " + swing, short_signal: ended,
          events: [{ id: "recovered", kind: "support_reclaimed", date: day, label: ended, related: "old-short" }],
          details: { lifecycle: [{ id: "old-short", source: "수동 지지", label: "숏 후보 · 지지 재시험 실패",
            status: "invalidated", started_on: day, age_days: 1, reason: ended }] } })));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await user.click(screen.getByRole("checkbox", { name: breakoutTitle }));
    await screen.findByRole("list", { name: "선택일 돌파·재시험" });
    const outcomes = panel().querySelector("dl")!;
    expect(outcomes).toHaveTextContent(swing);
    expect(outcomes).not.toHaveTextContent(manual);
    expect(outcomes).not.toHaveTextContent(ended);
    expect(outcomes).toHaveTextContent("위 돌파·재시험에 표시");
  });

  it("돌파 조회가 실패해도 기존 상승 패널의 숏 진입 주의는 유지한다", async () => {
    const day = "2022-01-06";
    fetchApi.mockImplementation(async (url) => String(url).includes("/breakout-retest") ? new Response(null, { status: 503 })
      : Response.json(result(day, { market: "롱 우세 · 정배열 유지", long_exit: "해당 없음", short_signal: "해당 없음" })));
    const user = await load();
    await user.click(screen.getByRole("checkbox", { name: toggleName }));
    await user.click(screen.getByRole("checkbox", { name: breakoutTitle }));
    await screen.findByRole("alert");
    expect(within(panel()).getByText("숏 진입 주의")).toBeVisible();
  });
});
