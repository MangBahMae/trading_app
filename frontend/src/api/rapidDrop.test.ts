import { afterEach, describe, expect, it, vi } from "vitest";
import { getRapidDrop } from "./rapidDrop";
import { rapidResponse } from "../test-fixtures/rapidDrop";

describe("급락 대응 API 클라이언트", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("선택 날짜와 취소 signal을 API에 전달한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => rapidResponse() });
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    expect(await getRapidDrop("2022-01-06", controller.signal)).toEqual(rapidResponse());
    expect(fetchMock).toHaveBeenCalledWith(`${import.meta.env.VITE_API_BASE_URL ?? ""}/api/rapid-drop?date=2022-01-06`, { signal: controller.signal });
  });

  it("실패 상태를 오류로 보고한다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    await expect(getRapidDrop("2022-01-06")).rejects.toThrow("급락 대응 조회 실패: 503");
  });

  it("다른 날짜의 응답을 선택일 결과로 표시하지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => rapidResponse({ date: "2022-01-07" }) }));
    await expect(getRapidDrop("2022-01-06")).rejects.toThrow("응답 날짜");
  });
});
