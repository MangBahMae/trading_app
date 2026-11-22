const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export interface RiseEvent {
  kind: string;
  label: string;
  id: string;
  date: string;
  evidence?: string[];
  first_peak_day?: string;
  pullback_day?: string;
  retry_day?: string;
  peak_relation?: string;
  confirmation_below?: number;
  confirmation_close?: number;
  watch_breakout?: number;
  related_id?: string;
  related?: string;
  version?: string;
}

export interface RiseResponse {
  enabled: boolean;
  date: string;
  symbol: "BTCUSDT";
  interval: "1d";
  data_source: string;
  market: string;
  long_exit: string;
  short_signal: string;
  events: RiseEvent[];
  details: {
    market?: {
      candle_shape?: string | null;
      surge_sources?: string[];
      bullish_body_pct?: number | null;
      window_returns_pct?: Record<string, number>;
      impulse_floor?: number | null;
      first_peak?: number | null;
      pullback_close?: number | null;
      retry_peak?: number | null;
      overlap_ratio?: number | null;
      high_advance_pct?: number | null;
      watch_breakout?: number | null;
      active_watches?: { id: string; date: string; watch_breakout: number }[];
    };
    drawings?: {
      trendline_status?: string;
      support_status?: string;
      active_short_ids?: string[];
      levels?: {
        kind: string;
        version: string;
        price?: number;
        bottom?: number;
        top?: number;
        state: string;
        rule?: string;
        time1?: string;
        price1?: number;
        time2?: string;
        price2?: number;
      }[];
    };
    warnings?: string[];
  };
}

export async function getRiseResponse(date: string, signal: AbortSignal): Promise<RiseResponse> {
  const response = await fetch(`${API_BASE_URL}/api/rise-response?date=${encodeURIComponent(date)}`, { signal });
  if (!response.ok) throw new Error(`상승 대응 조회 실패 (${response.status})`);
  const result: RiseResponse = await response.json();
  if (result.date !== date || result.interval !== "1d" || result.symbol !== "BTCUSDT") {
    throw new Error("선택한 BTCUSDT 일봉과 상승 대응 응답이 일치하지 않습니다.");
  }
  return result;
}
