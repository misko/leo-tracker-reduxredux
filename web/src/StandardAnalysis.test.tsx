import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { StandardAnalysis } from "./StandardAnalysis";
import type {
  StandardPlotViewV2,
  StandardSubjectDetailV2,
  StandardSubjectHierarchyV2,
  StandardSubjectSummaryV2,
  StandardViewKindV2,
} from "./standard-contracts";

const sha = "0123456789abcdef0123456789abcdef01234567";
const release = {
  authoritative_pipeline_release_id: sha,
  source_revision: sha,
  family: "standard-glrt64-v2" as const,
  display_version: "2.0.0",
  graph_digest: "a".repeat(64),
  configuration_digest: "b".repeat(64),
  environment_digest: "c".repeat(64),
};
const eligibility = {
  source_type: "TEST" as const,
  capture_committed: true,
  capture_healthy: true,
  automatic_eligible: false,
  explicit_eligible: true,
  promotion_allowed: false,
  evidence_only: true,
  exclusion_tags: [],
  reason: "Reviewed TEST corpus is explicit, non-current evidence only",
};
const paths = [0, 1].flatMap((radio) => [0, 1].map((receiver) => ({
  subject_id: `path:radio${radio}:rx${receiver}`,
  path_id: `radio${radio}:rx${receiver}`,
  radio_id: `radio${radio}`,
  radio_label: `Radio${radio}`,
  receiver_id: receiver,
  receiver_label: `RX${receiver}`,
  scope: {
    schema_version: 1 as const,
    kind: "receiver_path" as const,
    session_id: "T1",
    stream_id: `stream-${radio}`,
    radio_id: null,
    receiver_id: receiver,
    synchronization_inventory_digest: null,
  },
  scope_digest: "d".repeat(64),
})));

function subject(
  id: string,
  label: string,
  kind: "paired" | "radio" | "receiver_path",
  selectedPaths = paths,
  state: StandardSubjectSummaryV2["state"] = "complete",
): StandardSubjectSummaryV2 {
  return {
    subject_id: id,
    session_id: "T1",
    subject_kind: kind,
    label,
    derived: kind !== "receiver_path",
    receiver_paths: selectedPaths,
    expected_path_count: selectedPaths.length,
    completed_path_count: selectedPaths.length,
    child_subject_ids: kind === "paired" ? ["radio:radio0", "radio:radio1"] : kind === "radio" ? selectedPaths.map((item) => `path:${item.path_id}`) : [],
    state,
    ordinary_current: false,
    state_reasons: [],
    pipeline_release: release,
    desired_pipeline_release_id: sha,
    reuse: {
      computed_stage_count: 1,
      reused_stage_count: 8,
      recompute_stage_count: 0,
      blocked_stage_count: 0,
      reused_from_run_ids: ["run-source"],
      reason: "exact cache hit",
    },
    eligibility,
    evidence_label: "candidate evidence only",
  };
}

