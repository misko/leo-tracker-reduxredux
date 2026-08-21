import type {
  StandardPlotViewV2,
  StandardSubjectDetailV2,
  StandardSubjectHierarchyV2,
  StandardViewKindV2,
} from "./standard-contracts";

export interface StandardInvestigationImageV1 {
  image_id: string;
  subject_id: string;
  label: string;
  analysis_variant: "wide-fine-upper-edge";
  relative_path: string;
  byte_size: number;
  digest: string;
}

export interface StandardInvestigationGalleryV1 {
  schema_version: 1;
  session_id: string;
  title: string;
  status: "exploratory";
  candidate_only: true;
  specificity_claimed: false;
  payload_decoded: false;
  images: StandardInvestigationImageV1[];
}

export type AnalysisLane = "standard" | "research";

function subjectCollection(lane: AnalysisLane) {
  return lane === "standard" ? "standard-subjects" : "research-subjects";
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: "GET", signal });
  if (!response.ok) throw new Error(`Standard analysis request failed (${response.status})`);
  return (await response.json()) as T;
}

export function getStandardSubjects(
  sessionId: string,
  includeTest: boolean,
  signal?: AbortSignal,
  lane: AnalysisLane = "standard",
): Promise<StandardSubjectHierarchyV2> {
  const params = new URLSearchParams({ include_test: String(includeTest) });
  return getJson(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/${subjectCollection(lane)}?${params}`,
    signal,
  );
}

export function getStandardSubject(
  sessionId: string,
  subjectId: string,
  includeTest: boolean,
  signal?: AbortSignal,
  lane: AnalysisLane = "standard",
): Promise<StandardSubjectDetailV2> {
  const params = new URLSearchParams({ include_test: String(includeTest) });
  return getJson(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/${subjectCollection(lane)}/${encodeURIComponent(subjectId)}?${params}`,
    signal,
  );
}

export function getStandardView(
  sessionId: string,
  subjectId: string,
  view: StandardViewKindV2,
  includeTest: boolean,
  signal?: AbortSignal,
  lane: AnalysisLane = "standard",
): Promise<StandardPlotViewV2> {
  const params = new URLSearchParams({
    include_test: String(includeTest),
    maximum_points: "512",
  });
  return getJson(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/${subjectCollection(lane)}/${encodeURIComponent(subjectId)}/views/${view}?${params}`,
    signal,
  );
}

export function standardPngUrl(
  sessionId: string,
  subjectId: string,
  view: StandardViewKindV2,
  includeTest: boolean,
  lane: AnalysisLane = "standard",
): string {
  const params = new URLSearchParams({
    include_test: String(includeTest),
    maximum_points: "2048",
  });
  return `/api/v2/recordings/${encodeURIComponent(sessionId)}/${subjectCollection(lane)}/${encodeURIComponent(subjectId)}/views/${view}.png?${params}`;
}

export type StandardTrajectoryArtifactName = "cfo-raw" | "cfo-dealiased" | "cfo-final" | "cfo-alternate";

export function standardTrajectoryArtifactUrl(
  sessionId: string,
  subjectId: string,
  artifactName: StandardTrajectoryArtifactName,
  lane: AnalysisLane = "standard",
): string {
  return `/api/v2/recordings/${encodeURIComponent(sessionId)}/${subjectCollection(lane)}/${encodeURIComponent(subjectId)}/artifacts/${artifactName}.png`;
}

export async function getStandardInvestigation(
  sessionId: string,
  signal?: AbortSignal,
): Promise<StandardInvestigationGalleryV1 | null> {
  const response = await fetch(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/standard-investigations`,
    { method: "GET", signal },
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Standard investigation request failed (${response.status})`);
  return (await response.json()) as StandardInvestigationGalleryV1;
}

export function standardInvestigationPngUrl(sessionId: string, imageId: string): string {
  return `/api/v2/recordings/${encodeURIComponent(sessionId)}/standard-investigations/${encodeURIComponent(imageId)}.png`;
}
