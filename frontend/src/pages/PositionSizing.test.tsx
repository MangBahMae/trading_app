// 브라우저 자동화 도구가 이 환경에 없어서, 대신 실제 렌더된 컴포넌트에
// 진짜 타이핑 이벤트를 흘려보내고(jsdom) 실제로 떠 있는 백엔드(localhost:8000)에
// 진짜 네트워크 요청을 보내 결과를 검증한다 - "Enter 없이 즉시 반응하는지"를
// 목업이 아니라 실제 통합 경로로 확인하기 위함.
//
// 사전조건: backend가 http://localhost:8000 에서 떠 있어야 한다
// (uvicorn app.main:app --port 8000).
//
// 2단계(신호 스캐너) 도입 후 App의 기본 화면이 "신호 스캐너"로 바뀌어서,
// 포지션 사이징 화면을 보려면 먼저 네비게이션 클릭이 필요하다. 또한 기본
// 화면인 SignalScanner가 실제 TvChart(lightweight-charts)를 마운트하면
// jsdom엔 real canvas가 없어서 비동기 애니메이션 프레임에서 예외가 터지므로
// (SignalScanner.test.tsx 상단 설명 참고) 여기서도 동일하게 mock 처리한다.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../App";

vi.mock("../components/chart/TvChart", () => ({
  default: () => <div data-testid="tv-chart-mock" />,
}));

async function goToPositionSizing(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => screen.getByRole("button", { name: "포지션 사이징" }), { timeout: 10000 });
  await user.click(screen.getByRole("button", { name: "포지션 사이징" }));
  await screen.findByText("포지션 사이징 계산기");
}

describe("포지션 사이징 화면 - 실시간 반응성", () => {
  it("잔고/진입가 입력 시 Enter 없이 즉시 원화 환산 캡션이 갱신된다 (클라이언트 사이드)", async () => {
    const user = userEvent.setup();
    render(<App />);
    await goToPositionSizing(user);

    const balanceInput = screen.getByLabelText("잔고 (USDT)") as HTMLInputElement;
    await user.clear(balanceInput);
    await user.type(balanceInput, "1000");

    // 디바운스(백엔드 호출)를 기다릴 필요 없이 - 원화 환산 캡션은 클라이언트에서
    // 즉시 계산되므로 act() 플러시만으로 바로 보여야 한다.
    await waitFor(() => {
      expect(screen.getByText(/확정값:/)).toBeInTheDocument();
    });

    const entryPriceInput = screen.getByLabelText("진입 1 가격") as HTMLInputElement;
    await user.clear(entryPriceInput);
    await user.type(entryPriceInput, "65000");

    await waitFor(() => {
      expect(screen.getByText(/65,000 USDT ≈/)).toBeInTheDocument();
    });
  });

  it("입력을 마치면(디바운스 후) 백엔드 계산 결과가 자동으로 채워진다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await goToPositionSizing(user);

    const entryPriceInput = screen.getByLabelText("진입 1 가격") as HTMLInputElement;
    await user.clear(entryPriceInput);
    await user.type(entryPriceInput, "118000");

    const stopLossInput = screen.getByLabelText("손절가") as HTMLInputElement;
    await user.clear(stopLossInput);
    await user.type(stopLossInput, "113800");

    // 진입가=118000, 손절가=113800 -> stop_pct는 환율과 무관하게 결정적으로
    // 3.56%가 나와야 한다 (환율은 balance->KRW 환산에만 쓰이므로 이 값에는
    // 영향 없음). 백엔드 응답이 올 때까지(디바운스 200ms + 네트워크) 기다린다.
    await waitFor(
      () => {
        expect(screen.getByText(/손절 폭: 3\.56%/)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );

    // 평단(예상 평단)도 진입가와 동일하게 표시돼야 함
    expect(screen.getByText(/예상 평단: 118,000/)).toBeInTheDocument();

    // 1R/포지션 사이즈 메트릭도 채워짐(환율 의존값이라 정확한 숫자 대신
    // "계산 불가"가 아니라 실제 숫자가 표시됐는지만 확인)
    expect(screen.queryByText("계산 불가")).not.toBeInTheDocument();
  });
});