const pair = subject("pair:radio0:radio1", "Paired Radio0 + Radio1", "paired");
const hierarchy: StandardSubjectHierarchyV2 = {
  schema_version: 2,
  session_id: "T1",
  source_type: "TEST",
  eligibility,
  generated_at: "2026-08-19T18:00:00Z",
  rows: [
    pair,
    subject("radio:radio0", "Radio0", "radio", paths.slice(0, 2), "partial"),
    subject("radio:radio1", "Radio1", "radio", paths.slice(2), "failed"),
  ],
};
const domain = {
  absolute_start_utc: "2026-08-19T17:00:00Z",
  absolute_end_utc: "2026-08-19T17:01:00Z",
  elapsed_start_s: 0,
  elapsed_end_s: 60,
  time_unit: "s" as const,
  timing_uncertainty_s: 0.002,
};
const viewKinds: StandardViewKindV2[] = ["quality", "power", "waterfall", "glrt64", "cfo_trajectory", "qam"];
const detail: StandardSubjectDetailV2 = {
  schema_version: 2,
  subject: pair,
  time_domain: domain,
  receiver_path_expansions: paths.map((path) => subject(`path:${path.path_id}`, `${path.radio_label} ${path.receiver_label}`, "receiver_path", [path])),
  receiver_path_evidence: paths.map((path) => ({
    receiver_path: path,
    coverage_fraction: 1,
    analyzed_seconds: 60,
    declared_seconds: 60,
    quality_state: "complete",
    clipped_fraction: .00001,
    continuity_gap_count: 0,
    calibration_state: "applicable",
    calibration_id: `calibration:${path.path_id}`,
    calibration_digest: "c".repeat(64),
    frequency_uncertainty_hz: 125,
    reason: "full coverage",
  })),
  stage_source_count: 2,
  stages: [
    { stage_key: "path-pilot-scan", subject_id: pair.subject_id, disposition: "reused", runtime_seconds: 0.1, output_digest: "a".repeat(64), reused_from_run_id: "run-source", reason: "exact hit" },
    { stage_key: "paired-report", subject_id: pair.subject_id, disposition: "computed", runtime_seconds: 0.2, output_digest: "b".repeat(64), reused_from_run_id: null, reason: "children ready" },
  ],
  stages_truncated: false,
  trajectory_source_count: 1,
  trajectories: [{
    trajectory_id: "track-1", receiver_path_id: "radio0:rx0", algorithm: "glrt64", degree: 2,
    reference_time_s: 1, coefficients_hz: [2, -120, 253443.36], support_count: 27,
    residual_rms_hz: 312.5, bic: 84.1, selected_for_correction: true,
    corrected_glrt64_gain: 0.142, status: "selected", rejection_reason: null,
  }],
  trajectories_truncated: false,
  views: viewKinds.map((view_kind) => ({ view_kind, state: "available", href: `/view/${view_kind}`, source_point_count: 3, reason: "available" })),
  limitations: ["Candidate evidence only; source identity is unassessed; no payload recovery is claimed"],
};

function metricView(kind: StandardViewKindV2): StandardPlotViewV2 {
  return {
    schema_version: 2, session_id: "T1", subject_id: pair.subject_id, view_kind: kind,
    state: "available", time_domain: domain, source_point_count: 3, returned_point_count: 3,
    receiver_path_ids: paths.map((path) => path.path_id),
    horizontal_axis: kind === "waterfall"
      ? { axis_id: "frequency_hz", label: "Baseband frequency", unit: "Hz", full_source_min: 200000, full_source_max: 300000 }
      : { axis_id: "time", label: "Shared elapsed time", unit: "s", full_source_min: 0, full_source_max: 60 },
    vertical_axis: kind === "waterfall"
      ? { axis_id: "time", label: "Shared elapsed time", unit: "s", full_source_min: 0, full_source_max: 60 }
      : { axis_id: "metric_value", label: kind, unit: "response", full_source_min: 0, full_source_max: 1 },
    color_axis: kind === "waterfall"
      ? { axis_id: "power_db", label: "Power", unit: "dB", full_source_min: -100, full_source_max: -20 }
      : null,
    source_extrema: {
      schema_version: 2,
      source_artifact_digest: "a".repeat(64),
      source_content_digest: "b".repeat(64),
      source_point_count: 3,
      axes: kind === "waterfall"
        ? [
          { axis_id: "frequency_hz", source_min: 200000, source_max: 300000 },
          { axis_id: "power_db", source_min: -100, source_max: -20 },
        ]
        : [{ axis_id: "metric_value", source_min: 0, source_max: 1 }],
      lanes: [{
        receiver_path_id: "radio0:rx0",
        source_point_count: 3,
        axes: kind === "waterfall"
          ? [
            { axis_id: "frequency_hz", source_min: 200000, source_max: 300000 },
            { axis_id: "power_db", source_min: -100, source_max: -20 },
          ]
          : [{ axis_id: "metric_value", source_min: 0, source_max: 1 }],
      }],
      canonical_digest: "c".repeat(64),
    },
    truncated: false,
    series: kind === "waterfall" || kind === "cfo_trajectory" ? [] : [{
      series_id: `${kind}:rx0`, receiver_path_id: "radio0:rx0", label: kind,
      unit: "response", source_point_count: 3,
      points: [{ time_s: 0, value: .1 }, { time_s: 30, value: .3 }, { time_s: 60, value: .2 }],
      truncated: false, source_min: .1, source_max: .3,
    }],
    waterfall_cells: kind === "waterfall" ? [
      { receiver_path_id: "radio0:rx0", time_s: 0, frequency_hz: 250000, power_db: -70 },
      { receiver_path_id: "radio0:rx1", time_s: 30, frequency_hz: 255000, power_db: -60 },
      { receiver_path_id: "radio1:rx0", time_s: 60, frequency_hz: 260000, power_db: -50 },
    ] : [],
    cfo_observations: [], trajectory_curves: [], reason: "bounded fixture",
  };
}

