import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  addHorizontalLine, addTrendLine, addZone, deleteLine, getDashboard, updateTrend, updateZone,
} from "../api/dashboard";
import { getMarketState } from "../api/marketState";
import NumberInput from "../components/NumberInput";
import type { EmaSeriesConfig } from "../components/chart/TvChart";
import { THEME } from "../components/chart/chartTheme";
import AppTopBar from "../components/AppTopBar";
import ChartArea from "../components/ChartArea";
import type { LegendToggle } from "../components/ChartLegend";
import LineManager from "../components/LineManager";
import PeriodBar from "../components/PeriodBar";
import SignalPanel from "../components/SignalPanel";
import ToolRail from "../components/ToolRail";
import type { DashboardResponse, DrawMode, MarketStateBlock, MarketStateResponse } from "../types";
import styles from "./SignalScanner.module.css";

const WINDOW_OPTIONS: Record<string, number | null> = {
  "최근 3개월": 90, "최근 6개월": 180, "최근 1년": 365, "전체": null,
};
const DEFAULT_WINDOW = "최근 6개월";

const EMA_STYLE: Record<string, { label: string; color: string; dashed: boolean }> = {
  ema9: { label: "EMA9", color: THEME.ema9, dashed: false },
  ema20: { label: "EMA20", color: THEME.ema20, dashed: false },
  ema50: { label: "EMA50", color: THEME.ema50, dashed: false },
  ema200: { label: "EMA200", color: THEME.ema200, dashed: true },
};

// 기간 바의 짧은 글자 (접근성 이름은 WINDOW_OPTIONS의 키 그대로)
const WINDOW_SHORT: Record<string, string> = { "최근 3개월": "3M", "최근 6개월": "6M", "최근 1년": "1Y", "전체": "전체" };

// 시장 상태(횡보/추세) 기본 파라미터 - 서버 market_state.py의 DEFAULT_N/K와 같은 임시값.
// 입력칸에서 바꾸면 바로 서버에 다시 계산을 요청한다(음영/패널이 같이 갱신).
const DEFAULT_MS_N = 10;
const DEFAULT_MS_K = 4;
const MS_DEBOUNCE_MS = 200;
const NO_BLOCKS: MarketStateBlock[] = []; // 토글 OFF일 때 넘기는 빈 배열(참조 고정 - 불필요한 재렌더 방지)

const DIV_MARKER_COLOR: Record<string, string> = {
  regular_bullish: THEME.divergenceUp,
  regular_bearish: THEME.divergenceDown,
};

