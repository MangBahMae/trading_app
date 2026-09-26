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
import { describe, expect, it, vi } from "vitest";
import App from "../App";

vi.mock("../components/chart/TvChart", () => ({
  default: () => <div data-testid="tv-chart-mock" />,
}));

describe("신호 스캐너 화면", () => {
  it("로드 후 최신 날짜가 기본 선택되고, 해당 날짜 신호가 패널에 표시된다", async () => {
    render(<App />);

    // 데이터 범위 캡션이 뜰 때까지 대기(= /api/dashboard 로드 완료)
    await waitFor(
      () => {
        expect(screen.getByText(/데이터 범위:/)).toBeInTheDocument();
      },
      { timeout: 10000 },
    );

    // 최신 날짜(2026-09-26)가 우측 패널에 기본 선택돼 표시됨
    await waitFor(() => {
      expect(screen.getByText("2026-09-26")).toBeInTheDocument();
    });

    // 통합 탭 기본 진입 - 롱 1건/숏 0건(백엔드에서 직접 확인한 값)
    // "롱"이라는 텍스트는 탭 버튼과 메트릭 라벨 둘 다에 있어 getAllByText로
    // 받고, 버튼이 아닌(메트릭 라벨) 쪽의 부모(.metric)에서 숫자를 확인한다.
    const longTexts = screen.getAllByText("롱");
    const longLabel = longTexts.find((el) => el.tagName !== "BUTTON");
    expect(longLabel?.parentElement).toHaveTextContent("1");
  });

  it("숏 탭을 누르면 그 날짜에 숏 신호가 없다는 안내가 뜬다", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => screen.getByText("2026-09-26"), { timeout: 10000 });

    await user.click(screen.getByRole("button", { name: "숏" }));
    expect(screen.getByText("이 날짜에 숏 신호가 없습니다.")).toBeInTheDocument();
  });

  it("표시 기간/드로우 모드/EMA·RSI·다이버전스 체크박스가 정상 토글된다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText("2026-09-26"), { timeout: 10000 });

    const yearRadio = screen.getByLabelText("최근 1년") as HTMLInputElement;
    expect(yearRadio.checked).toBe(false);
    await user.click(yearRadio);
    expect(yearRadio.checked).toBe(true);

    const emaCheckbox = screen.getByLabelText("EMA20") as HTMLInputElement;
    expect(emaCheckbox.checked).toBe(false);
    await user.click(emaCheckbox);
    expect(emaCheckbox.checked).toBe(true);

    const rsiCheckbox = screen.getByLabelText("RSI") as HTMLInputElement;
    await user.click(rsiCheckbox);
    expect(rsiCheckbox.checked).toBe(true);

    const trendRadio = screen.getByLabelText(/추세선 그리기/) as HTMLInputElement;
    await user.click(trendRadio);
    expect(screen.getByText(/시작점과 끝점, 두 번 클릭하세요/)).toBeInTheDocument();
  });

  it("사이드 네비게이션으로 포지션 사이징 화면과 전환된다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText("2026-09-26"), { timeout: 10000 });

    await user.click(screen.getByRole("button", { name: "포지션 사이징" }));
    expect(screen.getByText("포지션 사이징 계산기")).toBeInTheDocument();

    // 신호 스캐너로 되돌아오면 SignalScanner가 재마운트되며 /api/dashboard를
    // 다시 호출한다(현재 구현은 화면 상태를 유지하지 않음) - 로드가 끝날 때까지 대기.
    await user.click(screen.getByRole("button", { name: "신호 스캐너" }));
    await waitFor(
      () => expect(screen.getByText("BTCUSDT 1d 통합 신호 대시보드")).toBeInTheDocument(),
      { timeout: 10000 },
    );
  });
});
