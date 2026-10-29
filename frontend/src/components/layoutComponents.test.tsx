// 레이아웃 개편 컴포넌트(상단 바, 도구 막대, 기간 바, 범례) 단위 테스트 - props만으로 렌더하므로 백엔드가 필요 없다.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AppTopBar, { AppNav } from "./AppTopBar";
import ChartLegend, { pickLegendCandle } from "./ChartLegend";
import IntervalSwitch from "./IntervalSwitch";
import LineManager from "./LineManager";
import PeriodBar from "./PeriodBar";
import ToolRail, { DRAW_TOOLS } from "./ToolRail";
import type { Candle, ManualLine } from "../types";

const candle = (date: string, open: number, close: number): Candle => ({
  date, open, high: Math.max(open, close) + 5, low: Math.min(open, close) - 5, close, volume: 1,
  ema9: null, ema20: null, ema50: null, ema200: null, rsi: null,
});
const candles = [candle("2026-03-08", 100, 110), candle("2026-03-09", 110, 100), candle("2026-03-10", 100, 120)];

describe("pickLegendCandle", () => {
  it("crosshair 캔들 > 선택 캔들 > 마지막 캔들 순서", () => {
    expect(pickLegendCandle(candles, "2026-03-08", "2026-03-09")?.date).toBe("2026-03-08");
    expect(pickLegendCandle(candles, null, "2026-03-09")?.date).toBe("2026-03-09");
    expect(pickLegendCandle(candles, null, null)?.date).toBe("2026-03-10");
  });
  it("찾을 수 없는 날짜(빈 공간 등)는 다음 후보로 넘어가고, 캔들이 없으면 null", () => {
    expect(pickLegendCandle(candles, "2099-01-01", "2026-03-09")?.date).toBe("2026-03-09");
    expect(pickLegendCandle(candles, "2099-01-01", "2098-01-01")?.date).toBe("2026-03-10");
    expect(pickLegendCandle([], null, null)).toBeNull();
  });
});

describe("ChartLegend", () => {
  it("1줄에 시/고/저/종을 보여주고, 양봉/음봉으로 색 클래스가 갈린다", () => {
    const { rerender } = render(<ChartLegend candle={candle("2026-03-10", 100, 120)} toggles={[]} />);
    const row = screen.getByTestId("chart-legend-ohlc");
    expect(row).toHaveTextContent("2026-03-10");
    expect(row).toHaveTextContent("시100고125저95종120");
    const closeUpClass = screen.getByText("120").className;   // 문자열로 먼저 잡아둔다(같은 DOM 노드가 재사용됨)
    rerender(<ChartLegend candle={candle("2026-03-10", 120, 100)} toggles={[]} />);
    expect(screen.getByText("100", { selector: "span[class*=down], span[class*=up]" }).className).not.toBe(closeUpClass);
  });

  it("토글은 role=checkbox + aria-checked, 클릭하면 onToggle이 호출된다", async () => {
    const onToggle = vi.fn();
    render(
      <ChartLegend
        candle={null}
        toggles={[
          { key: "a", label: "EMA9", color: "#fff", active: true, onToggle },
          { key: "b", label: "RSI", color: "#f0f", active: false, onToggle: vi.fn() },
        ]}
      />,
    );
    expect(screen.getByRole("checkbox", { name: "EMA9" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "RSI" })).not.toBeChecked();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: "EMA9" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("extra(횡보 음영 N/K 등)를 토글 줄 끝에 그린다", () => {
    render(<ChartLegend candle={null} toggles={[]} extra={<span data-testid="extra">N K</span>} />);
    expect(screen.getByTestId("extra")).toBeInTheDocument();
  });
});

describe("ToolRail", () => {
  it("4개 도구가 라디오 버튼으로 있고 현재 모드만 활성이다", () => {
    render(<ToolRail mode="zone" onChange={() => {}} />);
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    for (const tool of DRAW_TOOLS) {
      const radio = screen.getByRole("radio", { name: tool.label });
      if (tool.value === "zone") expect(radio).toBeChecked();
      else expect(radio).not.toBeChecked();
    }
  });

  it("툴팁 문구에 이름과 클릭 횟수가 있다", () => {
    render(<ToolRail mode="select" onChange={() => {}} />);
    expect(screen.getByRole("radio", { name: /수평선/ })).toHaveAttribute("data-tip", "수평선 · 클릭 1번");
    expect(screen.getByRole("radio", { name: /추세선/ })).toHaveAttribute("data-tip", "추세선 · 클릭 2번");
    expect(screen.getByRole("radio", { name: /존/ })).toHaveAttribute("data-tip", "존 · 클릭 2번");
    expect(screen.getByRole("radio", { name: "캔들 선택" })).toHaveAttribute("data-tip", "캔들 선택");
  });

  it("누르면 해당 모드로 onChange", async () => {
    const onChange = vi.fn();
    render(<ToolRail mode="select" onChange={onChange} />);
    await userEvent.setup().click(screen.getByRole("radio", { name: /추세선/ }));
    expect(onChange).toHaveBeenCalledWith("trend");
  });
});

describe("PeriodBar", () => {
  const options = [
    { value: "최근 3개월", short: "3M" }, { value: "최근 6개월", short: "6M" },
    { value: "최근 1년", short: "1Y" }, { value: "전체", short: "전체" },
  ];

  it("짧은 글자로 보이고 접근성 이름은 기존 라벨이며 하나만 활성이다", () => {
    render(<PeriodBar options={options} value="최근 6개월" onChange={() => {}} />);
    expect(screen.getByRole("radio", { name: "최근 6개월" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "최근 1년" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "최근 3개월" })).toHaveTextContent("3M");
  });

  it("누르면 값으로 onChange, hint는 있을 때만 그린다", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<PeriodBar options={options} value="전체" onChange={onChange} />);
    await userEvent.setup().click(screen.getByRole("radio", { name: "최근 1년" }));
    expect(onChange).toHaveBeenCalledWith("최근 1년");
    expect(screen.queryByText("안내")).not.toBeInTheDocument();
    rerender(<PeriodBar options={options} value="전체" onChange={onChange} hint="안내" />);
    expect(screen.getByText("안내")).toBeInTheDocument();
  });
});

