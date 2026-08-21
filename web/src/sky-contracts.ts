// Hand-maintained mirrors of the Python sky contracts, in the manner of
// contracts.generated.ts. tests/api/test_contract_boundary.py asserts the
// fragments below so the two cannot drift apart silently.

export const SKY_SCHEMA_VERSION = 1;

export interface SkySiteRowV1 {
  schema_version: 1;
  name: string;
  label: string;
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number;
  position_uncertainty_m: number;
  provenance: string;
}

export interface SkySiteListV1 {
  schema_version: 1;
  sites: SkySiteRowV1[];
}

export interface SkySnapshotRowV1 {
  schema_version: 1;
  provider: "space-track" | "huggingface";
  collected_utc: string;
  collected_utc_ns: number;
  digest: string;
  byte_size: number;
}

export interface SkySnapshotListV1 {
  schema_version: 1;
  archive_root: string;
  returned_count: number;
  source_count: number;
  truncated: boolean;
  snapshots: SkySnapshotRowV1[];
}

export interface TleSnapshotRefV1 {
  schema_version: 1;
  provider: "space-track" | "huggingface";
  collected_utc_ns: number;
  digest: string;
  object_count: number;
}

export interface SkyWindowV1 {
  schema_version: 1;
  anchor_utc_ns: number;
  half_width_s: number;
  sample_count: number;
}

export interface GlobeTrackV1 {
  schema_version: 1;
  catalog_number: number;
  object_name: string;
  /** Flattened [x,y,z, x,y,z, ...] in units of quantum_km, three per knot. */
  positions: number[];
}

export interface GlobeFrameSetV1 {
  schema_version: 1;
  window: SkyWindowV1;
  knot_utc_ns: number[];
  quantum_km: number;
  earth_radius_km: number;
  snapshot: TleSnapshotRefV1;
  tracks: GlobeTrackV1[];
  returned_object_count: number;
  source_object_count: number;
  truncated: boolean;
}

export interface SkyViewTrackV1 {
  schema_version: 1;
  catalog_number: number;
  object_name: string;
  azimuth_deg: number[];
  elevation_deg: number[];
  range_km: number[];
  peak_elevation_deg: number;
}

export interface SkyViewFrameSetV1 {
  schema_version: 1;
  observer: {
    schema_version: 1;
    latitude_deg: number;
    longitude_deg: number;
    altitude_m: number;
    label: string;
  };
  window: SkyWindowV1;
  knot_utc_ns: number[];
  horizon_mask_deg: number;
  snapshot: TleSnapshotRefV1;
  tracks: SkyViewTrackV1[];
  returned_object_count: number;
  source_object_count: number;
  truncated: boolean;
}

export interface OrbitElementsV1 {
  schema_version: 1;
  element_epoch_utc_ns: number;
  inclination_deg: number;
  right_ascension_deg: number;
  eccentricity: number;
  argument_of_perigee_deg: number;
  mean_anomaly_deg: number;
  mean_motion_rev_day: number;
  period_minutes: number;
  perigee_altitude_km: number;
  apogee_altitude_km: number;
}

export interface SkyViewObjectDetailV1 {
  schema_version: 1;
  observer: SkyViewFrameSetV1["observer"];
  window: SkyWindowV1;
  knot_utc_ns: number[];
  snapshot: TleSnapshotRefV1;
  catalog_number: number;
  object_name: string;
  orbit: OrbitElementsV1;
  downlink_frequency_hz: number;
  range_rate_km_s: number[];
  doppler_shift_hz: number[];
}