export default function SignalScanner({ nav }: { nav: ReactNode }) {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [windowLabel, setWindowLabel] = useState(DEFAULT_WINDOW);
  const [drawMode, setDrawMode] = useState<DrawMode>("select");
  const [showEma, setShowEma] = useState<Record<string, boolean>>({
    ema9: false, ema20: false, ema50: false, ema200: false,
  });
  const [showRsi, setShowRsi] = useState(false);
  const [showDivergence, setShowDivergence] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // 시장 상태 - 신호가 아니라 차트 배경 음영 전용(횡보 구간 표시).
  // 실험 단계라 기본 OFF: 판정이 실제 차트와 잘 안 맞아 보류 중이다(코드는 그대로 둠).
  // OFF면 서버 요청도, 차트 음영도, 신호 패널의 상태 박스도, N/K 입력칸도 없다.
  const [showMarketState, setShowMarketState] = useState(false);
  const [msN, setMsN] = useState(DEFAULT_MS_N);
  const [msK, setMsK] = useState(DEFAULT_MS_K);
  const [marketState, setMarketState] = useState<MarketStateResponse | null>(null);
  const [msError, setMsError] = useState<string | null>(null);
  const msParamsValid = Number.isInteger(msN) && Number.isInteger(msK) && msN >= 1 && msK >= 0 && msK <= msN;

  const loadDashboard = (refresh = false) => {
    setLoading(true);
    getDashboard(refresh)
      .then((res) => {
        setData(res);
        setError(null);
        setSelectedDate((prev) => prev ?? res.candles[res.candles.length - 1]?.date ?? null);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDashboard(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // N/K가 바뀌거나 데이터가 새로 갱신되면(마지막 캔들 날짜가 바뀜) 서버에 다시 계산을 요청한다.
  // 타이핑마다 요청이 나가지 않게 짧게 디바운스하고, 늦게 도착한 옛 응답은 버린다.
  const lastDate = data?.date_range.max ?? null;
  // 이미 받은 결과가 지금 N/K와 마지막 캔들 날짜에 맞으면(토글을 껐다 다시 켠 경우 등) 재사용한다.
  const marketStateUpToDate =
    marketState !== null &&
    marketState.params.n === msN &&
    marketState.params.k === msK &&
    marketState.candles[marketState.candles.length - 1]?.date === lastDate;
  useEffect(() => {
    // 토글 OFF면 요청하지 않는다(보류 중인 실험 기능).
    if (!showMarketState || lastDate === null || !msParamsValid || marketStateUpToDate) return;
    let stale = false;
    const timer = setTimeout(() => {
      getMarketState(msN, msK)
        .then((res) => {
          if (stale) return;
          setMarketState(res);
          setMsError(null);
        })
        .catch((err) => {
          if (!stale) setMsError(String(err));
        });
    }, MS_DEBOUNCE_MS);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [showMarketState, lastDate, msN, msK, msParamsValid, marketStateUpToDate]);

  const marketStateByDate = useMemo(
    () => new Map((marketState?.candles ?? []).map((row) => [row.date, row])),
    [marketState],
  );
  const marketStateBlocks = showMarketState && marketState ? marketState.blocks : NO_BLOCKS;

  const plotCandles = useMemo(() => {
    if (!data) return [];
    const days = WINDOW_OPTIONS[windowLabel];
    if (days === null) return data.candles;
    const maxDate = new Date(data.date_range.max);
    const cutoff = new Date(maxDate);
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return data.candles.filter((c) => c.date >= cutoffStr);
  }, [data, windowLabel]);

  const visibleDates = useMemo(() => new Set(plotCandles.map((c) => c.date)), [plotCandles]);

  const bars = useMemo(
    () => plotCandles.map((c) => ({ time: c.date, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume })),
    [plotCandles],
  );

  const emaSeriesConfig = useMemo(() => {
    const config: Record<string, EmaSeriesConfig> = {};
    for (const key of Object.keys(EMA_STYLE)) {
      const style = EMA_STYLE[key];
      config[style.label] = {
        color: style.color,
        dashed: style.dashed,
        visible: showEma[key],
        data: plotCandles
          .filter((c) => c[key as keyof typeof c] !== null)
          .map((c) => ({ time: c.date, value: c[key as keyof typeof c] as number })),
      };
    }
    return config;
  }, [plotCandles, showEma]);

  const rsiSeriesConfig = useMemo(
    () => ({
      visible: showRsi,
      data: plotCandles.filter((c) => c.rsi !== null).map((c) => ({ time: c.date, value: c.rsi as number })),
    }),
    [plotCandles, showRsi],
  );

  const visibleDivergenceMarkers = useMemo(() => {
    if (!data || !showDivergence) return [];
    return data.divergence_markers.filter(
      (m) => visibleDates.has(m.prev_date) && visibleDates.has(m.structure_date) && visibleDates.has(m.confirmed_date),
    );
  }, [data, showDivergence, visibleDates]);

  const selectedCandle = useMemo(
    () => data?.candles.find((c) => c.date === selectedDate) ?? null,
    [data, selectedDate],
  );
  const selectedSignals = useMemo(
    () => (selectedDate && data ? data.signals[selectedDate] ?? [] : []),
    [data, selectedDate],
  );

  const handleAddHorizontal = (price: number) => {
    addHorizontalLine(price).then(() => loadDashboard(false));
  };
  const handleAddTrend = (time1: string, price1: number, time2: string, price2: number) => {
    addTrendLine(time1, price1, time2, price2).then(() => loadDashboard(false));
  };
  const handleAddZone = (time1: string, price1: number, time2: string, price2: number) => {
    addZone(time1, price1, time2, price2).then(() => loadDashboard(false));
  };
  // 존 꼭지점 드래그 저장 - 실패하면 reject해서 TvChart가 원래 모양으로 되돌리고 에러를 보여준다.
  const handleUpdateZone = async (lineId: number, time1: string, price1: number, time2: string, price2: number) => {
    await updateZone(lineId, time1, price1, time2, price2);
    loadDashboard(false); // 화면(존 모양, 라벨)과 신호 목록 갱신
  };
  // 추세선 끝점 드래그 저장 - 존과 같은 방식(실패하면 reject해서 TvChart가 원복 + 에러 표시).
  const handleUpdateTrend = async (lineId: number, time1: string, price1: number, time2: string, price2: number) => {
    await updateTrend(lineId, time1, price1, time2, price2);
    loadDashboard(false); // 화면(선 모양, 라벨)과 신호 목록 갱신
  };
  const handleDeleteLine = (lineId: number) => {
    deleteLine(lineId).then(() => loadDashboard(false));
  };

  const refreshButton = (
    <button
      type="button"
      className={styles.refresh}
      onClick={() => loadDashboard(true)}
      disabled={loading}
      aria-label="데이터 새로고침"
      title={loading ? "새로고침 중..." : "데이터 새로고침"}
    >
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={loading ? styles.spin : undefined}>
        <path d="M16.5 10a6.5 6.5 0 1 1-2-4.7" /><polyline points="16.5 3 16.5 6.5 13 6.5" />
      </svg>
    </button>
  );
  const topBar = (
    <AppTopBar
      nav={nav}
      actions={refreshButton}
      left={
        <>
          <span className={styles.symbol}>BTCUSDT · 1D</span>
          {data && (
            <span className={styles.caption} title="마지막으로 마감된 캔들까지만 반영">
              데이터 범위: {data.date_range.min} ~ {data.date_range.max}
            </span>
          )}
        </>
      }
    />
  );

  if (loading && !data) return <div className={styles.page}>{topBar}<div className={styles.message}>불러오는 중...</div></div>;
  if (error && !data) return <div className={styles.page}>{topBar}<div className={styles.message}>오류: {error}</div></div>;
  if (!data) return null;

  const legendToggles: LegendToggle[] = [
    ...Object.keys(EMA_STYLE).map((key) => ({
      key, label: EMA_STYLE[key].label, color: EMA_STYLE[key].color, active: showEma[key],
      onToggle: () => setShowEma((prev) => ({ ...prev, [key]: !prev[key] })),
    })),
    { key: "rsi", label: "RSI", color: THEME.rsi, active: showRsi, onToggle: () => setShowRsi((v) => !v) },
    ...(data.divergence_markers.length > 0
      ? [{ key: "div", label: "다이버전스", color: THEME.divergenceUp, active: showDivergence, onToggle: () => setShowDivergence((v) => !v) }]
      : []),
    {
      key: "ms", label: "횡보 음영", color: "#5b8def", active: showMarketState,
      onToggle: () => setShowMarketState((v) => !v),
    },
  ];

  const marketStateControls = showMarketState ? (
    <>
      <label className={styles.checkLabel} htmlFor="ms-n">N</label>
      <NumberInput id="ms-n" className={styles.msInput} min={1} step={1} value={msN} onChange={setMsN} />
      <label className={styles.checkLabel} htmlFor="ms-k">K</label>
      <NumberInput id="ms-k" className={styles.msInput} min={0} step={1} value={msK} onChange={setMsK} />
      <span className={styles.msLegend}>
        <span className={styles.msSwatchA} /> A 꼬임
        <span className={styles.msSwatchBC} /> BC 간격 축소+9 교차
      </span>
      {!msParamsValid && <span className={styles.msError}>N은 1 이상 정수, K는 0 이상 N 이하 정수여야 합니다.</span>}
      {msError && <span className={styles.msError}>{msError}</span>}
    </>
  ) : null;

  const drawHint =
    drawMode === "select" ? null : (
      <>
        그리기 모드에서는 캔들 클릭이 신호 패널이 아니라 선 등록으로 쓰입니다. 하나를 그리면 자동으로 &quot;캔들 선택&quot;으로 돌아가며, Esc로 취소할 수 있습니다.{" "}
        {drawMode === "trend"
          ? "시작점과 끝점, 두 번 클릭하세요."
          : drawMode === "zone"
            ? "직사각형의 대각선 두 모서리를 클릭하세요. (가격 구간 + 시간 구간)"
            : "차트를 클릭해서 가격 레벨을 지정하세요."}
      </>
    );

  return (
    <div className={styles.page}>
      {topBar}
      <div className={styles.body}>
        <ToolRail mode={drawMode} onChange={setDrawMode} />
        <div className={styles.chartColumn}>
          <ChartArea
            candles={data.candles}
            selectedDate={selectedDate}
            toggles={legendToggles}
            legendExtra={marketStateControls}
            chartProps={{
              bars,
              selectedDate,
              emaSeries: emaSeriesConfig,
              rsiSeries: rsiSeriesConfig,
              divergenceMarkers: visibleDivergenceMarkers,
              divMarkerColors: DIV_MARKER_COLOR,
              marketStateBlocks,
              drawMode,
              lines: data.manual_lines,
              onSelectDate: setSelectedDate,
              onAddHorizontalLine: handleAddHorizontal,
              onAddTrendLine: handleAddTrend,
              onAddZone: handleAddZone,
              onFinishDrawing: () => setDrawMode("select"),
              onDeleteLine: handleDeleteLine,
              onUpdateZone: handleUpdateZone,
              onUpdateTrend: handleUpdateTrend,
            }}
          />
          <PeriodBar
            options={Object.keys(WINDOW_OPTIONS).map((value) => ({ value, short: WINDOW_SHORT[value] }))}
            value={windowLabel}
            onChange={setWindowLabel}
            hint={drawHint}
          />
        </div>
        <aside className={styles.side}>
          <SignalPanel
            candle={selectedCandle}
            signals={selectedSignals}
            marketState={showMarketState && selectedDate ? marketStateByDate.get(selectedDate) ?? null : null}
            marketStateParams={showMarketState ? marketState?.params ?? null : null}
          />
          <LineManager lines={data.manual_lines} onDelete={handleDeleteLine} />
        </aside>
      </div>
    </div>
  );
}
