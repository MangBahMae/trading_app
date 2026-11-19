import type { RapidDropResponse, RapidDropSignal } from "../types/rapidDrop";
import styles from "./RapidDropPanel.module.css";

interface Props {
  data: RapidDropResponse | null;
  loading: boolean;
  error: string | null;
}

const price = (value: number | null) => value === null ? "미확인" : value.toLocaleString("en-US", { maximumFractionDigits: 2 });
const SOURCE_NAMES: Record<string, string> = {
  manual: "사용자 수동 지지", manual_support: "사용자 수동 지지",
  automatic_reference: "자동 기준 봉 가격", unconfirmed: "지지 미확인",
  support_reaction_close: "지지 반응 봉 종가 · 자동 기준",
  market: "시장 상태",
};
const sourceName = (source: string) => SOURCE_NAMES[source] ?? source;

function SignalCard({ signal, maintained = false }: { signal: RapidDropSignal; maintained?: boolean }) {
  return (
    <li className={styles.signal} data-signal-id={signal.id}>
      <div className={styles.signalTitle}>
        <span className={signal.direction === "warning" ? styles.warning : undefined}>{signal.title}</span>
        <span className={styles.badge}>{maintained ? "유지" : "새 발생"}</span>
      </div>
      <div className={styles.meta}>발생 {signal.occurred_on}</div>
      <div className={styles.meta}>{sourceName(signal.reference.source)} · 기준 {price(signal.reference.price)}</div>
      <details className={styles.details}>
        <summary>근거·주의사항·참조 보기</summary>
        <div>확정 {signal.confirmed_at} (UTC)</div>
        <div>기준 가격대 {price(signal.reference.bottom)} ~ {price(signal.reference.top)}</div>
        {signal.anchor_day ? <div>기준 봉 {signal.anchor_day}</div> : null}
        {signal.reference.support_id ? <div>지지 ID {signal.reference.support_id}</div> : null}
        {signal.reference.support_version_id ? <div>지지 버전 {signal.reference.support_version_id}</div> : null}
        {signal.evidence.length > 0 ? <ul>{signal.evidence.map((text, i) => <li key={`${i}:${text}`}>{text}</li>)}</ul> : null}
        {signal.cautions.length > 0 ? <ul className={styles.cautions}>{signal.cautions.map((text, i) => <li key={`${i}:${text}`}>{text}</li>)}</ul> : null}
        {signal.previous_candidate_ids.length > 0 ? <div>연결된 이전 후보 ID: {signal.previous_candidate_ids.join(", ")}</div> : null}
        <div>신호 ID {signal.id}</div>
        {signal.anchor_id ? <div>기준 ID {signal.anchor_id}</div> : null}
        {signal.event_ids.length > 0 ? <div>근거 사건 ID {signal.event_ids.join(", ")}</div> : null}
      </details>
    </li>
  );
}

export default function RapidDropPanel({ data, loading, error }: Props) {
  const warnings = data ? [...new Set([...data.warnings, ...data.support.warnings])] : [];
  return (
    <section className={styles.section} aria-labelledby="rapid-drop-heading" data-testid="rapid-drop-panel">
      <h3 id="rapid-drop-heading">급락 대응 · 실험</h3>
      <p className={styles.note}>검증용 초안 · 기존 독립 신호의 롱·숏 집계와 별도입니다.</p>
      {loading ? <p role="status">선택한 날짜의 급락 대응을 불러오는 중...</p> : null}
      {error ? <p role="alert" className={styles.warning}>{error}</p> : null}
      {!loading && !error && data ? (
        data.enabled ? (
          <>
            {data.data_source === "synthetic_demo" ? <p className={styles.synthetic}>합성 데이터 · 검증용</p> : null}
            {data.data_source === "fixed_fixture" ? <p className={styles.note}>고정 마감 일봉 데이터</p> : null}
            <div className={styles.market}>
              <strong className={data.market.accelerating_down ? styles.warning : undefined}>
                {data.market.accelerating_down === null ? "가속 판정: 데이터 부족" : data.market.accelerating_down ? "현재 하락 가속" : "현재 하락 가속 아님"}
              </strong>
              <div>{data.market.observation_window ? "최근 급락 이후 관찰 구간" : "급락 관찰 구간 아님"}</div>
              {data.market.last_acceleration_date ? <div className={styles.meta}>최근 가속 {data.market.last_acceleration_date}</div> : null}
            </div>
            <p className={styles.note}>
              {data.support.status === "unconfirmed" ? "지지 미확인" : `확인된 지지 버전 ${data.support.known_versions}개`}
            </p>
            {data.support.recording_started_at ? <p className={styles.meta}>지지 기록 시작 {data.support.recording_started_at}</p> : null}
            <h4>당일 새 발생</h4>
            {data.signals.length > 0 ? <ul className={styles.list}>{data.signals.map((signal) => <SignalCard key={signal.id} signal={signal} />)}</ul> : <p className={styles.note}>당일 새 급락 대응 신호가 없습니다.</p>}
            <h4>이전 후보 유지</h4>
            {data.maintained_candidates.length > 0 ? <ul className={styles.list}>{data.maintained_candidates.map((signal) => <SignalCard key={signal.id} signal={signal} maintained />)}</ul> : <p className={styles.note}>유지 중인 이전 후보가 없습니다.</p>}
            <details className={styles.details}><summary>적용 규칙 출처</summary>{data.policy_source}</details>
          </>
        ) : <p className={styles.note}>서버에서 급락 대응 실험 기능이 꺼져 있습니다.</p>
      ) : null}
      {warnings.length > 0 ? <ul className={styles.cautions}>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
    </section>
  );
}
