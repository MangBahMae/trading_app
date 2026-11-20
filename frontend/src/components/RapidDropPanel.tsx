import { useState } from "react";
import type { RapidDropPhase, RapidDropRawEvent, RapidDropResponse, RapidDropSignal } from "../types/rapidDrop";
import styles from "./RapidDropPanel.module.css";

interface Props {
  data: RapidDropResponse | null;
  loading: boolean;
  error: string | null;
}

const price = (value: number | null) => value === null ? "미확인" : value.toLocaleString("en-US", { maximumFractionDigits: 2 });
const value = (number: number | null) => number === null ? "미확인" : String(number);
const yesNo = (flag: boolean | null) => flag === null ? "자료 부족" : flag ? "해당" : "아님";
const SOURCE_NAMES: Record<string, string> = {
  manual: "사용자 수동 지지", manual_support: "사용자 수동 지지",
  automatic_reference: "자동 기준 봉 가격", unconfirmed: "지지 미확인",
  support_reaction_close: "지지 반응 봉 종가 · 자동 기준", market: "시장 상태",
};
const PHASE_NAMES: Record<RapidDropPhase, string> = {
  insufficient: "데이터 부족", normal: "급락 구간 아님", active: "급락 지속", eased: "급락 완화",
};
const sourceName = (source: string) => SOURCE_NAMES[source] ?? source;

function SignalCard({ signal, maintained = false }: { signal: RapidDropSignal; maintained?: boolean }) {
  return (
    <li className={styles.signal} data-signal-id={signal.id}>
      <div className={styles.signalTitle}>
        <span className={signal.direction === "warning" ? styles.warning : undefined}>{signal.title}</span>
        <span className={styles.badge}>{maintained ? "유지" : "새 발생"}</span>
      </div>
      <div className={styles.meta}>발생 {signal.occurred_on} · 확정 {signal.confirmed_at} (UTC)</div>
      <div>{sourceName(signal.reference.source)} · 기준 {price(signal.reference.price)}</div>
      <div>기준 가격대 {price(signal.reference.bottom)} ~ {price(signal.reference.top)}</div>
      {signal.anchor_day ? <div>기준 봉 {signal.anchor_day}</div> : null}
      {signal.reference.support_id ? <div>지지 ID {signal.reference.support_id}</div> : null}
      {signal.reference.support_version_id ? <div>지지 버전 {signal.reference.support_version_id}</div> : null}
      {signal.evidence.length > 0 ? <ul>{signal.evidence.map((text, i) => <li key={`${i}:${text}`}>{text}</li>)}</ul> : null}
      {signal.cautions.length > 0 ? <ul className={styles.cautions}>{signal.cautions.map((text, i) => <li key={`${i}:${text}`}>{text}</li>)}</ul> : null}
      {signal.previous_candidate_ids.length > 0 ? <div>연결된 이전 후보 ID: {signal.previous_candidate_ids.join(", ")}</div> : null}
      <div>신호 ID {signal.id}</div>
      <div>신호 유형 {signal.type}</div>
      {signal.anchor_id ? <div>기준 ID {signal.anchor_id}</div> : null}
      {signal.event_ids.length > 0 ? <div>근거 사건 ID {signal.event_ids.join(", ")}</div> : null}
    </li>
  );
}

function RawEventCard({ event }: { event: RapidDropRawEvent }) {
  return (
    <li className={styles.signal} data-event-id={event.id}>
      <div>사건 종류 {event.kind} · 발생 {event.day}</div>
      <div>사건 ID {event.id}</div>
      <details className={styles.details}>
        <summary>원시 사건 전체 속성</summary>
        <pre className={styles.rawData}>{JSON.stringify(event, null, 2)}</pre>
      </details>
    </li>
  );
}

