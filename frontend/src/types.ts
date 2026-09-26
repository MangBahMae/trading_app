// 백엔드 backend/app/schemas/position_sizing.py 대응 타입

export type Direction = "long" | "short";

export interface PriceWeightItem {
  price: number;
  weight: number;
}

export interface CalculateRequest {
  balance: number;
  risk_pct: number;
  direction: Direction;
  entries: PriceWeightItem[];
  stop_loss: number;
  take_profits: PriceWeightItem[];
  margin?: number | null;
}

export interface TpResult {
  price: number;
  weight_pct: number;
  r_multiple: number;
}

export interface CalculateResponse {
  avg_entry: number;
  stop_pct: number;
  risk_amount: number;
  position_size: number | null;
  btc_quantity: number | null;
  leverage: number | null;
  tp_results: TpResult[];
  weighted_avg_r: number | null;
  warnings: string[];
  warning_messages: string[];
}

export interface ExchangeRateResponse {
  rate: number;
  source: "live" | "fallback";
}

// 진입가/TP가 동적 리스트 UI에서 쓰는 행 단위 - 삭제 시 인덱스가 밀려도
// key가 안 꼬이게 안정적인 id를 붙인다(기존 Streamlit _render_price_weight_list와
// 동일한 이유).
export interface PriceWeightRow {
  id: number;
  price: number;
  weight: number;
}
