import type {
  GlobeFrameSetV1,
  SkySiteListV1,
  SkySnapshotListV1,
  SkyViewFrameSetV1,
  SkyViewObjectDetailV1,
} from "./sky-contracts";

export class SkyUnavailableError extends Error {}

async function getSky<T>(path: string, params: Record<string, string | number>, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams(
    Object.entries(params).map(([key, value]) => [key, String(value)]),
  );
  const response = await fetch(`${path}?${query}`, { method: "GET", signal });
  if (response.status === 503) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new SkyUnavailableError(body?.detail ?? "Sky prediction is unavailable.");
  }
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getSkySites(signal?: AbortSignal): Promise<SkySiteListV1> {
  return getSky<SkySiteListV1>("/api/v1/sky/sites", {}, signal);
}

export function getSkySnapshots(signal?: AbortSignal): Promise<SkySnapshotListV1> {
  return getSky<SkySnapshotListV1>("/api/v1/sky/snapshots", {}, signal);
}

export function getGlobe(
  anchorUtcNs: number,
  limit: number,
  signal?: AbortSignal,
): Promise<GlobeFrameSetV1> {
  return getSky<GlobeFrameSetV1>("/api/v1/sky/globe", { at: anchorUtcNs, limit }, signal);
}

export function getSkyDome(
  anchorUtcNs: number,
  latitude: number,
  longitude: number,
  altitude: number,
  maskDeg: number,
  signal?: AbortSignal,
): Promise<SkyViewFrameSetV1> {
  return getSky<SkyViewFrameSetV1>(
    "/api/v1/sky/skyview",
    { at: anchorUtcNs, lat: latitude, lon: longitude, alt: altitude, mask: maskDeg },
    signal,
  );
}

export function getSkyObjectDetail(
  anchorUtcNs: number,
  latitude: number,
  longitude: number,
  altitude: number,
  catalogNumber: number,
  downlinkHz: number,
  provider: string,
  snapshotDigest: string,
  signal?: AbortSignal,
): Promise<SkyViewObjectDetailV1> {
  return getSky<SkyViewObjectDetailV1>(
    "/api/v1/sky/skyview/object",
    {
      at: anchorUtcNs,
      lat: latitude,
      lon: longitude,
      alt: altitude,
      catalog: catalogNumber,
      downlink_hz: downlinkHz,
      provider,
      snapshot: snapshotDigest,
    },
    signal,
  );
}
