// 실제 렌더된 컴포넌트 + 실제로 떠 있는 백엔드(localhost:8000)를 통합 테스트로
// 검증한다(1,2단계와 동일한 이유 - 브라우저 자동화 도구 없음). App 기본
// 화면(신호 스캐너)의 TvChart는 jsdom에 real canvas가 없어 크래시하므로 mock
// 처리(SignalScanner.test.tsx와 동일한 이유).
//
// 이 테스트가 만든 매매 기록은 전부 끝나고 삭제한다(실제 data/trades.db에
// 남기지 않기 위함 - "삭제" 버튼 클릭 흐름 자체도 검증할 겸 마지막 테스트에서
// UI를 통해 지운다).
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../App";

vi.mock("../components/chart/TvChart", () => ({
  default: () => <div data-testid="tv-chart-mock" />,
}));

// jsdom은 window.confirm()을 구현하지 않아 기본적으로 undefined(falsy)를
// 반환한다 - TradeJournal의 삭제 확인 다이얼로그가 항상 "취소"로 판정돼서
// 정리(cleanup) 클릭이 실제로는 삭제를 안 하고 넘어가는 걸 처음에 놓쳤다
// (레코드가 DB에 계속 남음). true를 반환하도록 명시적으로 스텁한다.
vi.stubGlobal("confirm", () => true);

// 전체 파일이 실제 백엔드에 붙어 통합 테스트를 하다 보니(다른 테스트 파일과
// 동시에 돌 때 백엔드 응답이 느려질 수 있음), find*/waitFor 전부 넉넉한
// 타임아웃을 명시적으로 준다 - 기본값(1000ms)에 걸려 실패하는 걸 방지.
const LONG_TIMEOUT = { timeout: 10000 };

async function goToTradeJournal(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => screen.getByRole("button", { name: "매매 기록" }), LONG_TIMEOUT);
  await user.click(screen.getByRole("button", { name: "매매 기록" }));
  await screen.findByRole("heading", { name: "매매 기록" }, LONG_TIMEOUT);
}

describe("매매 기록(기능 2) 화면", () => {
  it("계획 작성 -> 검증 실패 -> 필수값 채워 확정 -> 목록에 진행중으로 표시된다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await goToTradeJournal(user);

    await user.click(screen.getByRole("button", { name: "+ 새 계획 작성" }));
    await screen.findByRole("heading", { name: "진입 전 계획" }, LONG_TIMEOUT);

    // 필수값을 안 채우고 확정 시도 -> 서버 검증 에러가 그대로 표시돼야 함
    await user.click(screen.getByRole("button", { name: "계획 확정 (진행중으로 전환)" }));
    await waitFor(() => {
      expect(screen.getByText("진입 근거를 입력해주세요")).toBeInTheDocument();
    }, LONG_TIMEOUT);

    // 필수 필드 채우기
    await user.type(screen.getByLabelText("진입 근거 (필수)"), "EMA50 지지 확인 테스트");
    await user.type(screen.getByLabelText("무효화 지점 서술 (필수)"), "EMA50 이탈 시 무효");
    await user.type(screen.getByLabelText("무효화 지점 가격 (필수)"), "113000");
    await user.type(screen.getByLabelText("SL (필수, 실제 손절 실행가)"), "113800");
    await user.type(screen.getByLabelText("진입 1 가격"), "118000");
    await user.type(screen.getByLabelText("TP 1 가격"), "122000");
    await user.type(screen.getByLabelText("증거금 (필수)"), "1000");
    const leverageInput = screen.getByLabelText("레버리지 (필수)") as HTMLInputElement;
    await user.clear(leverageInput);
    await user.type(leverageInput, "10");

    await user.click(screen.getByRole("button", { name: "계획 확정 (진행중으로 전환)" }));

    // 저장 성공 시 목록으로 돌아가고, 방금 만든 계획이 "진행중"으로 보여야 함.
    // (getByRole은 못 찾으면 예외를 던지므로 부재 확인엔 queryByRole을 써야
    // waitFor가 정상적으로 재시도/수렴한다 - getByRole+not.toBeInTheDocument()
    // 조합은 클래식한 testing-library 안티패턴)
    await waitFor(
      () => {
        expect(screen.queryByRole("heading", { name: "진입 전 계획" })).not.toBeInTheDocument();
      },
      LONG_TIMEOUT,
    );
    expect(screen.getAllByText("진행중").length).toBeGreaterThan(0);
  });

  it("상세 화면에서 청산 기록을 작성하면 실현 R이 계산돼 표시된다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await goToTradeJournal(user);

    // 방금 만든(또는 이전 테스트가 만든) 진행중 매매 하나를 클릭해서 상세로 진입.
    // "진행중" 텍스트는 목록 상단 필터 버튼에도 있어서(전체/임시저장/진행중/완료),
    // 상태 배지(span)로 한정해서 찾아야 실제 행을 클릭하게 된다.
    const badges = await screen.findAllByText("진행중", { selector: "span" }, LONG_TIMEOUT);
    await user.click(badges[0]);
    await screen.findByRole("button", { name: "청산 기록 작성" }, LONG_TIMEOUT);

    await user.click(screen.getByRole("button", { name: "청산 기록 작성" }));
    await screen.findByText(/청산 후 기록 -/, {}, LONG_TIMEOUT);

    await user.type(screen.getByLabelText("청산 1 가격"), "122000");
    await user.type(screen.getByLabelText("실현손익"), "500");
    await user.click(screen.getByRole("radio", { name: "TP 도달" }));

    await user.click(screen.getByRole("button", { name: "청산 기록 저장 (완료로 전환)" }));

    await waitFor(() => {
      const heading = screen.getByRole("heading", { level: 2 });
      expect(heading.textContent).toContain("완료");
    }, LONG_TIMEOUT);

    const realizedRLabel = screen.getByText("실현 R");
    expect(realizedRLabel.nextElementSibling?.textContent).toMatch(/R$/);

    // 정리: 삭제 버튼으로 이 테스트가 만든 레코드를 지운다
    await user.click(screen.getByRole("button", { name: "삭제" }));
  });

  it("포지션 사이징 계산기 열기 버튼을 누르면 화면이 전환된다", async () => {
    const user = userEvent.setup();
    render(<App />);
    await goToTradeJournal(user);

    await user.click(screen.getByRole("button", { name: "+ 새 계획 작성" }));
    await screen.findByRole("heading", { name: "진입 전 계획" }, LONG_TIMEOUT);

    await user.click(screen.getByRole("button", { name: /계산기로 채우기/ }));
    await waitFor(() => {
      expect(screen.getByText("포지션 사이징 계산기")).toBeInTheDocument();
    }, LONG_TIMEOUT);
  });
});
