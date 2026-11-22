import { getRiseResponse, type RiseResponse } from "../api/riseResponse";
import { useDayExperiment } from "../hooks/useDayExperiment";
import styles from "./RapidDropPanel.module.css";
import layout from "./RiseResponsePanel.module.css";

const number = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 4 });
const percent = new Intl.NumberFormat("ko-KR", { style: "percent", maximumFractionDigits: 2 });
const levelKinds: Record<string, string> = {
  trend: "추세선", horizontal: "수평선", zone: "지지 존", swing_low: "확정 스윙 저점", resistance: "저항",
};
const regimes = { bullish: "정배열", bearish: "역배열", convergence: "수렴", mixed: "혼조" };
const priceDirections = {
  up: "고점·저점 상승", down: "고점·저점 하락", mixed: "고점·저점 엇갈림", unknown: "방향 미확인",
};
const stages = { new: "신규", maintained: "유지", released: "해제", invalidated: "무효" };

function hasSignal(text: string) {
  return text !== "해당 없음" && text !== "없음";
}

function shortCautionReason(data: RiseResponse) {
  if (hasSignal(data.long_exit) || hasSignal(data.short_signal) || data.details.warnings?.length) return null;
  const market = data.details.market;
  if (market?.price_phase === "상승 구간 · 눌림" || market?.price_phase === "상승 둔화 · 고점 횡보") return null;
  // 서버가 약화·충돌을 함께 표시한 정배열은 '온전한 상승 우세'로 강조하지 않는다.
  if (["롱 우세 · 정배열 유지", "상승 우세 · 수렴", "상승 우세 · 혼조"].includes(data.market)) {
    return "상승 우세";
  }
  if (market?.surge_context && market.price_phase === "상승 추세 유지" &&
      market.ema_regime !== "bearish" && market.ema_regime !== "bullish" && market.price_direction !== "down") {
    return "급등 직후";
  }
  return null;
}

function shortSignalClass(data: RiseResponse, label: string) {
  const event = data.events.find((item) => item.label === label);
  if (event?.kind === "support_retest_short") return layout.shortCandidate;
  if (event?.kind === "high_retry_failed" || event?.kind === "resistance_rejected") return layout.shortWatch;
  return layout.secondary;
}

