import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getRapidDrop } from "../api/rapidDrop";
import { useRapidDrop } from "./useRapidDrop";
import { rapidResponse } from "../test-fixtures/rapidDrop";
import type { RapidDropResponse } from "../types/rapidDrop";

vi.mock("../api/rapidDrop", () => ({ getRapidDrop: vi.fn() }));
const getMock = vi.mocked(getRapidDrop);
const deferred = () => {
  let resolve!: (value: RapidDropResponse) => void;
  const promise = new Promise<RapidDropResponse>((done) => { resolve = done; });
  return { promise, resolve };
};

describe("급락 대응 날짜별 요청", () => {
  beforeEach(() => { getMock.mockReset(); });

  it("OFF·주봉·미선택 상태에서는 요청하지 않는다", () => {
    const revision = {};
    const { rerender } = renderHook(({ enabled, daily, date }) => useRapidDrop(enabled, daily, date, revision),
      { initialProps: { enabled: false, daily: true, date: "2022-01-06" as string | null } });
    rerender({ enabled: true, daily: false, date: "2022-01-06" });
    rerender({ enabled: true, daily: true, date: null });
    expect(getMock).not.toHaveBeenCalled();
  });

  it("날짜 전환 전의 늦은 성공 응답이 현재 상태를 덮어쓰지 않는다", async () => {
    const first = deferred();
    const second = deferred();
    getMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const revision = {};
    const { result, rerender } = renderHook(({ date }) => useRapidDrop(true, true, date, revision),
      { initialProps: { date: "2022-01-06" } });
    rerender({ date: "2022-01-07" });
    expect(getMock.mock.calls[0][1]?.aborted).toBe(true);
    await act(async () => second.resolve(rapidResponse({ date: "2022-01-07" })));
    await waitFor(() => expect(result.current.data?.date).toBe("2022-01-07"));
    await act(async () => first.resolve(rapidResponse()));
    expect(result.current.data?.date).toBe("2022-01-07");
    expect(result.current.loading).toBe(false);
  });

  it("새로고침·수동 도형 변경으로 대시보드가 바뀌면 같은 날짜도 재조회한다", async () => {
    getMock.mockResolvedValue(rapidResponse());
    const { result, rerender } = renderHook(({ revision }) => useRapidDrop(true, true, "2022-01-06", revision),
      { initialProps: { revision: { version: 1 } } });
    await waitFor(() => expect(result.current.data).not.toBeNull());
    rerender({ revision: { version: 2 } });
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it("OFF 또는 주봉 전환으로 취소한 응답을 숨긴다", async () => {
    const pending = deferred();
    getMock.mockReturnValue(pending.promise);
    const revision = {};
    const { result, rerender } = renderHook(({ enabled, daily }) => useRapidDrop(enabled, daily, "2022-01-06", revision),
      { initialProps: { enabled: true, daily: true } });
    rerender({ enabled: false, daily: true });
    await act(async () => pending.resolve(rapidResponse()));
    expect(result.current).toEqual({ data: null, error: null, loading: false });
    rerender({ enabled: true, daily: false });
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it("현재 요청 오류를 표시한다", async () => {
    getMock.mockRejectedValue(new Error("요청 실패"));
    const revision = {};
    const { result } = renderHook(() => useRapidDrop(true, true, "2022-01-06", revision));
    await waitFor(() => expect(result.current.error).toContain("요청 실패"));
    expect(result.current.loading).toBe(false);
  });

  it("같은 날짜를 껐다 다시 켠 첫 렌더에서도 이전 결과를 새 요청 결과처럼 보이지 않는다", async () => {
    const pending = deferred();
    getMock.mockResolvedValueOnce(rapidResponse()).mockReturnValueOnce(pending.promise);
    const revision = {};
    const { result, rerender } = renderHook(({ enabled }) => useRapidDrop(enabled, true, "2022-01-06", revision),
      { initialProps: { enabled: true } });
    await waitFor(() => expect(result.current.data).not.toBeNull());
    rerender({ enabled: false });
    rerender({ enabled: true });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
    await act(async () => pending.resolve(rapidResponse()));
    expect(result.current.loading).toBe(false);
  });
});
