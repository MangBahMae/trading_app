import { useEffect, useMemo, useState } from "react";
import { getRapidDrop } from "../api/rapidDrop";
import type { RapidDropResponse } from "../types/rapidDrop";

interface Snapshot {
  key: object;
  data: RapidDropResponse | null;
  error: string | null;
}

// 대시보드 객체가 바뀌면 같은 날짜도 재조회한다(새로고침·수동 선/존 변경).
// 취소와 응답 키 확인을 함께 사용하여 날짜/봉 간격 전환 중 옛 응답이 표시되지 않게 한다.
export function useRapidDrop(enabled: boolean, daily: boolean, date: string | null, revision: unknown) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const requestKey = useMemo(() => ({ enabled, daily, date, revision }), [enabled, daily, date, revision]);

  useEffect(() => {
    if (!enabled || !daily || date === null || revision === null) return;
    const controller = new AbortController();
    getRapidDrop(date, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setSnapshot({ key: requestKey, data, error: null });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setSnapshot({ key: requestKey, data: null, error: String(error) });
        }
      });
    return () => controller.abort();
  }, [enabled, daily, date, revision, requestKey]);

  if (!enabled || !daily || date === null || revision === null) {
    return { data: null, error: null, loading: false };
  }
  const current = snapshot?.key === requestKey;
  return {
    data: current ? snapshot.data : null,
    error: current ? snapshot.error : null,
    loading: !current,
  };
}
