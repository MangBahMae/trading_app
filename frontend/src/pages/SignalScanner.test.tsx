// 브라우저 자동화 도구가 없는 환경이라(1단계와 동일한 제약), 실제 렌더된
// 컴포넌트 + 실제로 떠 있는 백엔드(localhost:8000)를 통합 테스트로 검증한다.
//
// 중요한 한계: lightweight-charts는 실제 <canvas> 2D 렌더링 컨텍스트가 있어야
// 하는데 jsdom은 그걸 구현하지 않는다. 처음엔 "Not implemented: getContext()"
// 경고만 뜨고 조용히 넘어가는 줄 알았는데, 실제로는 내부 requestAnimationFrame
// 리사이즈/리드로우 루프가 테스트 본문이 끝난 뒤 비동기로 실행되면서
// "ensureNotNull: Value is null" 예외를 던져 테스트 프로세스 전체가 오염된다
// (jsdom에 real canvas 백엔드(canvas npm 패키지, 네이티브 빌드 필요)가 없는 한
// 근본적으로 못 돌린다 - 이번 세션 범위에서 그 패키지 설치는 하지 않음).
// 그래서 TvChart는 여기서 목(mock)으로 대체하고, 그 "주변" 로직(데이터 로드,
// 기본 선택 날짜 표시, 탭 전환, 컨트롤 위젯, 화면 전환)만 실제 렌더+실제
// 백엔드로 검증한다. 캔들 클릭 시 패널 갱신 / 줌 유지 자체는 진짜 canvas
// 좌표 계산이 필요해 여기선 검증 불가 - 사용자가 직접 브라우저에서 확인 필요.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";

vi.mock("../components/chart/TvChart", () => ({
  default: (props: { marketStateBlocks?: unknown[]; readOnly?: boolean; barStepDays?: number; bars?: unknown[] }) => (
    <div
      data-testid="tv-chart-mock" data-market-blocks={props.marketStateBlocks?.length ?? -1}
      data-read-only={String(props.readOnly ?? false)} data-step-days={props.barStepDays ?? 1}
      data-bars={props.bars?.length ?? 0}
    />
  ),
}));

// 데이터는 매일 늘어나므로 "최신 날짜"를 테스트에 박아두지 않고, 화면 캡션의 데이터 범위 끝 날짜를 읽는다.
async function waitForLatestDate(): Promise<string> {
  const caption = await screen.findByText(/데이터 범위:/, {}, { timeout: 10000 });
  const last = /~\s*(\d{4}-\d{2}-\d{2})/.exec(caption.textContent ?? "")?.[1];
  expect(last).toBeTruthy();
  // 최신 날짜가 우측 패널(과 차트 범례)에 기본 선택돼 표시된다
  await screen.findAllByText(last as string, {}, { timeout: 10000 });
  return last as string;
}

const blockCount = () =>
  Number(screen.getByTestId("tv-chart-mock").getAttribute("data-market-blocks"));

