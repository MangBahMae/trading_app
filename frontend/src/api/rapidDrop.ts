import type { RapidDropResponse } from "../types/rapidDrop";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export async function getRapidDrop(date: string, signal?: AbortSignal): Promise<RapidDropResponse> {
  const response = await fetch(`${API_BASE_URL}/api/rapid-drop?date=${encodeURIComponent(date)}`, { signal });
  if (!response.ok) {
    throw new Error(`급락 대응 조회 실패: ${response.status}`);
  }
  const result: RapidDropResponse = await response.json();
  if (result.date !== date) {
    throw new Error("급락 대응 응답 날짜가 선택한 날짜와 다릅니다.");
  }
  return result;
}
