import { useEffect, useMemo, useState } from "react";
import {
  addHorizontalLine, addTrendLine, addZone, deleteLine, getDashboard, updateTrend, updateZone,
} from "../api/dashboard";
import TvChart from "../components/chart/TvChart";
import type { EmaSeriesConfig } from "../components/chart/TvChart";
import LineManager from "../components/LineManager";
import SignalPanel from "../components/SignalPanel";
import type { DashboardResponse, DrawMode } from "../types";
import styles from "./SignalScanner.module.css";

const WINDOW_OPTIONS: Record<string, number | null> = {
  "최근 3개월": 90, "최근 6개월": 180, "최근 1년": 365, "전체": null,
};
const DEFAULT_WINDOW = "최근 6개월";

const EMA_STYLE: Record<string, { label: string; color: string; dashed: boolean }> = {
  ema9: { label: "EMA9", color: "#1f77ff", dashed: false },
  ema20: { label: "EMA20", color: "#ff8c00", dashed: false },
  ema50: { label: "EMA50", color: "#7d3cff", dashed: false },
  ema200: { label: "EMA200", color: "#000000", dashed: true },
};

const DRAW_MODE_OPTIONS: { label: string; value: DrawMode }[] = [
  { label: "캔들 선택", value: "select" },
  { label: "수평선 그리기 (클릭 1번)", value: "horizontal" },
  { label: "추세선 그리기 (클릭 2번)", value: "trend" },
  { label: "존 그리기 (클릭 2번)", value: "zone" },
];

const DIV_MARKER_COLOR: Record<string, string> = {
  regular_bullish: "#1a9c1a",
  regular_bearish: "#c21807",
};

export default function SignalScanner() {
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

  if (loading && !data) return <div className={styles.page}>불러오는 중...</div>;
  if (error && !data) return <div className={styles.page}>오류: {error}</div>;
  if (!data) return null;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1>BTCUSDT 1d 통합 신호 대시보드</h1>
          <p className={styles.caption}>
            데이터 범위: {data.date_range.min} ~ {data.date_range.max} (마지막으로 마감된 캔들까지만 반영)
          </p>
        </div>
        <button type="button" onClick={() => loadDashboard(true)} disabled={loading}>
          {loading ? "새로고침 중..." : "데이터 새로고침"}
        </button>
      </div>

      <div className={styles.controls}>
        <div className={styles.controlGroup}>
          {Object.keys(WINDOW_OPTIONS).map((label) => (
            <label key={label} className={styles.radioLabel}>
              <input
                type="radio" name="window" checked={windowLabel === label}
                onChange={() => setWindowLabel(label)}
              />
              {label}
            </label>
          ))}
        </div>

        <div className={styles.controlGroup}>
          {DRAW_MODE_OPTIONS.map((opt) => (
            <label key={opt.value} className={drawMode === opt.value ? styles.radioLabelActive : styles.radioLabel}>
              <input
                type="radio" name="drawMode" checked={drawMode === opt.value}
                onChange={() => setDrawMode(opt.value)}
              />
              {opt.label}
            </label>
          ))}
        </div>

        <div className={styles.controlGroup}>
          {Object.keys(EMA_STYLE).map((key) => (
            <label key={key} className={styles.checkLabel}>
              <input
                type="checkbox" checked={showEma[key]}
                onChange={(e) => setShowEma((prev) => ({ ...prev, [key]: e.target.checked }))}
              />
              {EMA_STYLE[key].label}
            </label>
          ))}
          <label className={styles.checkLabel}>
            <input type="checkbox" checked={showRsi} onChange={(e) => setShowRsi(e.target.checked)} />
            RSI
          </label>
          <label className={styles.checkLabel}>
            <input type="checkbox" checked={showDivergence} onChange={(e) => setShowDivergence(e.target.checked)} />
            다이버전스
          </label>
        </div>
      </div>

      {drawMode !== "select" && (
        <p className={styles.drawHint}>
          그리기 모드에서는 캔들 클릭이 신호 패널이 아니라 선 등록으로 쓰입니다. 하나를 그리면 자동으로 &quot;캔들 선택&quot;으로 돌아가며, Esc로 취소할 수 있습니다.{" "}
          {drawMode === "trend"
            ? "시작점과 끝점, 두 번 클릭하세요."
            : drawMode === "zone"
              ? "직사각형의 대각선 두 모서리를 클릭하세요. (가격 구간 + 시간 구간)"
              : "차트를 클릭해서 가격 레벨을 지정하세요."}
        </p>
      )}

      <div className={styles.columns}>
        <div className={styles.left}>
          <TvChart
            bars={bars}
            selectedDate={selectedDate}
            height={680}
            emaSeries={emaSeriesConfig}
            rsiSeries={rsiSeriesConfig}
            divergenceMarkers={visibleDivergenceMarkers}
            divMarkerColors={DIV_MARKER_COLOR}
            drawMode={drawMode}
            lines={data.manual_lines}
            onSelectDate={setSelectedDate}
            onAddHorizontalLine={handleAddHorizontal}
            onAddTrendLine={handleAddTrend}
            onAddZone={handleAddZone}
            onFinishDrawing={() => setDrawMode("select")}
            onDeleteLine={handleDeleteLine}
            onUpdateZone={handleUpdateZone}
            onUpdateTrend={handleUpdateTrend}
          />
          <LineManager lines={data.manual_lines} onDelete={handleDeleteLine} />
        </div>
        <div className={styles.right}>
          <SignalPanel candle={selectedCandle} signals={selectedSignals} />
        </div>
      </div>
    </div>
  );
}