describe("신호 스캐너 화면", () => {
  it("로드 후 최신 날짜가 기본 선택되고, 해당 날짜 신호가 패널에 표시된다", async () => {
    render(<App />);
    await waitForLatestDate();

    // 통합 탭 기본 진입 - 롱/숏 건수 메트릭이 숫자로 표시된다
    // "롱"이라는 텍스트는 탭 버튼과 메트릭 라벨 둘 다에 있어 getAllByText로
    // 받고, 버튼이 아닌(메트릭 라벨) 쪽의 부모(.metric)에서 숫자를 확인한다.
    const longTexts = screen.getAllByText("롱");
    const longLabel = longTexts.find((el) => el.tagName !== "BUTTON");
    expect(longLabel?.parentElement).toHaveTextContent(/\d+/);
  });

  it("숏 탭을 누르면 통합 탭의 건수 메트릭이 사라지고 숏 신호 목록(없으면 안내)이 뜬다", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitForLatestDate();

    await user.click(screen.getByRole("button", { name: "숏" }));
    // 그날 숏 신호가 있는지는 데이터에 따라 달라서(매일 바뀜) 목록 또는 안내문 중 하나가 보이면 된다.
    const hasEmptyMessage = screen.queryByText("이 날짜에 숏 신호가 없습니다.") !== null;
    const hasShortList = document.querySelectorAll("ul li").length > 0;
    expect(hasEmptyMessage || hasShortList).toBe(true);
    expect(screen.queryAllByText("롱").some((el) => el.tagName !== "BUTTON")).toBe(false);
  });

  it("표시 기간/드로우 모드/EMA·RSI 체크박스가 정상 토글된다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitForLatestDate();

    // 기간 바 / 범례 토글 / 도구 막대는 role=radio·checkbox 버튼이라 접근성 이름과 toBeChecked 로 확인한다
    const yearRadio = screen.getByRole("radio", { name: "최근 1년" });
    expect(yearRadio).not.toBeChecked();
    await user.click(yearRadio);
    expect(yearRadio).toBeChecked();
    expect(screen.getByRole("radio", { name: "최근 6개월" })).not.toBeChecked();   // 하나만 활성

    const emaCheckbox = screen.getByRole("checkbox", { name: "EMA20" });
    expect(emaCheckbox).not.toBeChecked();
    await user.click(emaCheckbox);
    expect(emaCheckbox).toBeChecked();
    await user.click(emaCheckbox);
    expect(emaCheckbox).not.toBeChecked();

    const rsiCheckbox = screen.getByRole("checkbox", { name: "RSI" });
    await user.click(rsiCheckbox);
    expect(rsiCheckbox).toBeChecked();

    const selectTool = screen.getByRole("radio", { name: "캔들 선택" });
    expect(selectTool).toBeChecked();
    const trendRadio = screen.getByRole("radio", { name: /추세선 그리기/ });
    await user.click(trendRadio);
    expect(trendRadio).toBeChecked();
    expect(selectTool).not.toBeChecked();
    expect(screen.getByText(/시작점과 끝점, 두 번 클릭하세요/)).toBeInTheDocument();
    await user.click(selectTool);
    expect(screen.queryByText(/시작점과 끝점, 두 번 클릭하세요/)).not.toBeInTheDocument();
  });

  it("사이드 네비게이션으로 포지션 사이징 화면과 전환된다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitForLatestDate();

    await user.click(screen.getByRole("button", { name: "포지션 사이징" }));
    expect(screen.getByText("포지션 사이징 계산기")).toBeInTheDocument();

    // 신호 스캐너로 되돌아오면 SignalScanner가 재마운트되며 /api/dashboard를
    // 다시 호출한다(현재 구현은 화면 상태를 유지하지 않음) - 로드가 끝날 때까지 대기.
    await user.click(screen.getByRole("button", { name: "신호 스캐너" }));
    await waitFor(
      () => expect(screen.getByText("BTCUSDT · 1D")).toBeInTheDocument(),
      { timeout: 10000 },
    );
  });

  it("다이버전스는 플래그로 꺼져 있어 체크박스가 보이지 않는다", async () => {
    render(<App />);
    await waitForLatestDate();
    expect(screen.queryByLabelText("다이버전스")).not.toBeInTheDocument();
  });

  // 시장 상태(횡보 음영)는 실험 단계라 기본 OFF다 - 켜기 전에는 요청도, 음영도, 상태 박스도, N/K 입력칸도 없다.
  describe("시장 상태(횡보 음영, 신호 아님) - 실험 단계, 기본 OFF", () => {
    const marketStateRequests = () =>
      vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes("/api/market-state")).length;

    beforeEach(() => {
      vi.spyOn(globalThis, "fetch");
    });
    afterEach(() => {
      vi.restoreAllMocks();
    });

    async function enableMarketState(user: ReturnType<typeof userEvent.setup>) {
      await user.click(screen.getByLabelText("횡보 음영"));
      await screen.findByTestId("market-state-box", {}, { timeout: 10000 });
    }

    it("기본값은 OFF: 체크 해제, 상태 박스/음영 블록/N·K 입력칸이 없고 서버 요청도 안 나간다", async () => {
      render(<App />);
      await waitForLatestDate();
      await new Promise((r) => setTimeout(r, 500)); // 디바운스(200ms)보다 길게 기다려도 요청이 없어야 한다

      expect(screen.getByLabelText("횡보 음영")).not.toBeChecked();
      expect(screen.queryByTestId("market-state-box")).not.toBeInTheDocument();
      expect(blockCount()).toBe(0);
      expect(screen.queryByLabelText("N")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("K")).not.toBeInTheDocument();
      expect(marketStateRequests()).toBe(0);
    });

    it("켜면 패널 상단에 상태/사유/B 간격/C 교차가 표시되고 N·K 입력칸이 나타난다", async () => {
      const user = userEvent.setup();
      render(<App />);
      await waitForLatestDate();
      await enableMarketState(user);

      const box = screen.getByTestId("market-state-box");
      expect(box).toHaveTextContent(/시장 상태 (상승|하락|횡보) · 사유 (A|BC|없음)/);
      expect(box).toHaveTextContent("B 간격 축소");
      expect(box).toHaveTextContent("기준 4회 이상"); // 기본 K=4
      expect(screen.getByLabelText("N")).toBeInTheDocument();
      expect(screen.getByLabelText("K")).toBeInTheDocument();
    });

    it("토글: 켜면 차트에 블록이 넘어가고, 끄면 블록/박스/입력칸이 사라지고, 다시 켜도 재요청 없이 돌아온다", async () => {
      const user = userEvent.setup();
      render(<App />);
      await waitForLatestDate();
      await enableMarketState(user);
      await waitFor(() => expect(blockCount()).toBeGreaterThan(0), { timeout: 10000 });
      const before = blockCount();
      expect(marketStateRequests()).toBe(1);

      await user.click(screen.getByLabelText("횡보 음영"));
      await waitFor(() => expect(blockCount()).toBe(0));
      expect(screen.queryByTestId("market-state-box")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("K")).not.toBeInTheDocument();

      await user.click(screen.getByLabelText("횡보 음영"));
      await waitFor(() => expect(blockCount()).toBe(before));
      expect(screen.getByTestId("market-state-box")).toBeInTheDocument();
      await new Promise((r) => setTimeout(r, 500));
      expect(marketStateRequests()).toBe(1); // 이미 받은 결과를 재사용 - 다시 요청하지 않는다
    });

    it("K를 바꾸면 바로 서버에 다시 계산을 요청해 패널의 기준과 음영 블록이 갱신된다", async () => {
      const user = userEvent.setup();
      render(<App />);
      await waitForLatestDate();
      await enableMarketState(user);
      await waitFor(() => expect(blockCount()).toBeGreaterThan(0), { timeout: 10000 });

      const kInput = screen.getByLabelText("K") as HTMLInputElement;
      await user.clear(kInput);
      await user.type(kInput, "9");

      await waitFor(
        () => expect(screen.getByTestId("market-state-box")).toHaveTextContent("기준 9회 이상"),
        { timeout: 10000 },
      );
      expect(Number.isNaN(blockCount())).toBe(false);
      expect(blockCount()).toBeGreaterThan(0);
      expect(marketStateRequests()).toBe(2); // 기본 K=4 한 번 + K=9 한 번
    });

    it("K가 N보다 크면 안내가 뜨고 요청하지 않는다(이전 결과 유지)", async () => {
      const user = userEvent.setup();
      render(<App />);
      await waitForLatestDate();
      await enableMarketState(user);

      const kInput = screen.getByLabelText("K") as HTMLInputElement;
      await user.clear(kInput);
      await user.type(kInput, "11"); // 기본 N=10 -> K>N

      expect(await screen.findByText(/K는 0 이상 N 이하 정수/)).toBeInTheDocument();
      expect(screen.getByTestId("market-state-box")).toHaveTextContent("기준 4회 이상");
      await new Promise((r) => setTimeout(r, 500));
      expect(marketStateRequests()).toBe(1);
    });
  });
});