describe("AppTopBar / AppNav", () => {
  it("왼쪽 정보, 메뉴 탭, 오른쪽 동작을 그리고 메뉴를 누르면 전환 콜백이 불린다", async () => {
    const onMenu = vi.fn();
    render(
      <AppTopBar
        left={<span>BTCUSDT · 1D</span>}
        nav={<AppNav menu="scanner" onMenu={onMenu} />}
        actions={<button type="button" aria-label="데이터 새로고침" />}
      />,
    );
    expect(screen.getByText("BTCUSDT · 1D")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "데이터 새로고침" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "포지션 사이징" }));
    expect(onMenu).toHaveBeenCalledWith("position-sizing");
    await userEvent.setup().click(screen.getByRole("button", { name: "매매 기록" }));
    expect(onMenu).toHaveBeenCalledWith("trade-journal");
  });
});

describe("IntervalSwitch (1D / 1W)", () => {
  it("1D/1W 라디오 버튼, 현재 값만 활성, 누르면 그 값으로 onChange", async () => {
    const onChange = vi.fn();
    render(<IntervalSwitch value="1D" onChange={onChange} />);
    expect(screen.getByRole("radio", { name: "1D" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "1W" })).not.toBeChecked();
    await userEvent.setup().click(screen.getByRole("radio", { name: "1W" }));
    expect(onChange).toHaveBeenCalledWith("1W");
  });
});

describe("ToolRail drawingEnabled=false (1W)", () => {
  it("선택 도구만 켜져 있고 그리기 도구는 비활성이며 툴팁에 이유가 있다", async () => {
    const onChange = vi.fn();
    render(<ToolRail mode="select" onChange={onChange} drawingEnabled={false} />);
    expect(screen.getByRole("radio", { name: "캔들 선택" })).toBeEnabled();
    for (const name of [/수평선 그리기/, /추세선 그리기/, /존 그리기/]) {
      const radio = screen.getByRole("radio", { name });
      expect(radio).toBeDisabled();
      expect(radio.getAttribute("data-tip")).toContain("1D에서만 그릴 수 있음");
    }
    await userEvent.setup().click(screen.getByRole("radio", { name: /추세선 그리기/ }));
    expect(onChange).not.toHaveBeenCalled();
  });
  it("기본(1D)은 전부 활성", () => {
    render(<ToolRail mode="select" onChange={() => {}} />);
    for (const r of screen.getAllByRole("radio")) expect(r).toBeEnabled();
  });
});

describe("LineManager readOnly (1W)", () => {
  const lines: ManualLine[] = [
    { id: 1, symbol: "BTCUSDT", interval: "1d", line_type: "horizontal", time1: null, price1: 60000, time2: null, price2: null, created_at: "x", label: "수평선 60,000" },
  ];
  it("읽기 전용이면 목록만 보이고 삭제 버튼이 없다, 아니면 삭제 버튼이 있다", async () => {
    const onDelete = vi.fn();
    const { rerender } = render(<LineManager lines={lines} onDelete={onDelete} />);
    expect(screen.getByText(/그은 선 관리 \(1개\)/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "삭제" }));
    expect(onDelete).toHaveBeenCalledWith(1);
    rerender(<LineManager lines={lines} onDelete={onDelete} readOnly />);
    expect(screen.getByText(/편집은 1D에서/)).toBeInTheDocument();
    expect(screen.getByText("수평선 60,000")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "삭제" })).not.toBeInTheDocument();
  });
});