function Evidence({ data }: { data: RiseResponse }) {
  const { market, drawings, warnings, lifecycle } = data.details;
  const breakouts = new Map(market?.active_watches?.map((watch) => [watch.id, watch.watch_breakout]));
  const prices = [
    ["상승 구간 유지 기준가", market?.impulse_floor],
    ["첫 고점", market?.first_peak],
    ["눌림 종가", market?.pullback_close],
    ["재시도 고점", market?.retry_peak],
    ["숏 관찰 해제 기준", market?.watch_breakout],
  ] as const;
  return (
    <details className={styles.details}>
      <summary>판정 근거와 당일 사건</summary>
      {market && <>
        <h4>시장 방향의 근거</h4>
        <div>EMA9·20·50 {market.ema_regime ? regimes[market.ema_regime] : "배열 미확인"}</div>
        {market.price_direction && <div>가격 구조 · {priceDirections[market.price_direction]}</div>}
        {market.price_phase && <div>{market.price_phase}</div>}
        {([["고점", market.swing_highs], ["저점", market.swing_lows]] as const).map(([label, points]) =>
          points?.map((point) => <div key={label + point.date}>
            {label} {number.format(point.price)} · 발생 {point.date} → 확인 {point.confirmed_on}
          </div>))}
        {market.ema50 != null && <div>EMA50 {number.format(market.ema50)}</div>}
        {market.ema200 != null && <div>EMA200 {number.format(market.ema200)}</div>}
        <div>당일 급등 조건 · {market.surge_sources?.join(" · ") || "해당 없음"}</div>
        {market.surge_context && !market.surge_sources?.length && <div>최근 급등 영향 구간</div>}
        {market.bullish_body_pct != null && <div>몸통 등락률 {number.format(market.bullish_body_pct)}%</div>}
        {Object.entries(market.window_returns_pct ?? {}).map(([bars, value]) => (
          <div key={bars}>{bars}봉 누적 등락률 {number.format(value)}%</div>
        ))}
        {market.candle_shape && <div>캔들 모양 · {market.candle_shape}</div>}
        {market.overlap_ratio != null && <div>가격대 겹침 {percent.format(market.overlap_ratio)}</div>}
        {market.high_advance_pct != null && <div>고점 전진 {number.format(market.high_advance_pct)}%</div>}
        {prices.map(([label, price]) => price == null ? null : <div key={label}>{label} {number.format(price)}</div>)}
      </>}
      {drawings && <>
        <h4>당시 지지·저항</h4>
        <div>{[drawings.trendline_status, drawings.support_status].filter(Boolean).join(" · ")}</div>
        {drawings.levels?.map((level) => (
          <div className={styles.signal} key={level.kind + ":" + level.version}>
            <strong>{level.kind === "resistance" && level.source && (level.source === "manual" ? "수동 " : level.source + " ")}
              {levelKinds[level.kind] ?? level.kind} · {level.state}</strong>
            {level.kind === "trend" && level.price != null && <div>당일 선 가격 {number.format(level.price)}</div>}
            {(level.source === "EMA50" || level.source === "EMA200") && <>
              {level.price != null && <div>접촉 당시 {level.source} {number.format(level.price)}</div>}
              {level.current_price != null && <div>당일 {level.source} {number.format(level.current_price)}</div>}
            </>}
            {level.bottom != null && <div>하단 {number.format(level.bottom)}</div>}
            {level.top != null && <div>상단 {number.format(level.top)}</div>}
            {level.pivot_date && level.confirmed_on &&
              <div>저점 발생 {level.pivot_date} → 지지 확인 {level.confirmed_on}</div>}
            {level.touch_date && <div>접촉 {level.touch_date}
              {level.touch_low != null && <> · 접촉 봉 저가 {number.format(level.touch_low)}</>}
            </div>}
            {level.rule && <div>{level.rule}</div>}
            {level.time1 && level.price1 != null && <div>첫 좌표 {level.time1} · {number.format(level.price1)}</div>}
            {level.time2 && level.price2 != null && <div>둘째 좌표 {level.time2} · {number.format(level.price2)}</div>}
            <div className={styles.meta}>기준 {level.version}</div>
          </div>
        ))}
      </>}
      {lifecycle && lifecycle.length > 0 && <>
        <h4>선택일 숏 관찰·후보</h4>
        <ul className={layout.lifecycle}>
          {lifecycle.map((item) => {
            const breakout = breakouts.get(item.id);
            return <li key={item.id}>
              <span className={styles.badge}>{stages[item.status]}</span> <strong>{item.label}</strong>
              <div>{item.source} · 시작 {item.started_on}
                {item.ended_on && <> · 종료 {item.ended_on}</>} · {item.age_days}일</div>
              {breakout != null && <div>해제 기준 · 종가 {number.format(breakout)} 초과</div>}
              {item.reason && <div>{item.reason}</div>}
            </li>;
          })}
        </ul>
      </>}
      <h4>당일 사건 ({data.events.length})</h4>
      {data.events.map((event) => (
        <div className={styles.signal} key={event.id}>
          <strong>{event.label}</strong>
          <div className={styles.meta}>확정 {event.date} (UTC 일봉)</div>
          {event.retry_day && <div>첫 고점 {event.first_peak_day} → 눌림 {event.pullback_day} → 재시도 {event.retry_day} · {event.peak_relation}</div>}
          {event.confirmation_below != null && <div>밀림 확인 기준 {number.format(event.confirmation_below)}</div>}
          {event.watch_breakout != null && <div>상방 돌파 기준 {number.format(event.watch_breakout)}</div>}
          {event.confirmation_close != null && <div>확정 종가 {number.format(event.confirmation_close)}</div>}
          {event.evidence?.map((reason) => <div key={reason}>{reason}</div>)}
          {event.version && <div className={styles.meta}>도형 버전 {event.version}</div>}
          {(event.related_id || event.related) && <div className={styles.meta}>연결 사건 {event.related_id || event.related}</div>}
          <div className={styles.meta}>ID {event.id}</div>
        </div>
      ))}
      {warnings?.map((text) => <p key={text} className={styles.warning}>{text}</p>)}
    </details>
  );
}

export default function RiseResponsePanel({ date, revision }: { date: string; revision: unknown }) {
  const { data, loading, error } = useDayExperiment(getRiseResponse, date, revision);
  const statuses = new Set(data?.details.lifecycle?.map((item) => item.status));
  const caution = data?.enabled ? shortCautionReason(data) : null;
  return (
    <section aria-labelledby="rise-response-heading" className={styles.section} data-testid="rise-response-panel"
      data-date={data?.date}>
      <h3 id="rise-response-heading">상승·급등 대응 · 실험</h3>
      {loading && <p role="status">선택한 날짜의 상승 대응을 불러오는 중…</p>}
      {error && <p role="alert" className={styles.warning}>{error}</p>}
      {data && (data.enabled ? <>
        {caution && <p className={layout.caution}>
          <strong>숏 진입 주의</strong><span>{caution} · 신규 숏 근거 없음</span>
        </p>}
        {data.data_source === "synthetic_demo" && <p className={styles.synthetic}>합성 데이터 · 검증용</p>}
        {data.data_source === "fixed_fixture" && <p className={styles.meta}>고정 마감 일봉 데이터</p>}
        <dl className={layout.outcomes}>
          <div><dt>시장 방향</dt><dd>{data.market}</dd></div>
          <div><dt>기존 롱 종료 검토</dt><dd className={hasSignal(data.long_exit) ? layout.longExit : layout.secondary}>{data.long_exit}</dd></div>
          <div><dt>숏 관찰·후보
            {statuses.size > 0 && <span className={layout.statuses}>
              {Array.from(statuses, (status) => <span key={status} className={styles.badge}>{stages[status]}</span>)}
            </span>}
          </dt><dd>{data.short_signal.split(" / ").map((label, index) => (
            <span key={label}>{index > 0 && " / "}<span className={shortSignalClass(data, label)}>{label}</span></span>
          ))}</dd></div>
        </dl>
        <Evidence data={data} />
      </> : <p className={styles.note}>서버에서 상승 대응 실험 기능이 꺼져 있습니다.</p>)}
    </section>
  );
}
