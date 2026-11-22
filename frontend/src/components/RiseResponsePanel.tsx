import { getRiseResponse, type RiseResponse } from "../api/riseResponse";
import { useDayExperiment } from "../hooks/useDayExperiment";
import styles from "./RapidDropPanel.module.css";
import layout from "./RiseResponsePanel.module.css";

const number = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 4 });
const percent = new Intl.NumberFormat("ko-KR", { style: "percent", maximumFractionDigits: 2 });
const levelKinds: Record<string, string> = { trend: "추세선", horizontal: "수평선", zone: "지지 존" };

function Evidence({ data }: { data: RiseResponse }) {
  const { market, drawings, warnings } = data.details;
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
        <h4>상승 구간</h4>
        <div>당일 급등 조건 · {market.surge_sources?.join(" · ") || "해당 없음"}</div>
        {market.bullish_body_pct != null && <div>몸통 등락률 {number.format(market.bullish_body_pct)}%</div>}
        {Object.entries(market.window_returns_pct ?? {}).map(([bars, value]) => (
          <div key={bars}>{bars}봉 누적 등락률 {number.format(value)}%</div>
        ))}
        {market.candle_shape && <div>캔들 모양 · {market.candle_shape}</div>}
        {market.overlap_ratio != null && <div>가격대 겹침 {percent.format(market.overlap_ratio)}</div>}
        {market.high_advance_pct != null && <div>고점 전진 {number.format(market.high_advance_pct)}%</div>}
        {prices.map(([label, price]) => price == null ? null : <div key={label}>{label} {number.format(price)}</div>)}
        {market.active_watches && market.active_watches.length > 0 && <details>
          <summary>유지 중인 고점 관찰 ({market.active_watches.length})</summary>
          {market.active_watches.map((watch) => <div key={watch.id}>
            {watch.date} · 해제 기준 {number.format(watch.watch_breakout)} · {watch.id}
          </div>)}
        </details>}
      </>}
      {drawings && <>
        <h4>당시 수동 도형</h4>
        <div>{[drawings.trendline_status, drawings.support_status].filter(Boolean).join(" · ")}</div>
        {drawings.levels?.map((level) => (
          <div className={styles.signal} key={level.version}>
            <strong>{levelKinds[level.kind] ?? level.kind} · {level.state}</strong>
            {level.price != null && <div>당일 선 가격 {number.format(level.price)}</div>}
            {level.bottom != null && <div>하단 {number.format(level.bottom)}</div>}
            {level.top != null && <div>상단 {number.format(level.top)}</div>}
            {level.rule && <div>{level.rule}</div>}
            {level.time1 && level.price1 != null && <div>첫 좌표 {level.time1} · {number.format(level.price1)}</div>}
            {level.time2 && level.price2 != null && <div>둘째 좌표 {level.time2} · {number.format(level.price2)}</div>}
            <div className={styles.meta}>버전 {level.version}</div>
          </div>
        ))}
        {drawings.active_short_ids && drawings.active_short_ids.length > 0 &&
          <div className={styles.meta}>추적 중인 숏 후보 ID {drawings.active_short_ids.join(", ")}</div>}
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
  return (
    <section aria-labelledby="rise-response-heading" className={styles.section} data-testid="rise-response-panel"
      data-date={data?.date}>
      <h3 id="rise-response-heading">상승·급등 대응 · 실험</h3>
      {loading && <p role="status">선택한 날짜의 상승 대응을 불러오는 중…</p>}
      {error && <p role="alert" className={styles.warning}>{error}</p>}
      {data && (data.enabled ? <>
        {data.data_source === "synthetic_demo" && <p className={styles.synthetic}>합성 데이터 · 검증용</p>}
        {data.data_source === "fixed_fixture" && <p className={styles.meta}>고정 마감 일봉 데이터</p>}
        <dl className={layout.outcomes}>
          <div><dt>시장 상태</dt><dd>{data.market}</dd></div>
          <div><dt>롱 종료 검토</dt><dd>{data.long_exit}</dd></div>
          <div><dt>숏 관찰·후보</dt><dd>{data.short_signal}</dd></div>
        </dl>
        <Evidence data={data} />
      </> : <p className={styles.note}>서버에서 상승 대응 실험 기능이 꺼져 있습니다.</p>)}
    </section>
  );
}
