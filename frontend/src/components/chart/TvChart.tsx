import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type Logical,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { DivergenceMarker, DrawMode, ManualLine } from "../../types";
import type { Bar } from "./chartLogic";
import { ZonePrimitive } from "./ZonePrimitive";
import { PreviewPrimitive } from "./PreviewPrimitive";
import { TrendLinePrimitive } from "./TrendLinePrimitive";
import {
  buildCandleData, buildVolumeData, CORNER_CURSOR, cornerPoint, formatDateWithWeekday, HIT_TOLERANCE_PX,
  hitTestShapes, hitTestTrendHandle, hitTestZoneHandle, oppositeCorner, otherTrendHandle, sameTrend, sameZone,
  trendFromPoints, trendHandlePoints, trendPoint, trendVisibleGeom, ZONE_DRAG_MIN_PX, zoneFromCorners,
  zoneIsDegenerate, zoneRectPixels, type TrendHandle, type ZoneCorner, type ZoneGeom,
} from "./chartLogic";
import { createTimeAxis, makeBarIndex, type BarIndex, type TimeAxis } from "./timeAxis";

// 시간 <-> 화면 좌표 변환은 전부 이 함수가 만드는 TimeAxis로 한다(그리기 클릭, 미리보기, 존/추세선
// 렌더링, 핸들 드래그, 히트 테스트 공통). 차트의 timeScale을 그때그때 읽으므로 줌/스크롤을 따라간다.
function axisFor(chart: IChartApi, index: BarIndex): TimeAxis {
  return createTimeAxis(index, {
    logicalToCoordinate: (logical) => chart.timeScale().logicalToCoordinate(logical as Logical),
    coordinateToLogical: (x) => chart.timeScale().coordinateToLogical(x),
  });
}

// 처음 열 때/표시 기간을 바꿀 때 마지막 캔들 오른쪽에 이 만큼(봉 수)의 빈 공간을 둔다.
// fitContent()가 [첫 봉, 마지막 봉 + rightOffset] 범위로 맞춘다.
const RIGHT_OFFSET_BARS = 25;

// 클릭과 드래그를 구분하는 이동 거리(px) - 이 이상 움직이고 놓은 건 클릭으로 처리하지 않는다.
const DRAG_THRESHOLD_PX = 5;
const TOOLBAR_WIDTH_PX = 40;
const TOOLBAR_HEIGHT_PX = 34;

interface Selection {
  id: number;
  x: number;       // 툴바 기준점(차트 영역 안 화면 좌표)
  y: number;
  width: number;   // 선택 시점의 차트 폭 - 툴바가 화면 밖으로 안 나가게 자르는 데 쓴다
}

// 선택한 도형의 핸들 드래그 상태 - 존(꼭지점 4개)과 추세선(끝점 2개) 공통. fixed는 반대편(고정) 점,
// moving은 마우스를 따라가는 점이다. 존/추세선의 모양은 구조가 같아서(time1/price1/time2/price2) ZoneGeom 하나로
// 다룬다(존: price1=상단/price2=하단, 추세선: price1/price2 = 1번/2번 점의 가격).
type ShapeKind = "zone" | "trend";
type DragHandle = ZoneCorner | TrendHandle;

interface ShapeDragState {
  kind: ShapeKind;
  id: number;
  handle: DragHandle;
  original: ZoneGeom;
  fixed: { time: string; price: number };
  moving: { time: string; price: number };
  startX: number;
  startY: number;
  pointerId: number;
}

