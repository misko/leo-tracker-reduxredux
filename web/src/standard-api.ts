import type {
  StandardPlotViewV2,
  StandardSubjectDetailV2,
  StandardSubjectHierarchyV2,
  StandardViewKindV2,
} from "./standard-contracts";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: "GET", signal });
  if (!response.ok) throw new Error(`Standard analysis request failed (${response.status})`);
  return (await response.json()) as T;
}

export function getStandardSubjects(
  sessionId: string,
  includeTest: boolean,
  signal?: AbortSignal,
): Promise<StandardSubjectHierarchyV2> {
  const params = new URLSearchParams({ include_test: String(includeTest) });
  return getJson(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/standard-subjects?${params}`,
    signal,
  );
}

export function getStandardSubject(
  sessionId: string,
  subjectId: string,
  includeTest: boolean,
  signal?: AbortSignal,
): Promise<StandardSubjectDetailV2> {
  const params = new URLSearchParams({ include_test: String(includeTest) });
  return getJson(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/standard-subjects/${encodeURIComponent(subjectId)}?${params}`,
    signal,
  );
}

export function getStandardView(
  sessionId: string,
  subjectId: string,
  view: StandardViewKindV2,
  includeTest: boolean,
  signal?: AbortSignal,
): Promise<StandardPlotViewV2> {
  const params = new URLSearchParams({
    include_test: String(includeTest),
    maximum_points: "512",
  });
  return getJson(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/standard-subjects/${encodeURIComponent(subjectId)}/views/${view}?${params}`,
    signal,
  );
}