afterEach(() => vi.restoreAllMocks());

test("rejects crossed eligibility reason truth before rendering subjects", async () => {
  const crossedHierarchy: StandardSubjectHierarchyV2 = {
    ...hierarchy,
    eligibility: {
      ...hierarchy.eligibility,
      reason: "Committed ordinary LIVE capture is Standard eligible",
    },
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(
    JSON.stringify(crossedHierarchy),
    { status: 200, headers: { "Content-Type": "application/json" } },
  )));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Standard eligibility reason does not match its truth projection",
  );
});

test("rejects current subjects carrying stale-coded reasons", async () => {
  const currentWithStaleReason: StandardSubjectSummaryV2 = {
    ...pair,
    state: "current",
    state_reasons: [{
      code: "product_unavailable",
      message: "Product is unavailable",
      affected_stage_keys: [],
      affected_subject_ids: [],
    }],
  };
  const crossedHierarchy: StandardSubjectHierarchyV2 = {
    ...hierarchy,
    rows: [currentWithStaleReason, ...hierarchy.rows.slice(1)],
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(
    JSON.stringify(crossedHierarchy),
    { status: 200, headers: { "Content-Type": "application/json" } },
  )));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Standard subject state and stale reasons are incompatible",
  );
});

test("shows four independent receiver tabs plus a combined PNG gallery", async () => {
  const pathDetail = (index: number): StandardSubjectDetailV2 => ({
    ...detail,
    subject: detail.receiver_path_expansions[index],
    receiver_path_expansions: [detail.receiver_path_expansions[index]],
    receiver_path_evidence: [detail.receiver_path_evidence[index]],
  });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    let body: StandardSubjectHierarchyV2 | StandardSubjectDetailV2 = hierarchy;
    if (url.includes("pair%3Aradio0%3Aradio1")) body = detail;
    if (url.includes("path%3Aradio0%3Arx0")) body = pathDetail(0);
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  const tabs = await screen.findByRole("navigation", { name: "Receiver path image tabs" });
  expect(within(tabs).getAllByRole("button")).toHaveLength(5);
  for (const label of ["Radio0 RX0", "Radio0 RX1", "Radio1 RX0", "Radio1 RX1"]) {
    expect(within(tabs).getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
  }
  expect(within(tabs).getByRole("button", { name: /Combined 4-path/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getAllByRole("img")).toHaveLength(5);
  expect(screen.queryByRole("img", { name: /Known-pilot QAM/ })).not.toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Waterfall.*Paired/ })).toHaveAttribute(
    "src",
    expect.stringContaining("/views/waterfall.png?"),
  );
  expect(screen.getAllByRole("link", { name: "Open PNG" })).toHaveLength(5);
  expect(screen.getByText("frequency → · elapsed time ↓ · color = power")).toBeInTheDocument();

  fireEvent.click(within(tabs).getByRole("button", { name: /Radio0 RX0/ }));
  await waitFor(() => expect(screen.getByRole("img", { name: /Waterfall.*Radio0 RX0/ })).toHaveAttribute(
    "src",
    expect.stringContaining("path%3Aradio0%3Arx0/views/waterfall.png"),
  ));
});
