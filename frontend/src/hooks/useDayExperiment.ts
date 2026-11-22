import { useEffect, useMemo, useState } from "react";

interface Snapshot<T> {
  key: object;
  data: T | null;
  error: string | null;
}

// 날짜가 없으면 조회하지 않는다. 같은 날짜의 대시보드 갱신(수동 도형 편집 포함)도 새 요청이다.
export function useDayExperiment<T>(
  fetchDay: (date: string, signal: AbortSignal) => Promise<T>,
  date: string | null,
  revision: unknown,
) {
  const [snapshot, setSnapshot] = useState<Snapshot<T> | null>(null);
  const request = useMemo(() => ({ date, revision, fetchDay }), [date, revision, fetchDay]);

  useEffect(() => {
    if (request.date === null || request.revision === null) return;
    const controller = new AbortController();
    request.fetchDay(request.date, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setSnapshot({ key: request, data, error: null });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setSnapshot({ key: request, data: null, error: String(error) });
      });
    return () => controller.abort();
  }, [request]);

  if (date === null || revision === null) return { data: null, error: null, loading: false };
  if (snapshot?.key !== request) return { data: null, error: null, loading: true };
  return { data: snapshot.data, error: snapshot.error, loading: false };
}
