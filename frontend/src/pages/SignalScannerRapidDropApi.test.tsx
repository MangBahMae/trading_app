// 실제 로컬 백엔드(CCX_TEST_API_PORT, 기본 8000)와 기존 패널의 연결 검사.
// 캔버스만 jsdom 제한으로 대체한다.
// 합성 신호를 주입하지 않으며 실제 응답의 enabled/data_source를 그대로 화면과 비교한다.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import SignalScanner from "./SignalScanner";
import { getRapidDrop } from "../api/rapidDrop";

vi.mock("../components/chart/TvChart", () => ({
  default: ({ onSelectDate }: { onSelectDate?: (date: string) => void }) => (
    <button onClick={() => onSelectDate?.("2023-06-11")}>고정 검증일 2023-06-11 선택</button>
  ),
}));

describe("급락 대응 실제 API → 기존 패널", () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it("날짜 선택과 토글 후 실제 응답의 상태·신호·출처를 표시한다", async () => {
    const expected = await getRapidDrop("2023-06-11");
    expect(expected.schema_version).toBe("0.3");
    expect(expected.date).toBe("2023-06-11");
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<SignalScanner nav={<span>검증</span>} />);
    await screen.findByText(/데이터 범위:/, {}, { timeout: 10000 });
    await user.click(screen.getByRole("button", { name: "고정 검증일 2023-06-11 선택" }));
    await user.click(screen.getByRole("checkbox", { name: "급락 대응 · 실험" }));
    await waitFor(() => expect(fetchSpy.mock.calls.some(([url]) => String(url).includes("/api/rapid-drop?date=2023-06-11"))).toBe(true));
    await waitFor(() => expect(screen.queryByText("선택한 날짜의 급락 대응을 불러오는 중...")).not.toBeInTheDocument(), { timeout: 10000 });
    const panel = screen.getByTestId("rapid-drop-panel");
    expect(panel.querySelector('[role="alert"]')).toBeNull();
    if (!expected.enabled) {
      expect(panel).toHaveTextContent("서버에서 급락 대응 실험 기능이 꺼져 있습니다.");
    } else {
      const summary = screen.getByTestId("rapid-drop-summary");
      expect(summary).toHaveTextContent(expected.summary.title);
      if (expected.summary.caution) expect(summary).toHaveTextContent(expected.summary.caution);
      expect(panel.querySelector("[data-signal-id]")).toBeNull();
      await user.click(screen.getByText("전체 사건·근거·기록 보기"));
      await screen.findByText("시장 판정 상세");
      for (const signal of [...expected.signals, ...expected.maintained_candidates]) {
        expect(panel).toHaveTextContent(signal.title);
        expect(panel.querySelector(`[data-signal-id="${signal.id}"]`)).not.toBeNull();
      }
      for (const event of expected.raw_events) {
        expect(panel.querySelector(`[data-event-id="${event.id}"]`)).not.toBeNull();
      }
      expect(panel).toHaveTextContent(expected.support.status === "unconfirmed" ? "지지 미확인" : "확인된 지지 버전");
      if (expected.data_source === "synthetic_demo") expect(panel).toHaveTextContent("합성 데이터 · 검증용");
      if (expected.data_source === "fixed_fixture") expect(panel).toHaveTextContent("고정 마감 일봉 데이터");
    }
  });
});
