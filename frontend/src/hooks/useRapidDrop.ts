import { getRapidDrop } from "../api/rapidDrop";
import { useDayExperiment } from "./useDayExperiment";

export function useRapidDrop(enabled: boolean, daily: boolean, date: string | null, revision: unknown) {
  return useDayExperiment(getRapidDrop, enabled && daily ? date : null, revision);
}
