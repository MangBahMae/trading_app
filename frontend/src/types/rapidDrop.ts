// 급락 대응 v0.3 전용 응답. 기존 SignalItem과 별도로 표시·집계한다.
export interface RapidDropSignal {
  id: string;
  type: string;
  title: string;
  direction: "long" | "warning" | "reference";
  occurred_on: string;
  confirmed_at: string;
  anchor_id: string | null;
  anchor_day: string | null;
  reference: {
    price: number | null;
    bottom: number | null;
    top: number | null;
    source: string;
    support_id: string | null;
    support_version_id: string | null;
  };
  evidence: string[];
  cautions: string[];
  previous_candidate_ids: string[];
  event_ids: string[];
}

export type RapidDropPhase = "insufficient" | "normal" | "active" | "eased";

export interface RapidDropRawEvent {
  id: string;
  kind: string;
  day: string;
  [field: string]: unknown;
}

export interface RapidDropResponse {
  enabled: boolean;
  schema_version: "0.3";
  symbol: "BTCUSDT";
  interval: "1d";
  date: string;
  data_source: string;
  policy_source: string;
  summary: {
    title: string;
    badge: "new" | "maintained" | null;
    caution: string | null;
  };
  market: {
    phase: RapidDropPhase;
    accelerating_now: boolean | null;
    strong_drop: boolean | null;
    episode_id: string | null;
    episode_start: string | null;
    episode_low_close: number | null;
    previous_low_close: number | null;
    new_closing_low: boolean | null;
    eased_on: string | null;
    stable_bars: number;
    stable_bars_required: number | null;
    strong_speed_threshold: number | null;
    ease_speed_threshold: number | null;
    acceleration_delta: number | null;
    accelerating_down: boolean | null;
    observation_window: boolean;
    last_acceleration_date: string | null;
    previous_speed: number | null;
    recent_speed: number | null;
  };
  support: {
    status: "known" | "unconfirmed";
    known_versions: number;
    recording_started_at: string | null;
    unsupported_line_ids: number[];
    warnings: string[];
  };
  signals: RapidDropSignal[];
  maintained_candidates: RapidDropSignal[];
  history: RapidDropSignal[];
  raw_events: RapidDropRawEvent[];
  warnings: string[];
}
