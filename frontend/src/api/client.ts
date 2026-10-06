import type { CalculateRequest, CalculateResponse, ExchangeRateResponse } from "../types";

// 로컬 개발 기준 백엔드 주소. 배포 구성은 다음 단계(EC2/nginx)에서 다룬다.
// 서버 배포에서는 같은 도메인의 /api/...를 상대 경로로 부른다(빈 문자열). 개발 중에는 Vite 프록시
// (vite.config.ts)가 /api를 백엔드로 넘기고, 필요하면 VITE_API_BASE_URL로 다른 주소를 지정할 수 있다.
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export async function calculatePosition(payload: CalculateRequest): Promise<CalculateResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/position-sizing/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`계산 요청 실패: ${resp.status}`);
  }
  return resp.json();
}

export async function getExchangeRate(refresh = false): Promise<ExchangeRateResponse> {
  const resp = await fetch(
    `${API_BASE_URL}/api/position-sizing/exchange-rate?refresh=${refresh}`,
  );
  if (!resp.ok) {
    throw new Error(`환율 조회 실패: ${resp.status}`);
  }
  return resp.json();
}
