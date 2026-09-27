import type { Trade, TradeCloseInput, TradePlanInput, TradeStatus } from "../types";

const API_BASE_URL = "http://localhost:8000";

export class TradeApiError extends Error {
  errors: string[];
  constructor(errors: string[]) {
    super(errors.join(", "));
    this.errors = errors;
  }
}

// FastAPI는 두 종류의 detail을 준다: 우리 서비스 계층이 던진 문자열 코드
// 배열(예: "entries_empty" - 400)과, pydantic 자체 스키마 검증 실패 시의
// 에러 객체 배열(예: {type, loc, msg, ...} - 422, 우리가 만든 코드가 아님).
// 후자를 문자열로 렌더링하려던 게 실제로 크래시("Objects are not valid as
// a React child")를 낸 적이 있어서, 어떤 모양이 와도 항상 문자열 배열로
// 정규화한다.
function normalizeDetail(detail: unknown): string[] {
  if (!Array.isArray(detail)) return [String(detail ?? "unknown_error")];
  return detail.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object" && "msg" in item) return String((item as { msg: unknown }).msg);
    return JSON.stringify(item);
  });
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new TradeApiError(normalizeDetail(body?.detail ?? resp.status));
  }
  return resp.json();
}

export async function getSignalTags(): Promise<string[]> {
  const resp = await fetch(`${API_BASE_URL}/api/trades/signal-tags`);
  return handle(resp);
}

export async function listTrades(status?: TradeStatus): Promise<Trade[]> {
  const url = new URL(`${API_BASE_URL}/api/trades`);
  if (status) url.searchParams.set("status", status);
  const resp = await fetch(url);
  return handle(resp);
}

export async function getTrade(id: number): Promise<Trade> {
  const resp = await fetch(`${API_BASE_URL}/api/trades/${id}`);
  return handle(resp);
}

export async function createTrade(payload: TradePlanInput, draft = false): Promise<Trade> {
  const resp = await fetch(`${API_BASE_URL}/api/trades?draft=${draft}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(resp);
}

export async function updateTrade(id: number, payload: Partial<TradePlanInput>, draft = false): Promise<Trade> {
  const resp = await fetch(`${API_BASE_URL}/api/trades/${id}?draft=${draft}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(resp);
}

export async function closeTrade(id: number, payload: TradeCloseInput): Promise<Trade> {
  const resp = await fetch(`${API_BASE_URL}/api/trades/${id}/close`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(resp);
}

export async function deleteTrade(id: number): Promise<void> {
  const resp = await fetch(`${API_BASE_URL}/api/trades/${id}`, { method: "DELETE" });
  await handle(resp);
}
