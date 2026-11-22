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
  reaction_low: number | null;
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

export type RapidDropPhase = "insufficient" | "normal" | "sharp_drop" | "post_drop";

export interface RapidDropRawEvent {
  id: string;
  kind: string;
  day: string;
  [field: string]: unknown;
}

export interface RapidDropAnchor {
  id: string;
  day: string;
  source: "manual" | "auto";
  reference_price: number;
  initial_low: number;
  bottom: number;
  top: number;
  bounced_on: string | null;
  support_id: string | null;
  support_version_id: string | null;
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
    last_drop_date: string | null;
    recovery_line: number | null;
    post_drop_bars: number;
    price_recovery_streak: number;
    speed_stable_count: number;
    exit_reason: "price_recovery" | "speed_stability" | null;
    reworsened: boolean;
    strong_speed_threshold: number | null;
    ease_speed_threshold: number | null;
    acceleration_delta: number | null;
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
  active_anchors: RapidDropAnchor[];
  history: RapidDropSignal[];
  raw_events: RapidDropRawEvent[];
  warnings: string[];
}