describe("1D / 1W 전환 (주봉)", () => {
  it("기본은 1D(일봉, 편집 가능). 1W로 바꾸면 주봉 데이터와 읽기 전용 모드, 1D로 돌아오면 일봉", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitForLatestDate();
    const chart = () => screen.getByTestId("tv-chart-mock");

    expect(screen.getByRole("radio", { name: "1D" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "1W" })).not.toBeChecked();
    expect(screen.getByText("BTCUSDT · 1D")).toBeInTheDocument();
    expect(chart()).toHaveAttribute("data-read-only", "false");
    expect(chart()).toHaveAttribute("data-step-days", "1");
    const dailyBars = Number(chart().getAttribute("data-bars"));
    expect(screen.getByRole("radio", { name: /추세선 그리기/ })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "횡보 음영" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "1W" }));
    await waitFor(() => expect(screen.getByText("BTCUSDT · 1W")).toBeInTheDocument(), { timeout: 10000 });
    expect(screen.getByRole("radio", { name: "1W" })).toBeChecked();
    expect(screen.getByText(/데이터 범위: 2022-01-03/)).toBeInTheDocument();         // 주봉은 2022-01-03(월요일)부터
    expect(chart()).toHaveAttribute("data-read-only", "true");                         // 선/존은 표시만
    expect(chart()).toHaveAttribute("data-step-days", "7");                            // 한 칸 = 7일
    expect(Number(chart().getAttribute("data-bars"))).toBeLessThan(dailyBars / 3);     // 같은 기간이라도 주봉은 캔들이 훨씬 적다
    expect(screen.getByRole("radio", { name: /추세선 그리기/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /존 그리기/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /수평선 그리기/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "캔들 선택" })).toBeEnabled();
    expect(screen.queryByRole("checkbox", { name: "횡보 음영" })).not.toBeInTheDocument();   // 일봉 전용 실험 기능
    expect(screen.getByRole("checkbox", { name: "EMA200" })).toBeInTheDocument();             // EMA/RSI 토글은 그대로
    expect(screen.getByText(/주봉: 선\/존은 1D에서 그린 것을 표시만/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "삭제" })).not.toBeInTheDocument();           // 그은 선 관리에 삭제 버튼 없음

    await user.click(screen.getByRole("radio", { name: "1D" }));
    expect(screen.getByText("BTCUSDT · 1D")).toBeInTheDocument();
    expect(chart()).toHaveAttribute("data-read-only", "false");
    expect(chart()).toHaveAttribute("data-step-days", "1");
    expect(Number(chart().getAttribute("data-bars"))).toBe(dailyBars);
    expect(screen.getByRole("radio", { name: /추세선 그리기/ })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "횡보 음영" })).toBeInTheDocument();
  });

  it("1W 패널에는 주봉 신호만 나오고, 일봉/주봉이 선택한 날짜를 따로 들고 있다", async () => {
    const user = userEvent.setup();
    render(<App />);
    const dailyLast = await waitForLatestDate();
    await user.click(screen.getByRole("radio", { name: "1W" }));
    await waitFor(() => expect(screen.getByText("BTCUSDT · 1W")).toBeInTheDocument(), { timeout: 10000 });
    const caption = screen.getByText(/데이터 범위:/).textContent ?? "";
    const weeklyLast = /~\s*(\d{4}-\d{2}-\d{2})/.exec(caption)?.[1] as string;
    expect(weeklyLast <= dailyLast).toBe(true);
    expect((await screen.findAllByText(weeklyLast)).length).toBeGreaterThan(0);       // 주봉의 마지막 주가 패널에 선택돼 있다
    // 패널의 신호 문구는 전부 주봉 신호("주봉 ...")다 - 일봉 신호 문구가 섞여 나오지 않는다
    const texts = Array.from(document.querySelectorAll("ul li")).map((li) => li.textContent ?? "");
    expect(texts.every((t) => t.startsWith("- 주봉 ") || !t.startsWith("- "))).toBe(true);
    await user.click(screen.getByRole("radio", { name: "1D" }));
    expect((await screen.findAllByText(dailyLast)).length).toBeGreaterThan(0);          // 일봉 선택은 그대로
  });
});