function SignalHistory({ history }: { history: RapidDropSignal[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <details className={styles.details} open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>선택일까지의 전체 발생 기록 ({history.length}개)</summary>
      {expanded ? history.length > 0
        ? <ul className={styles.list}>{history.map((signal) => <SignalCard key={signal.id} signal={signal} />)}</ul>
        : <p className={styles.note}>이전 발생 기록이 없습니다.</p> : null}
    </details>
  );
}

function MarketDetails({ market }: { market: RapidDropResponse["market"] }) {
  return (
    <div className={styles.marketDetails}>
      <h4>시장 판정 상세</h4>
      <div>현재 추가 가속: {yesNo(market.accelerating_now)} · 강한 급락 속도: {yesNo(market.strong_drop)}</div>
      <div>최근 속도 {value(market.recent_speed)} · 이전 속도 {value(market.previous_speed)} (봉당 로그수익률)</div>
      <div>강한 급락 기준 {value(market.strong_speed_threshold)} · 완화 속도 기준 {value(market.ease_speed_threshold)}</div>
      <div>추가 가속 차이 기준 {value(market.acceleration_delta)} · 안정 봉 {market.stable_bars}/{value(market.stable_bars_required)}</div>
      <div>구간 시작 {market.episode_start ?? "없음"} · 완화일 {market.eased_on ?? "없음"}</div>
      <div>전일까지 최저 종가 {price(market.previous_low_close)} · 구간 최저 종가 {price(market.episode_low_close)}</div>
      <div>새 종가 저점: {yesNo(market.new_closing_low)}</div>
      {market.last_acceleration_date ? <div>최근 추가 가속 {market.last_acceleration_date}</div> : null}
      {market.episode_id ? <div>급락 구간 ID {market.episode_id}</div> : null}
    </div>
  );
}

export default function RapidDropPanel({ data, loading, error }: Props) {
  const [expanded, setExpanded] = useState(false);
  const warnings = data ? [...new Set([...data.warnings, ...data.support.warnings])] : [];
  const phaseLabel = data?.market.phase === "active" && data.market.accelerating_now
    ? "급락 지속·가속" : data ? PHASE_NAMES[data.market.phase] : null;
  return (
    <section className={styles.section} aria-labelledby="rapid-drop-heading" data-testid="rapid-drop-panel">
      <h3 id="rapid-drop-heading">급락 대응 · 실험</h3>
      <p className={styles.note}>검증용 초안 · 기존 롱·숏 집계와 별도</p>
      {loading ? <p role="status">선택한 날짜의 급락 대응을 불러오는 중...</p> : null}
      {error ? <p role="alert" className={styles.warning}>{error}</p> : null}
      {!loading && !error && data ? data.enabled ? (
        <>
          {data.data_source === "synthetic_demo" ? <p className={styles.synthetic}>합성 데이터 · 검증용</p> : null}
          {data.data_source === "fixed_fixture" ? <p className={styles.meta}>고정 마감 일봉 데이터</p> : null}
          <div className={styles.market} data-testid="rapid-drop-summary">
            <div className={data.market.phase === "active" ? styles.warning : styles.phase}>{phaseLabel}</div>
            <div className={styles.summaryTitle}>
              <strong>{data.summary.title}</strong>
              {data.summary.badge ? <span className={styles.badge}>{data.summary.badge === "new" ? "새 발생" : "유지"}</span> : null}
            </div>
            {data.summary.caution ? <p className={styles.caution}>{data.summary.caution}</p> : null}
          </div>
          <details className={styles.details} open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
            <summary>전체 사건·근거·기록 보기</summary>
            {expanded ? (
              <>
                <MarketDetails market={data.market} />
                <p className={styles.meta}>{data.support.status === "unconfirmed" ? "지지 미확인" : `확인된 지지 버전 ${data.support.known_versions}개`}</p>
                {data.support.recording_started_at ? <p className={styles.meta}>지지 기록 시작 {data.support.recording_started_at}</p> : null}
                {data.support.unsupported_line_ids.length > 0 ? <div>미지원 도형 ID {data.support.unsupported_line_ids.join(", ")}</div> : null}
                <h4>당일 모든 발생 사건 ({data.signals.length}개)</h4>
                {data.signals.length > 0 ? <ul className={styles.list}>{data.signals.map((signal) => <SignalCard key={signal.id} signal={signal} />)}</ul> : <p className={styles.note}>당일 새 급락 대응 신호가 없습니다.</p>}
                <h4>이전 후보 유지 ({data.maintained_candidates.length}개)</h4>
                {data.maintained_candidates.length > 0 ? <ul className={styles.list}>{data.maintained_candidates.map((signal) => <SignalCard key={signal.id} signal={signal} maintained />)}</ul> : <p className={styles.note}>유지 중인 이전 후보가 없습니다.</p>}
                <h4>당일 원시 사건 ({data.raw_events.length}개)</h4>
                {data.raw_events.length > 0 ? <ul className={styles.list}>{data.raw_events.map((event) => <RawEventCard key={event.id} event={event} />)}</ul> : <p className={styles.note}>당일 원시 사건이 없습니다.</p>}
                <SignalHistory history={data.history} />
                <h4>적용 규칙 출처</h4>
                <div>{data.policy_source}</div>
                {warnings.length > 0 ? <ul className={styles.cautions}>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
              </>
            ) : null}
          </details>
        </>
      ) : <p className={styles.note}>서버에서 급락 대응 실험 기능이 꺼져 있습니다.</p> : null}
    </section>
  );
}
