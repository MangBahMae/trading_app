import { useEffect, useRef } from "react";
import {
  createChart,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { DivergenceMarker, DrawMode, ManualLine } from "../../types";
import type { Bar } from "./chartLogic";
import { buildCandleData, buildVolumeData, formatDateWithWeekday, trendPriceAt } from "./chartLogic";

export interface EmaSeriesConfig {
  color: string;
  dashed: boolean;
  visible: boolean;
  data: { time: string; value: number }[];
}

export interface RsiSeriesConfig {
  visible: boolean;
  data: { time: string; value: number }[];
}

interface TvChartProps {
  bars: Bar[];
  selectedDate: string | null;
  height: number;
  emaSeries: Record<string, EmaSeriesConfig>;
  rsiSeries: RsiSeriesConfig;
  divergenceMarkers: DivergenceMarker[];
  divMarkerColors: Record<string, string>;
  drawMode: DrawMode;
  lines: ManualLine[];
  onSelectDate: (date: string) => void;
  onAddHorizontalLine: (price: number) => void;
  onAddTrendLine: (time1: string, price1: number, time2: string, price2: number) => void;
}

// components/tv_chart/frontend/index.html(기존 Streamlit 커스텀 컴포넌트)의
// 로직을 그대로 옮긴 React 버전. 서드파티 React 래퍼 대신 lightweight-charts를
// 직접 useRef+useEffect로 감싼다(공식 권장 패턴) - RSI 서브패널, 다이버전스
// 연결선/마커, 3모드 클릭(선택/수평선/추세선), opacity 하이라이트, "데이터
// 구성 자체가 바뀔 때만 fitContent()"로 줌 유지하는 로직까지 원본과 동일하게.
//
// 원본이 var 전역변수로 들고 있던 "iframe 생애주기 동안 유지되는 상태"는
// 여기선 컴포넌트 인스턴스 생애주기 동안 유지되는 ref로 대응한다(리렌더 때마다
// 새로 만들지 않음 - 이게 줌/이동 상태 보존의 핵심).
export default function TvChart({
  bars, selectedDate, height, emaSeries, rsiSeries, divergenceMarkers,
  divMarkerColors, drawMode, lines, onSelectDate, onAddHorizontalLine, onAddTrendLine,
}: TvChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi70SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi30SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const emaSeriesMapRef = useRef<Record<string, ISeriesApi<"Line">>>({});
  const divLineSeriesRef = useRef<ISeriesApi<"Line">[]>([]);
  const divergencePriceMarkersRef = useRef<SeriesMarker<Time>[]>([]);
  const pendingTrendMarkerRef = useRef<SeriesMarker<Time> | null>(null);
  const lastBarTimesRef = useRef<string | null>(null);
  const currentDrawModeRef = useRef<DrawMode>("select");
  const pendingTrendPointRef = useRef<{ time: string; price: number } | null>(null);
  const priceLineRefsRef = useRef<IPriceLine[]>([]);
  const trendSeriesMapRef = useRef<Record<number, ISeriesApi<"Line">>>({});
  const firstBarTimeRef = useRef<string | null>(null);
  const lastBarTimeRef = useRef<string | null>(null);

  // 클릭 핸들러(subscribeClick)는 최초 마운트 시 한 번만 등록하는데, 그 안에서
  // 항상 "최신" 콜백/드로우모드를 참조해야 하므로 ref에 담아 매 렌더마다 갱신한다.
  const callbacksRef = useRef({ onSelectDate, onAddHorizontalLine, onAddTrendLine });
  useEffect(() => {
    callbacksRef.current = { onSelectDate, onAddHorizontalLine, onAddTrendLine };
  }, [onSelectDate, onAddHorizontalLine, onAddTrendLine]);

  function applyCandleMarkers() {
    const markers = divergencePriceMarkersRef.current.slice();
    if (pendingTrendMarkerRef.current) markers.push(pendingTrendMarkerRef.current);
    markers.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
    candleSeriesRef.current?.setMarkers(markers);
  }

  // 차트 생성 - 최초 마운트 시 1회만 (컴포넌트가 언마운트될 때까지 재생성 안 함,
  // 이게 줌/이동 상태가 리렌더와 무관하게 유지되는 핵심).
  useEffect(() => {
    const container = containerRef.current;
    if (!container || chartRef.current) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: { textColor: "#333333", background: { color: "#ffffff" } },
      grid: { vertLines: { color: "#eeeeee" }, horzLines: { color: "#eeeeee" } },
      rightPriceScale: { borderColor: "#cccccc" },
      timeScale: { borderColor: "#cccccc", tickMarkFormatter: () => "" },
      localization: { timeFormatter: formatDateWithWeekday },
      crosshair: { mode: CrosshairMode.Normal },
      handleScroll: true,
      handleScale: true,
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#26a69a", downColor: "#ef5350",
      wickUpColor: "#26a69a", wickDownColor: "#ef5350",
      borderUpColor: "#26a69a", borderDownColor: "#ef5350",
    });
    candleSeriesRef.current = candleSeries;

    chart.priceScale("right").applyOptions({ scaleMargins: { top: 0.05, bottom: 0.45 } });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volumeSeriesRef.current = volumeSeries;
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.55, bottom: 0.25 } });

    const rsiSeriesApi = chart.addLineSeries({
      color: "#7b1fa2", lineWidth: 1, priceScaleId: "rsi", visible: false,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false, title: "RSI",
    });
    rsiSeriesRef.current = rsiSeriesApi;
    chart.priceScale("rsi").applyOptions({ scaleMargins: { top: 0.78, bottom: 0.02 } });

    rsi70SeriesRef.current = chart.addLineSeries({
      color: "#ff6f42", lineWidth: 1, lineStyle: LineStyle.Dotted, priceScaleId: "rsi",
      visible: false, crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
    });
    rsi30SeriesRef.current = chart.addLineSeries({
      color: "#4169e1", lineWidth: 1, lineStyle: LineStyle.Dotted, priceScaleId: "rsi",
      visible: false, crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
    });

    // 캔들의 시간축 칸 아무 곳을 클릭해도 그 캔들의 time을 준다(lightweight-charts
    // 기본 동작). 그리기 모드일 때는 같은 클릭을 신호패널용 "선택"이 아니라
        // 선 추가용 좌표로 쓴다.
    chart.subscribeClick((param: MouseEventParams) => {
      if (!param || !param.time) return;
      const mode = currentDrawModeRef.current;
      const { onSelectDate: select, onAddHorizontalLine: addH, onAddTrendLine: addT } = callbacksRef.current;

      if (mode === "select") {
        select(param.time as string);
        return;
      }

      const price = param.point ? candleSeries.coordinateToPrice(param.point.y) : null;
      if (price === null || price === undefined) return;

      if (mode === "horizontal") {
        addH(price);
        return;
      }

      if (mode === "trend") {
        if (!pendingTrendPointRef.current) {
          pendingTrendPointRef.current = { time: param.time as string, price };
          pendingTrendMarkerRef.current = {
            time: param.time as Time, position: "aboveBar", color: "#ff9800", shape: "circle", text: "1",
          };
          applyCandleMarkers();
        } else {
          const p1 = pendingTrendPointRef.current;
          addT(p1.time, p1.price, param.time as string, price);
          pendingTrendPointRef.current = null;
          pendingTrendMarkerRef.current = null;
          applyCandleMarkers();
        }
      }
    });

    chart.subscribeCrosshairMove((param: MouseEventParams) => {
      container.style.cursor = param && param.time ? "pointer" : "default";
    });

    const handleResize = () => {
      chart.applyOptions({ width: container.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 렌더 - 원본 onRender(args)와 동일한 역할. bars/selectedDate/ema/rsi/
  // divergence/drawMode/lines 중 하나라도 바뀌면 다시 그린다.
  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!chart || !candleSeries || !volumeSeries) return;

    // 그리기 모드가 바뀌면 대기 중이던 추세선 임시 상태를 정리한다.
    if (drawMode !== currentDrawModeRef.current) {
      pendingTrendPointRef.current = null;
      pendingTrendMarkerRef.current = null;
      applyCandleMarkers();
    }
    currentDrawModeRef.current = drawMode;

    if (bars.length > 0) {
      firstBarTimeRef.current = bars[0].time;
      lastBarTimeRef.current = bars[bars.length - 1].time;
    }

    const barTimes = bars.map((b) => b.time).join(",");
    const dataChanged = barTimes !== lastBarTimesRef.current;
    lastBarTimesRef.current = barTimes;

    candleSeries.setData(buildCandleData(bars, selectedDate) as never);
    volumeSeries.setData(buildVolumeData(bars, selectedDate) as never);

    // --- 수동 선(수평선/추세선) ---
    priceLineRefsRef.current.forEach((pl) => candleSeries.removePriceLine(pl));
    priceLineRefsRef.current = [];
    Object.values(trendSeriesMapRef.current).forEach((s) => chart.removeSeries(s));
    trendSeriesMapRef.current = {};

    lines.forEach((line) => {
      if (line.line_type === "horizontal") {
        const pl = candleSeries.createPriceLine({
          price: line.price1, color: "#1565c0", lineWidth: 2, lineStyle: LineStyle.Dashed,
          axisLabelVisible: true, title: line.label || "",
        });
        priceLineRefsRef.current.push(pl);
      } else if (line.line_type === "trend" && firstBarTimeRef.current && lastBarTimeRef.current && line.time1 && line.time2 && line.price2 !== null) {
        const s = chart.addLineSeries({
          color: "#c62828", lineWidth: 1, lineStyle: LineStyle.Dashed,
          crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
          title: line.label || "추세선",
        });
        s.setData([
          { time: firstBarTimeRef.current as Time, value: trendPriceAt(line.time1, line.price1, line.time2, line.price2, firstBarTimeRef.current) },
          { time: lastBarTimeRef.current as Time, value: trendPriceAt(line.time1, line.price1, line.time2, line.price2, lastBarTimeRef.current) },
        ]);
        trendSeriesMapRef.current[line.id] = s;
      }
    });

    // --- EMA ---
    Object.keys(emaSeries).forEach((key) => {
      if (!emaSeriesMapRef.current[key]) {
        const cfg = emaSeries[key];
        emaSeriesMapRef.current[key] = chart.addLineSeries({
          color: cfg.color, lineWidth: 1, lineStyle: cfg.dashed ? LineStyle.Dashed : LineStyle.Solid,
          visible: false, crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
          title: key,
        });
      }
    });
    Object.keys(emaSeries).forEach((key) => {
      const cfg = emaSeries[key];
      const s = emaSeriesMapRef.current[key];
      s.applyOptions({ visible: !!cfg.visible });
      if (cfg.visible) {
        s.setData(cfg.data.map((d) => ({ time: d.time as Time, value: d.value })));
      }
    });

    // --- RSI 패널 ---
    const rsiVisible = !!rsiSeries.visible;
    rsiSeriesRef.current?.applyOptions({ visible: rsiVisible });
    rsi70SeriesRef.current?.applyOptions({ visible: rsiVisible });
    rsi30SeriesRef.current?.applyOptions({ visible: rsiVisible });
    if (rsiVisible) {
      rsiSeriesRef.current?.setData(rsiSeries.data.map((d) => ({ time: d.time as Time, value: d.value })));
      if (firstBarTimeRef.current && lastBarTimeRef.current) {
        rsi70SeriesRef.current?.setData([
          { time: firstBarTimeRef.current as Time, value: 70 },
          { time: lastBarTimeRef.current as Time, value: 70 },
        ]);
        rsi30SeriesRef.current?.setData([
          { time: firstBarTimeRef.current as Time, value: 30 },
          { time: lastBarTimeRef.current as Time, value: 30 },
        ]);
      }
    }

    // --- 다이버전스 마커/연결선 ---
    divLineSeriesRef.current.forEach((s) => chart.removeSeries(s));
    divLineSeriesRef.current = [];
    const priceMarkers: SeriesMarker<Time>[] = [];
    const rsiMarkers: SeriesMarker<Time>[] = [];

    divergenceMarkers.forEach((m) => {
      const color = divMarkerColors[m.type] || "#888888";
      const isBullish = m.type.indexOf("bullish") !== -1;

      const priceLine = chart.addLineSeries({
        color, lineWidth: 1, lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      });
      priceLine.setData([
        { time: m.prev_date as Time, value: m.prev_price },
        { time: m.structure_date as Time, value: m.price },
      ]);
      divLineSeriesRef.current.push(priceLine);

      if (rsiVisible) {
        const rsiLine = chart.addLineSeries({
          color, lineWidth: 1, lineStyle: LineStyle.Dashed, priceScaleId: "rsi",
          crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
        });
        rsiLine.setData([
          { time: m.prev_date as Time, value: m.prev_rsi },
          { time: m.structure_date as Time, value: m.rsi },
        ]);
        divLineSeriesRef.current.push(rsiLine);
      }

      const arrowShape = isBullish ? "arrowUp" : "arrowDown";
      const pricePos = isBullish ? "belowBar" : "aboveBar";
      priceMarkers.push({ time: m.prev_date as Time, position: pricePos, color, shape: arrowShape });
      priceMarkers.push({ time: m.structure_date as Time, position: pricePos, color, shape: arrowShape });
      if (rsiVisible) {
        rsiMarkers.push({ time: m.prev_date as Time, position: "inBar", color, shape: arrowShape });
        rsiMarkers.push({ time: m.structure_date as Time, position: "inBar", color, shape: arrowShape });
      }
      priceMarkers.push({ time: m.confirmed_date as Time, position: "inBar", color: "#000000", shape: "circle" });
    });

    priceMarkers.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
    rsiMarkers.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));

    divergencePriceMarkersRef.current = priceMarkers;
    applyCandleMarkers();
    rsiSeriesRef.current?.setMarkers(rsiMarkers);

    // 데이터 구성 자체가 바뀐 경우(최초 로드, 표시 기간 변경)에만 전체 보기로
    // 맞추고, 캔들 선택/EMA 토글만 바뀐 경우엔 절대 건드리지 않는다 - 줌 유지의 핵심.
    if (dataChanged) {
      chart.timeScale().fitContent();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, selectedDate, emaSeries, rsiSeries, divergenceMarkers, divMarkerColors, drawMode, lines]);

  return <div ref={containerRef} style={{ width: "100%" }} />;
}
