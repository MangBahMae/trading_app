const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";
export const breakoutTitle = "돌파·재시험 · 실험";

export interface BreakoutEvent {
  id: string;
  type: string;
  label: string;
  origin: string;
  status: "new" | "maintained" | "ended";
  drawing_id: string;
  version_id: string;
  drawing_kind: string;
  attempt_id: string | null;
  breakout_date: string | null;
  retest_date: string | null;
  confirmed_date: string;
  linked_ids: string[];
  bottom: number | null;
  top: number | null;
  close: number | null;
  candle_shape: string | null;
  volume: number | null;
  current_bottom?: number | null;
  current_top?: number | null;
  steps: { id: string; type: string; label: string; date: string; bottom: number | null; top: number | null; close: number | null }[];
  evidence: string[];
}

export interface BreakoutResponse {
  date: string;
  enabled: boolean;
  interval: "1d";
  symbol: "BTCUSDT";
  data_source: string;
  market_label: string;
  market_context: string | null;
  history_status: "unconfirmed" | "recorded";
  remaining_long_exits: string[];
  warnings: string[];
  events: BreakoutEvent[];
  active: BreakoutEvent[];
}

export async function getBreakoutRetest(date: string, signal: AbortSignal): Promise<BreakoutResponse> {
  const response = await fetch(`${API_BASE_URL}/api/breakout-retest?date=${encodeURIComponent(date)}`, { signal });
  if (!response.ok) throw new Error(`돌파·재시험 조회 실패 (${response.status})`);
  const result: BreakoutResponse = await response.json();
  if (result.date !== date || result.symbol !== "BTCUSDT" || result.interval !== "1d") {
    throw new Error("선택한 BTCUSDT 일봉과 돌파·재시험 응답이 일치하지 않습니다.");
  }
  return result;
}