// 드래그 중(또는 저장 후 새 데이터가 도착하기 전)에 화면에 보여주는 임시 모양.
// 렌더 effect가 프리미티브를 다시 만들어도 이 값으로 다시 덮어써서 깜빡임이 없게 한다.
interface ShapeOverride {
  kind: ShapeKind;
  id: number;
  geom: ZoneGeom;
  saved: boolean;                    // 서버 저장 성공 여부
  linesAtSave: ManualLine[] | null;  // 저장 성공 시점의 lines - 이후 lines가 바뀌면(새 데이터 도착) 임시 모양을 버린다
}

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
  onAddZone: (time1: string, price1: number, time2: string, price2: number) => void;
  onFinishDrawing: () => void;           // 도형 확정/Esc 취소 시 기본 모드로 복귀
  onDeleteLine: (lineId: number) => void; // 선택한 도형 삭제(서버 삭제 + 화면 갱신은 부모가 한다)
  // 존 꼭지점 드래그 저장(PUT) - 저장 후 화면 갱신은 부모가 한다. 실패하면 reject(TvChart가 원복 + 에러 표시).
  onUpdateZone: (lineId: number, time1: string, price1: number, time2: string, price2: number) => Promise<void>;
  // 추세선 끝점 드래그 저장(PUT) - 존과 같은 방식. time1 <= time2로 정규화된 값이 온다.
  onUpdateTrend: (lineId: number, time1: string, price1: number, time2: string, price2: number) => Promise<void>;
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
  divMarkerColors, drawMode, lines, onSelectDate, onAddHorizontalLine, onAddTrendLine, onAddZone,
  onFinishDrawing, onDeleteLine, onUpdateZone, onUpdateTrend,
}: TvChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const selectedLineId = selection?.id ?? null;
  const previewRef = useRef<PreviewPrimitive | null>(null);
  const linesRef = useRef<ManualLine[]>(lines);
  const selectionRef = useRef<Selection | null>(null);
  const [dragging, setDragging] = useState(false);          // 존 꼭지점 드래그 중(툴바 숨김)
  const [dragError, setDragError] = useState<string | null>(null);
  const zonePrimitiveByIdRef = useRef<Map<number, ZonePrimitive>>(new Map());
  const trendPrimitiveByIdRef = useRef<Map<number, TrendLinePrimitive>>(new Map());
  const shapeOverrideRef = useRef<ShapeOverride | null>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi70SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi30SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const emaSeriesMapRef = useRef<Record<string, ISeriesApi<"Line">>>({});
  const divLineSeriesRef = useRef<ISeriesApi<"Line">[]>([]);
  const divergencePriceMarkersRef = useRef<SeriesMarker<Time>[]>([]);
  const lastBarTimesRef = useRef<string | null>(null);
  const currentDrawModeRef = useRef<DrawMode>("select");
  const pendingTrendPointRef = useRef<{ time: string; price: number } | null>(null);
  const priceLineRefsRef = useRef<IPriceLine[]>([]);
  const zonePrimitivesRef = useRef<ZonePrimitive[]>([]);
  const pendingZonePointRef = useRef<{ time: string; price: number } | null>(null);
  const trendPrimitivesRef = useRef<TrendLinePrimitive[]>([]);
  const barIndexRef = useRef<BarIndex>(makeBarIndex([]));
  const firstBarTimeRef = useRef<string | null>(null);
  const lastBarTimeRef = useRef<string | null>(null);

  // 클릭 핸들러(subscribeClick)는 최초 마운트 시 한 번만 등록하는데, 그 안에서
  // 항상 "최신" 콜백/드로우모드를 참조해야 하므로 ref에 담아 매 렌더마다 갱신한다.
  const callbacksRef = useRef({
    onSelectDate, onAddHorizontalLine, onAddTrendLine, onAddZone, onFinishDrawing, onUpdateZone, onUpdateTrend,
  });
  useEffect(() => {
    callbacksRef.current = {
      onSelectDate, onAddHorizontalLine, onAddTrendLine, onAddZone, onFinishDrawing, onUpdateZone, onUpdateTrend,
    };
  }, [onSelectDate, onAddHorizontalLine, onAddTrendLine, onAddZone, onFinishDrawing, onUpdateZone, onUpdateTrend]);

  // 이벤트 핸들러(최초 마운트 때 한 번만 등록)가 최신 선택 상태를 읽도록 매 렌더 뒤에 동기화한다.
  useEffect(() => {
    selectionRef.current = selection;
  });

  // 드래그/저장 에러 메시지는 잠시 뒤 저절로 사라진다.
  useEffect(() => {
    if (!dragError) return;
    const timer = setTimeout(() => setDragError(null), 6000);
    return () => clearTimeout(timer);
  }, [dragError]);

  function applyCandleMarkers() {
    const markers = divergencePriceMarkersRef.current.slice();
    markers.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
    candleSeriesRef.current?.setMarkers(markers);
  }

  // 미리보기(고무줄)의 도형 종류/첫 점을 현재 그리기 상태에 맞춘다.
  function syncPreview() {
    const mode = currentDrawModeRef.current;
    const first = mode === "trend" ? pendingTrendPointRef.current : mode === "zone" ? pendingZonePointRef.current : null;
    previewRef.current?.setState(mode, first);
  }

  // 진행 중이던 그리기 상태(첫 점, 미리보기)를 전부 지운다. 첫 점 표시(주황 점)는 미리보기
  // 프리미티브가 그리므로 clear() 한 번이면 같이 사라진다.
  function clearPendingDrawing() {
    pendingTrendPointRef.current = null;
    pendingZonePointRef.current = null;
    previewRef.current?.clear();
  }

  // 도형을 확정(또는 Esc 취소)했을 때: 진행 상태를 지우고 기본 모드로 복귀시킨다.
  // 연속 그리기는 하지 않는다 - 다시 그리려면 그리기 버튼을 다시 눌러야 한다.
  function finishDrawing() {
    clearPendingDrawing();
    currentDrawModeRef.current = "select";
    callbacksRef.current.onFinishDrawing();
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
      timeScale: { borderColor: "#cccccc", tickMarkFormatter: () => "", rightOffset: RIGHT_OFFSET_BARS },
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

    // 미리보기(고무줄) 프리미티브 - 그리는 중인 도형을 마우스를 따라 보여준다.
    const preview = new PreviewPrimitive();
    candleSeries.attachPrimitive(preview);
    previewRef.current = preview;

    // 클릭 판정에 쓰는 좌표 변환(수평선/추세선/존 히트 테스트용).
    const hitCoords = () => {
      const axis = axisFor(chart, barIndexRef.current);
      return {
        priceToY: (price: number) => candleSeries.priceToCoordinate(price),
        dateToX: axis.dateToX,
        firstTime: axis.firstDate,
      };
    };

    // 차트 영역(캔들/빈 공간) 안인지 - 가격축/시간축 위 클릭과 구분한다.
    const inPane = (x: number, y: number) =>
      x >= 0 && y >= 0 && x <= chart.timeScale().width() && y <= container.clientHeight - chart.timeScale().height();

    // 드래그(이동/스크롤) 후 마우스를 놓은 걸 클릭으로 처리하지 않기 위한 추적.
    // capture 단계로 받아서 lightweight-charts 내부 처리와 무관하게 동작한다.
    let pointerStart: { x: number; y: number } | null = null;
    let dragged = false;

    // --- 도형 핸들 드래그 (선택된 존의 꼭지점 / 추세선의 끝점을 끌어 모양 수정) ---
    let shapeDrag: ShapeDragState | null = null;
    let saving = false;
    let hoverCursor: string | null = null;

    function containerPoint(e: PointerEvent) {
      const rect = container!.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    const handleCursor = (kind: ShapeKind, handle: DragHandle) =>
      kind === "zone" ? CORNER_CURSOR[handle as ZoneCorner] : "move";

    // 지금 선택된 존/추세선의 모양(저장 대기 중이면 임시 모양 기준). 같은 날 추세선은 화면에서 price1 높이의
    // 수평 선분이라 편집 대상 모양도 price2 = price1로 본다.
    function selectedShape(): { kind: ShapeKind; id: number; geom: ZoneGeom } | null {
      const sel = selectionRef.current;
      const line = sel
        ? linesRef.current.find((l) => l.id === sel.id && (l.line_type === "zone" || l.line_type === "trend"))
        : undefined;
      if (!line || !line.time1 || !line.time2 || line.price2 === null) return null;
      const kind: ShapeKind = line.line_type === "zone" ? "zone" : "trend";
      const ov = shapeOverrideRef.current;
      if (ov && ov.id === line.id) return { kind, id: line.id, geom: ov.geom };
      const raw = { time1: line.time1, time2: line.time2, price1: line.price1, price2: line.price2 };
      return { kind, id: line.id, geom: kind === "trend" ? trendVisibleGeom(raw) : raw };
    }

    // 마우스 아래의 핸들(없으면 null)
    function handleAt(e: PointerEvent) {
      if (currentDrawModeRef.current !== "select") return null;
      const shape = selectedShape();
      if (!shape) return null;
      const coords = hitCoords();
      const p = containerPoint(e);
      if (shape.kind === "zone") {
        const rect = zoneRectPixels(shape.geom, coords);
        const handle = rect ? hitTestZoneHandle(p, rect) : null;
        return handle ? { ...shape, handle } : null;
      }
      const pts = trendHandlePoints(shape.geom, coords.dateToX, coords.priceToY);
      const handle = pts ? hitTestTrendHandle(p, pts) : null;
      return handle ? { ...shape, handle } : null;
    }

    function setShapeOverride(kind: ShapeKind, id: number, geom: ZoneGeom | null) {
      if (kind === "zone") zonePrimitiveByIdRef.current.get(id)?.setOverride(geom);
      else trendPrimitiveByIdRef.current.get(id)?.setOverride(geom);
    }

    // 고정점과 움직이는 점으로 새 모양을 만든다. 존은 반대편을 넘어가도 상단>하단/시작<끝으로 정규화하고,
    // 추세선은 두 점을 time1 <= time2 순서로 정규화한다(순서가 뒤바뀌면 가격도 점과 함께 바뀐다).
    function geomFromDrag(d: ShapeDragState): ZoneGeom {
      if (d.kind === "zone") return zoneFromCorners(d.fixed, d.moving);
      return d.handle === "p1" ? trendFromPoints(d.moving, d.fixed) : trendFromPoints(d.fixed, d.moving);
    }

    function onShapeDragMove(e: PointerEvent) {
      const d = shapeDrag;
      if (!d) return;
      const p = containerPoint(e);
      // 시간은 캔들에 맞춘다(데이터 이전이라 못 구하면 직전 값 유지), 가격은 마우스 위치의 가격.
      const t = axisFor(chart, barIndexRef.current).xToDate(p.x); // 미래(빈 공간)도 변환된다
      if (t !== null) d.moving.time = t;
      const price = candleSeries.coordinateToPrice(p.y);
      if (price !== null) d.moving.price = price;
      const geom = geomFromDrag(d);
      shapeOverrideRef.current = { kind: d.kind, id: d.id, geom, saved: false, linesAtSave: null };
      setShapeOverride(d.kind, d.id, geom);
    }

    // 드래그를 끝낼 때(성공/취소 모두) 차트 스크롤/줌, 리스너, 포인터 캡처를 반드시 복구한다.
    function endShapeDrag() {
      const d = shapeDrag;
      shapeDrag = null;
      window.removeEventListener("pointermove", onShapeDragMove, true);
      window.removeEventListener("pointerup", onShapeDragUp, true);
      window.removeEventListener("pointercancel", cancelShapeDrag, true);
      window.removeEventListener("blur", cancelShapeDrag);
      try {
        chart.applyOptions({ handleScroll: true, handleScale: true });
      } catch {
        // 차트가 이미 제거된 경우
      }
      if (d) {
        try {
          container!.releasePointerCapture(d.pointerId);
        } catch {
          // 이미 해제됨
        }
      }
      hoverCursor = null;
      container!.style.cursor = "default";
      setDragging(false);
    }

    // Esc/창 포커스 상실/리사이즈/언마운트: 드래그를 취소하고 원래 모양으로 복귀한다.
    function cancelShapeDrag() {
      const d = shapeDrag;
      if (!d) return;
      endShapeDrag();
      shapeOverrideRef.current = null;
      setShapeOverride(d.kind, d.id, null);
      dragged = true; // 드래그 끝의 클릭이 선택 해제 등으로 처리되지 않게
    }

    function onShapeDragUp(e: PointerEvent) {
      const d = shapeDrag;
      if (!d) return;
      const p = containerPoint(e);
      const movedPx = Math.hypot(e.clientX - d.startX, e.clientY - d.startY);
      const geom = geomFromDrag(d);
      endShapeDrag();
      dragged = true;

      const revert = () => {
        shapeOverrideRef.current = null;
        setShapeOverride(d.kind, d.id, null);
      };
      // 살짝 클릭만 한 것(3px 이하)이나 모양이 그대로인 건 수정으로 치지 않는다.
      const unchanged = d.kind === "zone" ? sameZone(geom, d.original) : sameTrend(geom, d.original);
      if (movedPx <= ZONE_DRAG_MIN_PX || unchanged) {
        revert();
        return;
      }
      // 존은 폭/높이가 0이면 저장할 수 없다. 추세선은 같은 날(수평 선분)도 POST와 같이 허용한다.
      if (d.kind === "zone" && zoneIsDegenerate(geom)) {
        revert();
        setDragError("존의 폭이나 높이가 0이 되어 수정할 수 없습니다.");
        return;
      }

      // 툴바 기준점을 새 모양 위로 옮긴다(존: 위쪽 변, 추세선: 끌고 있던 점).
      const anchorY = candleSeries.priceToCoordinate(d.kind === "zone" ? geom.price1 : d.moving.price);
      setSelection({
        id: d.id, x: Math.max(0, Math.min(p.x, container!.clientWidth)), y: anchorY ?? p.y,
        width: container!.clientWidth,
      });

      // 저장 중에도 새 모양을 유지하고, 실패하면 원래 모양으로 되돌리고 에러를 보여준다.
      saving = true;
      shapeOverrideRef.current = { kind: d.kind, id: d.id, geom, saved: false, linesAtSave: null };
      setShapeOverride(d.kind, d.id, geom);
      const update = d.kind === "zone" ? callbacksRef.current.onUpdateZone : callbacksRef.current.onUpdateTrend;
      update(d.id, geom.time1, geom.price1, geom.time2, geom.price2).then(
        () => {
          saving = false;
          const ov = shapeOverrideRef.current;
          if (ov && ov.id === d.id) {
            ov.saved = true;
            ov.linesAtSave = linesRef.current; // 이후 lines가 바뀌면(새 데이터 도착) 렌더 effect가 임시 모양을 버린다
          }
        },
        (err: unknown) => {
          saving = false;
          revert();
          setDragError(err instanceof Error ? err.message : String(err));
        },
      );
    }

    function startShapeDrag(
      e: PointerEvent, kind: ShapeKind, id: number, geom: ZoneGeom, handle: DragHandle,
    ) {
      e.preventDefault();  // 차트 내부의 스크롤 시작(mousedown 호환 이벤트)을 막는다
      e.stopPropagation();
      try {
        container!.setPointerCapture(e.pointerId); // 차트 밖에서 놓아도 pointerup을 받는다
      } catch {
        // 캡처에 실패해도 window 리스너로 진행한다
      }
      chart.applyOptions({ handleScroll: false, handleScale: false }); // 드래그 중에는 스크롤/줌 끔
      shapeDrag = {
        kind, id, handle, original: geom,
        fixed: kind === "zone"
          ? cornerPoint(geom, oppositeCorner(handle as ZoneCorner))
          : trendPoint(geom, otherTrendHandle(handle as TrendHandle)),
        moving: kind === "zone" ? cornerPoint(geom, handle as ZoneCorner) : trendPoint(geom, handle as TrendHandle),
        startX: e.clientX, startY: e.clientY, pointerId: e.pointerId,
      };
      shapeOverrideRef.current = { kind, id, geom, saved: false, linesAtSave: null };
      setDragging(true);
      setDragError(null);
      container!.style.cursor = handleCursor(kind, handle);
      window.addEventListener("pointermove", onShapeDragMove, true);
      window.addEventListener("pointerup", onShapeDragUp, true);
      window.addEventListener("pointercancel", cancelShapeDrag, true);
      window.addEventListener("blur", cancelShapeDrag);
    }

    const onPointerDown = (e: PointerEvent) => {
      setDragError(null);
      if (e.button === 0 && !shapeDrag && !saving) {
        const hit = handleAt(e);
        if (hit) {
          startShapeDrag(e, hit.kind, hit.id, hit.geom, hit.handle);
          return;
        }
      }
      pointerStart = { x: e.clientX, y: e.clientY };
      dragged = false;
    };
    // 미리보기용 마우스 위치 - lightweight-charts 크로스헤어 이벤트(빈 공간에서 발화 여부 불확실)
    // 대신 DOM pointermove를 컨테이너 기준(getBoundingClientRect)으로 보정해서 쓴다.
    const updatePreviewMouse = (e: PointerEvent) => {
      const p = containerPoint(e);
      previewRef.current?.setMouse(inPane(p.x, p.y) ? p : null);
    };
    const onPointerLeave = () => previewRef.current?.setMouse(null);

    const onPointerMove = (e: PointerEvent) => {
      updatePreviewMouse(e);
      if (!pointerStart && !shapeDrag) {
        // 핸들 위에서는 커서를 바꾼다(존 꼭지점: 크기 조절, 추세선 끝점: 이동).
        const hit = saving ? null : handleAt(e);
        hoverCursor = hit ? handleCursor(hit.kind, hit.handle) : null;
        if (hit) container.style.cursor = hoverCursor!;
      }
      if (!pointerStart || dragged) return;
      if (Math.hypot(e.clientX - pointerStart.x, e.clientY - pointerStart.y) > DRAG_THRESHOLD_PX) {
        dragged = true;
        setSelection(null); // 차트를 끌어 옮기면 툴바 위치가 어긋나므로 선택 해제
      }
    };
    const onPointerEnd = () => {
      pointerStart = null;
    };
    const onWheel = () => {
      if (!shapeDrag) setSelection(null); // 줌하면 도형 좌표가 바뀌므로 선택 해제
    };
    container.addEventListener("pointerdown", onPointerDown, true);
    container.addEventListener("pointermove", onPointerMove, true);
    container.addEventListener("pointerleave", onPointerLeave, true);
    container.addEventListener("pointerup", onPointerEnd, true);
    container.addEventListener("pointercancel", onPointerEnd, true);
    container.addEventListener("wheel", onWheel, true);

    // Esc: 진행 중이던 그리기를 취소하고 기본 모드로 돌아가며, 선택도 해제한다.
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (shapeDrag) {
        cancelShapeDrag(); // 존 꼭지점/추세선 끝점 드래그 취소 -> 원래 모양으로 복귀(선택은 유지)
        return;
      }
      setSelection(null);
      if (currentDrawModeRef.current !== "select" || pendingTrendPointRef.current || pendingZonePointRef.current) {
        finishDrawing();
      }
    };
    window.addEventListener("keydown", onKeyDown);

    // 캔들의 시간축 칸 아무 곳을 클릭해도 그 캔들의 time을 준다(lightweight-charts
    // 기본 동작). 그리기 모드일 때는 같은 클릭을 신호패널용 "선택"이 아니라
    // 선 추가용 좌표로 쓴다. 기본(select) 모드에서는 새 선이 절대 생기지 않는다.
    chart.subscribeClick((param: MouseEventParams) => {
      if (!param || dragged) return;
      const mode = currentDrawModeRef.current;
      const {
        onSelectDate: select, onAddHorizontalLine: addH, onAddTrendLine: addT, onAddZone: addZ,
      } = callbacksRef.current;

      if (mode === "select") {
        // 이미 그려진 도형을 먼저 판정한다(겹치면 가장 가까운 하나). 맞으면 도형 선택 +
        // 삭제 툴바, 아니면 선택 해제 후 기존처럼 캔들 선택.
        if (param.point) {
          const hit = hitTestShapes(linesRef.current, param.point, hitCoords(), HIT_TOLERANCE_PX);
          if (hit) {
            setSelection({ id: hit.id, x: hit.anchor.x, y: hit.anchor.y, width: container.clientWidth });
            return;
          }
        }
        setSelection(null);
        if (param.time) select(param.time as string);
        return;
      }

      // 그리기 모드: param.time은 캔들이 없는 빈 공간에서 undefined라서 쓰지 않고, 화면 좌표로
      // 가격/날짜를 구한다. 가격은 빈 공간에서도 되고, 날짜는 timeAxis가 캔들 구간(그 캔들의 날짜)과
      // 미래(마지막 캔들 날짜 + N일)를 모두 변환한다.
      const point = param.point;
      if (!point || !inPane(point.x, point.y)) return;
      const price = candleSeries.coordinateToPrice(point.y);
      if (price === null || price === undefined) return;
      setSelection(null);

      if (mode === "horizontal") {
        addH(price); // 날짜가 필요 없어서 빈 공간 클릭도 가격만으로 확정
        finishDrawing();
        return;
      }

      const date = axisFor(chart, barIndexRef.current).xToDate(point.x);
      if (date === null) return; // 첫 캔들 이전(데이터 이전)은 무시

      if (mode === "zone") {
        // 추세선처럼 클릭 두 번 - 대각선 두 모서리. 두 번째 클릭 때 시간/가격의 앞뒤를
        // 정규화해서(시작<끝, 상단>하단) 넘긴다. 폭/높이가 0이면 버린다(그리기 모드는 유지).
        const p1 = pendingZonePointRef.current;
        if (!p1) {
          pendingZonePointRef.current = { time: date, price };
          syncPreview();
        } else {
          const t2 = date;
          if (t2 !== p1.time && price !== p1.price) {
            addZ(
              p1.time < t2 ? p1.time : t2, Math.max(p1.price, price),
              p1.time < t2 ? t2 : p1.time, Math.min(p1.price, price),
            );
            finishDrawing();
          } else {
            clearPendingDrawing();
            syncPreview();
          }
        }
        return;
      }

      if (mode === "trend") {
        if (!pendingTrendPointRef.current) {
          pendingTrendPointRef.current = { time: date, price };
          syncPreview();
        } else {
          const p1 = pendingTrendPointRef.current;
          // 클릭 순서와 상관없이 time1 <= time2로 정규화해서 저장한다(오른쪽 점을 먼저 찍어도 같은 선)
          const t = trendFromPoints(p1, { time: date, price });
          addT(t.time1, t.price1, t.time2, t.price2);
          finishDrawing();
        }
      }
    });

    chart.subscribeCrosshairMove((param: MouseEventParams) => {
      const mode = currentDrawModeRef.current;
      container.style.cursor = shapeDrag
        ? handleCursor(shapeDrag.kind, shapeDrag.handle)
        : hoverCursor ? hoverCursor
          : mode !== "select" ? "crosshair" : param && param.time ? "pointer" : "default";
    });

    const handleResize = () => {
      chart.applyOptions({ width: container.clientWidth });
      cancelShapeDrag();
      setSelection(null); // 리사이즈하면 툴바 위치가 어긋나므로 선택 해제
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("keydown", onKeyDown);
      container.removeEventListener("pointerdown", onPointerDown, true);
      container.removeEventListener("pointermove", onPointerMove, true);
      container.removeEventListener("pointerleave", onPointerLeave, true);
      container.removeEventListener("pointerup", onPointerEnd, true);
      container.removeEventListener("pointercancel", onPointerEnd, true);
      container.removeEventListener("wheel", onWheel, true);
      cancelShapeDrag(); // 드래그 중 언마운트되면 스크롤/줌 복구 + 리스너 제거
      shapeOverrideRef.current = null;
      zonePrimitiveByIdRef.current = new Map();
      trendPrimitiveByIdRef.current = new Map();
      previewRef.current?.clear(); // 미리보기 잔상 제거(StrictMode 재마운트 포함)
      previewRef.current = null;
      chart.remove();
      chartRef.current = null;
      // 지워진 차트에 속한 시리즈 참조가 남으면 StrictMode 재마운트 때 새 차트에
      // EMA/추세선이 안 만들어진다.
      emaSeriesMapRef.current = {};
      priceLineRefsRef.current = [];
      zonePrimitivesRef.current = [];
      trendPrimitivesRef.current = [];
      pendingZonePointRef.current = null;
      pendingTrendPointRef.current = null;
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

    // 그리기 모드가 바뀌면 대기 중이던 임시 상태(첫 점, 마커, 미리보기)를 정리하고
    // 새 모드에 맞는 미리보기 상태로 맞춘다.
    if (drawMode !== currentDrawModeRef.current) {
      clearPendingDrawing();
      currentDrawModeRef.current = drawMode;
      syncPreview();
    }
    currentDrawModeRef.current = drawMode;
    linesRef.current = lines;

    // 표시 중인 캔들이 바뀌면 시간 변환(날짜 <-> 논리 인덱스)도 같이 갱신한다.
    barIndexRef.current = makeBarIndex(bars.map((b) => b.time));
    const axis = axisFor(chart, barIndexRef.current);
    previewRef.current?.setAxis(axis);

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
    // 추세선은 프리미티브(미래 날짜도 정확한 위치) - 매번 떼고 다시 붙인다
    trendPrimitivesRef.current.forEach((p) => candleSeries.detachPrimitive(p));
    trendPrimitivesRef.current = [];
    trendPrimitiveByIdRef.current = new Map();

    lines.forEach((line) => {
      if (line.line_type === "horizontal") {
        const isSelected = line.id === selectedLineId;
        const pl = candleSeries.createPriceLine({
          price: line.price1, color: isSelected ? "#0d47a1" : "#1565c0", lineWidth: isSelected ? 4 : 2,
          lineStyle: isSelected ? LineStyle.Solid : LineStyle.Dashed,
          axisLabelVisible: true, title: line.label || "",
        });
        priceLineRefsRef.current.push(pl);
      } else if (line.line_type === "trend" && line.time1 && line.time2 && line.price2 !== null) {
        const trend = new TrendLinePrimitive(
          {
            time1: line.time1, price1: line.price1, time2: line.time2, price2: line.price2,
            selected: line.id === selectedLineId,
          },
          axis,
        );
        candleSeries.attachPrimitive(trend);
        trendPrimitivesRef.current.push(trend);
        trendPrimitiveByIdRef.current.set(line.id, trend);
      }
    });

    // --- 존(직사각형) - 시리즈 프리미티브. 매번 떼고 다시 붙인다(마지막 종가가 바뀌면 색도 바뀜) ---
    zonePrimitivesRef.current.forEach((p) => candleSeries.detachPrimitive(p));
    zonePrimitivesRef.current = [];
    zonePrimitiveByIdRef.current = new Map();
    const lastClose = bars.length > 0 ? bars[bars.length - 1].close : null;
    lines.forEach((line) => {
      if (line.line_type !== "zone" || !line.time1 || !line.time2 || line.price2 === null) return;
      const zone = new ZonePrimitive(
        { time1: line.time1, time2: line.time2, top: line.price1, bottom: line.price2, selected: line.id === selectedLineId },
        { axis, lastClose },
      );
      candleSeries.attachPrimitive(zone);
      zonePrimitivesRef.current.push(zone);
      zonePrimitiveByIdRef.current.set(line.id, zone);
    });
    // 핸들 드래그 중/저장 직후의 임시 모양(존, 추세선 공통): 새 데이터가 도착하기 전에는 새 프리미티브에도
    // 다시 입히고, 저장된 새 데이터가 도착했으면(lines가 바뀜) 버린다.
    const shapeOverride = shapeOverrideRef.current;
    if (shapeOverride) {
      if (shapeOverride.saved && shapeOverride.linesAtSave !== null && lines !== shapeOverride.linesAtSave) {
        shapeOverrideRef.current = null;
      } else if (shapeOverride.kind === "zone") {
        zonePrimitiveByIdRef.current.get(shapeOverride.id)?.setOverride(shapeOverride.geom);
      } else {
        trendPrimitiveByIdRef.current.get(shapeOverride.id)?.setOverride(shapeOverride.geom);
      }
    }

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
  }, [bars, selectedDate, emaSeries, rsiSeries, divergenceMarkers, divMarkerColors, drawMode, lines, selectedLineId]);

  // 선택된 도형 위에 뜨는 작은 툴바(지금은 삭제 버튼 하나). 도형 위쪽에 두되 위로 공간이
  // 없으면 아래로, 좌우로는 차트 영역 안에 자른다.
  const toolbarShape = selection ? lines.find((l) => l.id === selection.id) : null;
  const toolbarLeft = selection
    ? Math.max(4, Math.min(selection.x - TOOLBAR_WIDTH_PX / 2, selection.width - TOOLBAR_WIDTH_PX - 4))
    : 0;
  const toolbarTop = selection
    ? selection.y - TOOLBAR_HEIGHT_PX - 8 < 4 ? selection.y + 10 : selection.y - TOOLBAR_HEIGHT_PX - 8
    : 0;

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <div ref={containerRef} style={{ width: "100%" }} />
      {selection && toolbarShape && !dragging && (
        <div
          role="toolbar"
          aria-label="도형 도구"
          style={{
            position: "absolute", left: toolbarLeft, top: toolbarTop, width: TOOLBAR_WIDTH_PX, height: TOOLBAR_HEIGHT_PX,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "#ffffff", border: "1px solid #b0b0b0", borderRadius: 6,
            boxShadow: "0 2px 6px rgba(0,0,0,0.2)", zIndex: 10,
          }}
        >
          <button
            type="button"
            title="삭제"
            aria-label="선택한 도형 삭제"
            style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 18, lineHeight: 1 }}
            onClick={() => {
              onDeleteLine(selection.id);
              setSelection(null);
            }}
          >
            🗑
          </button>
        </div>
      )}
      {dragError && (
        <div
          role="alert"
          style={{
            position: "absolute", left: 8, top: 8, zIndex: 11, padding: "6px 10px", fontSize: 13,
            background: "#fdecea", color: "#b71c1c", border: "1px solid #f5c6cb", borderRadius: 6,
          }}
        >
          {dragError}
        </div>
      )}
    </div>
  );
}
