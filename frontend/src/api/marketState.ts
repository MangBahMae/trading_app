import type { MarketStateResponse } from "../types";

// dashboard.ts와 같은 방식 - 배포에선 같은 도메인의 상대 경로, 개발 중엔 Vite 프록시.
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

// 시장 상태 라벨(횡보/추세) - 신호가 아니라 차트 음영 전용. N/K를 바꿔 가며 다시 부른다.
export async function getMarketState(n: number, k: number): Promise<MarketStateResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/market-state?n=${n}&k=${k}`);
  if (!resp.ok) {
    throw new Error(`시장 상태 조회 실패: ${resp.status}`);
  }
  return resp.json();
}
