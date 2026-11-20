import type { RapidDropResponse, RapidDropSignal } from "../types/rapidDrop";

// 프런트 표시·요청 흐름 검사용 합성 응답. 실제 시장 신호를 재현한 자료가 아니다.
export const rapidSignal = (patch: Partial<RapidDropSignal> = {}): RapidDropSignal => ({
  id: "synthetic-first", type: "first_brake_long", title: "롱 후보 · 첫 제동 반응", direction: "long",
  occurred_on: "2022-01-06", confirmed_at: "2022-01-07T00:00:00+00:00", anchor_id: "synthetic-anchor",
  anchor_day: "2022-01-06", reference: { price: 97, bottom: 96.03, top: 97.97,
    source: "support_reaction_close", support_id: "synthetic-support", support_version_id: "synthetic-v1" },
  evidence: ["망치형 반전 반응", "최근 평균 대비 거래량 3배"], cautions: ["실험 후보이며 주문이 아닙니다."],
  previous_candidate_ids: [], event_ids: ["synthetic-event"], ...patch,
});

export const rapidResponse = (patch: Partial<RapidDropResponse> = {}): RapidDropResponse => ({
  enabled: true, schema_version: "0.3", symbol: "BTCUSDT", interval: "1d", date: "2022-01-06",
  data_source: "synthetic_demo", policy_source: "급락 대응 v0.3 검증용 초안",
  summary: { title: "롱 후보 · 첫 제동", badge: "new", caution: "급락 경고가 남아 있습니다." },
  market: { phase: "active", accelerating_now: true, strong_drop: true,
    episode_id: "synthetic-episode", episode_start: "2022-01-05", episode_low_close: 95,
    previous_low_close: 97, new_closing_low: true, eased_on: null, stable_bars: 0, stable_bars_required: 3,
    strong_speed_threshold: -0.02, ease_speed_threshold: -0.01, acceleration_delta: 0.01,
    accelerating_down: true, observation_window: true, last_acceleration_date: "2022-01-05",
    previous_speed: -0.01, recent_speed: -0.03 },
  support: { status: "known", known_versions: 1, recording_started_at: "2022-01-01T00:00:00+00:00",
    unsupported_line_ids: [], warnings: [] },
  signals: [rapidSignal()], maintained_candidates: [], history: [rapidSignal()], raw_events: [], warnings: [], ...patch,
});
