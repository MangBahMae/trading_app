import type { CalculateRequest, CalculateResponse, ExchangeRateResponse } from "../types";

// 로컬 개발 기준 백엔드 주소. 배포 구성은 다음 단계(EC2/nginx)에서 다룬다.
const API_BASE_URL = "http://localhost:8000";

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
