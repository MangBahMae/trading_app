import { breakoutTitle, type BreakoutEvent, type BreakoutResponse } from "../api/breakoutRetest";
import styles from "./RapidDropPanel.module.css";
import layout from "./BreakoutRetestPanel.module.css";

const number = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 6 });
const kinds: Record<string, string> = { zone: "존", horizontal: "수평선", trend: "추세선" };
const priority: Record<string, number> = {
  long_candidate: 0, short_candidate: 0, long_exit: 1, breakout_failed: 1,
  breakdown_failed: 1, reclaim_failed: 1, breakout_caution: 1,
};

function bounds(bottom: number, top: number) {
  return bottom === top ? `선 가격 ${number.format(top)}`
    : `하단 ${number.format(bottom)} · 상단 ${number.format(top)}`;
}

function EventLine({ event }: { event: BreakoutEvent }) {
  const stage = { new: "신규", maintained: "유지", ended: "종료" }[event.status];
  return (
    <li className={layout.line} data-event-id={event.id} data-type={event.type} data-status={event.status}>
      <span className={styles.badge}>{stage}</span> <strong>{event.label}</strong>
    </li>
  );
}

function EventDetails({ event }: { event: BreakoutEvent }) {
  return (
    <div className={styles.signal} data-detail-id={event.id}>
      <strong>{event.label}</strong>
      <div>{kinds[event.drawing_kind] ?? event.drawing_kind} {event.drawing_id} · 버전 {event.version_id}</div>
      <div>확인 {event.confirmed_date} (UTC 일봉)</div>
      {event.steps.length > 0 && <ol className={layout.steps}>{event.steps.map((step) =>
        <li key={step.id}>{step.date} · {step.label}
          {step.bottom != null && step.top != null && <div>{bounds(step.bottom, step.top)}</div>}
        </li>)}</ol>}
      {event.current_bottom != null && event.current_top != null && event.status === "maintained"
        && <div>선택일 기준 · {bounds(event.current_bottom, event.current_top)}</div>}
      {event.bottom != null && event.top != null && <div>확인 기준 · {bounds(event.bottom, event.top)}</div>}
      {event.close != null && <div>종가 {number.format(event.close)}</div>}
      <div>캔들 모양 · {event.candle_shape || "해당 없음"}
        {event.volume != null && <> · 거래량 {number.format(event.volume)}</>}</div>
      {event.origin === "rise_response" && <div>출처 · 기존 상승 대응 사건</div>}
      {event.evidence.map((line) => <div key={line}>{line}</div>)}
      {event.attempt_id && <div className={styles.meta}>시도 {event.attempt_id}</div>}
      <div className={styles.meta}>사건 {event.id}</div>
      {event.linked_ids.length > 0 && <div className={styles.meta}>연결 {event.linked_ids.join(" → ")}</div>}
    </div>
  );
}

interface Props {
  data: BreakoutResponse | null;
  loading: boolean;
  error: string | null;
}

export default function BreakoutRetestPanel({ data, loading, error }: Props) {
  const issued = data?.events ?? [];
  const ids = new Set(issued.map((event) => event.id));
  const maintained = data?.active.filter((event) => !ids.has(event.id)) ?? [];
  const today = issued.filter((event) => event.status !== "ended")
    .sort((a, b) => (priority[a.type] ?? 2) - (priority[b.type] ?? 2));
  const rows = [...today,
    ...issued.filter((event) => event.status === "ended"), ...maintained];
  return (
    <section className={styles.section} aria-labelledby="breakout-retest-heading"
      data-testid="breakout-retest-panel" data-date={data?.date}>
      <h3 id="breakout-retest-heading">{breakoutTitle}</h3>
      {loading && <p role="status">선택한 날짜의 돌파·재시험을 불러오는 중…</p>}
      {error && <p role="alert" className={styles.warning}>{error}</p>}
      {data && (data.enabled ? <>
        {data.data_source === "synthetic_demo" && <p className={styles.synthetic}>합성 데이터 · 검증용</p>}
        {data.data_source === "fixed_fixture" && <p className={styles.meta}>고정 마감 일봉 데이터</p>}
        {rows.length ? <ul className={layout.outcomes} aria-label="선택일 돌파·재시험">
          {rows.map((event) => <EventLine key={event.id} event={event} />)}
        </ul> : <p className={styles.note}>{data.history_status === "unconfirmed"
          ? "당시 도형 이력 미확인" : "돌파·재시험 사건 없음"}</p>}
        <div className={styles.note}>시장 방향 · {data.market_label}</div>
        {data.market_context && data.market_context !== data.market_label && <div>{data.market_context}</div>}
        {data.warnings.map((warning) => <p key={warning} className={styles.warning}>{warning}</p>)}
        {rows.length > 0 && <details className={styles.details}>
          <summary>도형·가격과 사건 순서</summary>
          {rows.map((event) => <EventDetails key={event.id} event={event} />)}
        </details>}
      </> : <p className={styles.note}>서버에서 돌파·재시험 실험 기능이 꺼져 있습니다.</p>)}
    </section>
  );
}
