import type { DashboardResponse } from "../types";

// 서버 배포에서는 같은 도메인의 /api/...를 상대 경로로 부른다(빈 문자열). 개발 중에는 Vite 프록시
// (vite.config.ts)가 /api를 백엔드로 넘기고, 필요하면 VITE_API_BASE_URL로 다른 주소를 지정할 수 있다.
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export async function getDashboard(refresh = false): Promise<DashboardResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/dashboard?refresh=${refresh}`);
  if (!resp.ok) {
    throw new Error(`대시보드 조회 실패: ${resp.status}`);
  }
  return resp.json();
}

export async function addHorizontalLine(price: number): Promise<{ id: number }> {
  const resp = await fetch(`${API_BASE_URL}/api/lines/horizontal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ price }),
  });
  if (!resp.ok) {
    throw new Error(`수평선 추가 실패: ${resp.status}`);
  }
  return resp.json();
}

export async function addTrendLine(
  time1: string, price1: number, time2: string, price2: number,
): Promise<{ id: number }> {
  const resp = await fetch(`${API_BASE_URL}/api/lines/trend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time1, price1, time2, price2 }),
  });
  if (!resp.ok) {
    throw new Error(`추세선 추가 실패: ${resp.status}`);
  }
  return resp.json();
}

// 존: price1=상단, price2=하단, time1=시작, time2=끝 (서버가 잘못된 값은 422로 거부)
export async function addZone(
  time1: string, price1: number, time2: string, price2: number,
): Promise<{ id: number }> {
  const resp = await fetch(`${API_BASE_URL}/api/lines/zone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time1, price1, time2, price2 }),
  });
  if (!resp.ok) {
    throw new Error(`존 추가 실패: ${resp.status}`);
  }
  return resp.json();
}

// 추세선 두 점 수정(끝점 드래그): time1 <= time2로 정규화된 값을 보낸다. id는 그대로이고 서버가
// created_at을 수정 시각으로 갱신한다. 실패(404/422)하면 throw한다.
export async function updateTrend(
  lineId: number, time1: string, price1: number, time2: string, price2: number,
): Promise<{ id: number }> {
  const resp = await fetch(`${API_BASE_URL}/api/lines/trend/${lineId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time1, price1, time2, price2 }),
  });
  if (!resp.ok) {
    throw new Error(`추세선 수정 실패: ${resp.status}`);
  }
  return resp.json();
}

// 존 모양 수정(꼭지점 드래그): price1=상단, price2=하단, time1=시작, time2=끝. id는 그대로이고
// 서버가 created_at을 수정 시각으로 갱신한다. 실패(404/422)하면 throw한다.
export async function updateZone(
  lineId: number, time1: string, price1: number, time2: string, price2: number,
): Promise<{ id: number }> {
  const resp = await fetch(`${API_BASE_URL}/api/lines/zone/${lineId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time1, price1, time2, price2 }),
  });
  if (!resp.ok) {
    throw new Error(`존 수정 실패: ${resp.status}`);
  }
  return resp.json();
}

export async function deleteLine(lineId: number): Promise<void> {
  const resp = await fetch(`${API_BASE_URL}/api/lines/${lineId}`, { method: "DELETE" });
  if (!resp.ok) {
    throw new Error(`선 삭제 실패: ${resp.status}`);
  }
}
