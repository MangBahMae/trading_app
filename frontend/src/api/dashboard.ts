import type { DashboardResponse } from "../types";

const API_BASE_URL = "http://localhost:8000";

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

export async function deleteLine(lineId: number): Promise<void> {
  const resp = await fetch(`${API_BASE_URL}/api/lines/${lineId}`, { method: "DELETE" });
  if (!resp.ok) {
    throw new Error(`선 삭제 실패: ${resp.status}`);
  }
}
