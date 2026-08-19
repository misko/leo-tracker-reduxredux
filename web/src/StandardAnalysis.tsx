import { useEffect, useMemo, useState } from "react";

import { getStandardSubject, getStandardSubjects, getStandardView } from "./standard-api";
import type {
  StandardPlotViewV2,
  StandardSubjectDetailV2,
  StandardSubjectHierarchyV2,
  StandardSubjectSummaryV2,
  StandardViewKindV2,
} from "./standard-contracts";
import "./standard-analysis.css";

const viewLabels: Record<StandardViewKindV2, string> = {
  quality: "Quality",
  power: "Power",
  waterfall: "Waterfall",
  glrt64: "GLRT64 response",
  cfo_trajectory: "CFO trajectories",
  qam: "Known-pilot QAM",
};

export function StandardAnalysis({
  sessionId,
  includeTest,
}: {
  sessionId: string;
  includeTest: boolean;
}) {
  const [hierarchy, setHierarchy] = useState<StandardSubjectHierarchyV2 | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<StandardSubjectDetailV2 | null>(null);
  const [viewKind, setViewKind] = useState<StandardViewKindV2>("glrt64");
  const [plot, setPlot] = useState<StandardPlotViewV2 | null>(null);
  const [cursor, setCursor] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setHierarchy(null);
    setDetail(null);
    setPlot(null);
    getStandardSubjects(sessionId, includeTest, controller.signal)
      .then((result) => {
        validateHierarchyTruth(result);
        setHierarchy(result);
        setSelectedId(result.rows[0]?.subject_id ?? null);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [includeTest, sessionId]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setDetail(null);
    setPlot(null);
    getStandardSubject(sessionId, selectedId, includeTest, controller.signal)
      .then((result) => {
        validateSubjectTruth(result.subject);
        result.receiver_path_expansions.forEach(validateSubjectTruth);
        setDetail(result);
        setCursor(result.time_domain.elapsed_start_s);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [includeTest, selectedId, sessionId]);

  useEffect(() => {
    if (!detail || detail.subject.subject_id !== selectedId) return;
    const descriptor = detail.views.find((item) => item.view_kind === viewKind);
    if (!descriptor || descriptor.state === "unavailable") {
      setPlot(null);
      return;
    }
    const controller = new AbortController();
    setPlot(null);
    getStandardView(sessionId, selectedId, viewKind, includeTest, controller.signal)
      .then((result) => {
        if (!sameTimeDomain(result.time_domain, detail.time_domain)) {
          throw new Error("Plot time domain does not match the selected subject");
        }
        const expectedLanes = detail.subject.receiver_paths.map((path) => path.path_id);
        if (!sameOrderedValues(result.receiver_path_ids, expectedLanes)) {
          throw new Error("Plot receiver paths do not match the selected subject");
        }
        setPlot(result);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [detail, includeTest, selectedId, sessionId, viewKind]);

  if (error) return <section className="standard-error" role="alert">{error}</section>;
  if (!hierarchy) return <section className="standard-loading">Loading Standard subjects…</section>;
  return (
    <section className="standard-analysis" aria-label="Standard GLRT64 analysis">
      <header className="standard-heading">
        <div><span>STANDARD GLRT64 PIPELINE</span><h3>Receiver, radio & paired evidence</h3></div>
        <EligibilityBadge hierarchy={hierarchy} />
      </header>
      <SubjectTable
        rows={hierarchy.rows}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />
      {!detail ? <p>Loading selected subject shell…</p> : (
        <SubjectWorkspace
          detail={detail}
          plot={plot}
          viewKind={viewKind}
          onView={setViewKind}
          cursor={cursor}
          onCursor={setCursor}
        />
      )}
    </section>
  );
}

const canonicalExclusionTags = ["QUALIFICATION", "CALIBRATION", "ACCEPTANCE"] as const;

function validateHierarchyTruth(hierarchy: StandardSubjectHierarchyV2) {
  validateEligibilityTruth(hierarchy.eligibility);
  if (hierarchy.source_type !== hierarchy.eligibility.source_type) {
    throw new Error("Standard eligibility source does not match the hierarchy");
  }
  hierarchy.rows.forEach((row) => {
    validateEligibilityTruth(row.eligibility);
    validateSubjectTruth(row);
  });
}

function validateEligibilityTruth(eligibility: StandardSubjectHierarchyV2["eligibility"]) {
  const orderedExclusions = canonicalExclusionTags.filter((tag) => eligibility.exclusion_tags.includes(tag));
  if (!sameOrderedValues(eligibility.exclusion_tags, orderedExclusions)) {
    throw new Error("Standard eligibility exclusions are not canonical");
  }
  const ready = eligibility.capture_committed
    && eligibility.capture_healthy
    && eligibility.exclusion_tags.length === 0;
  const isTest = eligibility.source_type === "TEST";
  if (
    eligibility.automatic_eligible !== (ready && !isTest)
    || eligibility.explicit_eligible !== ready
    || eligibility.promotion_allowed !== (ready && !isTest)
    || eligibility.evidence_only !== isTest
  ) {
    throw new Error("Standard eligibility state does not match source readiness");
  }
  let expectedReason: string;
  if (!eligibility.capture_committed) {
    expectedReason = "Capture is not committed; Standard analysis eligibility fails closed";
  } else if (!eligibility.capture_healthy) {
    expectedReason = "Capture health is unavailable or failed; Standard analysis eligibility fails closed";
  } else if (eligibility.exclusion_tags.length > 0) {
    expectedReason = `Excluded from Standard by evidence-lane tag(s): ${eligibility.exclusion_tags.join(", ")}`;
  } else if (isTest) {
    expectedReason = "Reviewed TEST corpus is explicit, non-current evidence only";
  } else {
    expectedReason = `Committed ordinary ${eligibility.source_type} capture is Standard eligible`;
  }
  if (eligibility.reason !== expectedReason) {
    throw new Error("Standard eligibility reason does not match its truth projection");
  }
}

function validateSubjectTruth(subject: StandardSubjectSummaryV2) {
  validateEligibilityTruth(subject.eligibility);
  const staleCodedReasons = subject.state_reasons.filter((reason) => reason.code !== null);
  if (
    (subject.state === "stale" && staleCodedReasons.length !== subject.state_reasons.length)
    || (subject.state === "stale" && subject.state_reasons.length === 0)
    || (subject.state !== "stale" && staleCodedReasons.length > 0)
  ) {
    throw new Error("Standard subject state and stale reasons are incompatible");
  }
}

function sameTimeDomain(
  left: StandardSubjectDetailV2["time_domain"],
  right: StandardSubjectDetailV2["time_domain"],
) {
  return left.absolute_start_utc === right.absolute_start_utc
    && left.absolute_end_utc === right.absolute_end_utc
    && left.elapsed_start_s === right.elapsed_start_s
    && left.elapsed_end_s === right.elapsed_end_s
    && left.time_unit === right.time_unit
    && left.timing_uncertainty_s === right.timing_uncertainty_s;
}

function sameOrderedValues(left: string[], right: string[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function EligibilityBadge({ hierarchy }: { hierarchy: StandardSubjectHierarchyV2 }) {
  const eligibility = hierarchy.eligibility;
  return (
    <div className={`standard-eligibility ${eligibility.evidence_only ? "test" : "ordinary"}`}>
      <strong>{hierarchy.source_type}{eligibility.evidence_only ? " · EVIDENCE ONLY" : " · ORDINARY"}</strong>
      <span>{eligibility.reason}</span>
      <small>{eligibility.capture_committed ? "Committed" : "Not committed"} · {eligibility.capture_healthy ? "Healthy" : "Health unavailable"}</small>
      <small>{eligibility.promotion_allowed ? "May become ordinary current" : "Cannot replace ordinary current analysis"}</small>
    </div>
  );
}

function SubjectTable({
  rows,
  selectedId,
  onSelect,
}: {
  rows: StandardSubjectSummaryV2[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="standard-subject-table">
      <table aria-label="Analysis subjects">
        <thead><tr>
          <th scope="col">Type</th><th scope="col">Subject</th><th scope="col">Paths</th>
          <th scope="col">Pipeline</th><th scope="col">State / evidence</th><th scope="col">Reuse</th>
        </tr></thead>
        <tbody>{rows.map((row) => (
          <tr
            className={`standard-subject-row ${row.subject_id === selectedId ? "selected" : ""}`}
            key={row.subject_id}
          >
            <td>{row.subject_kind === "paired" ? "Derived pair" : "Derived radio"}</td>
            <td><button type="button" onClick={() => onSelect(row.subject_id)}>{row.label}</button></td>
            <td>{row.completed_path_count} / {row.expected_path_count}</td>
            <td><span className="standard-release">
              {row.pipeline_release ? `${row.pipeline_release.family} ${row.pipeline_release.display_version}` : "Not analyzed"}
              <code>{row.pipeline_release?.authoritative_pipeline_release_id ?? row.desired_pipeline_release_id}</code>
            </span></td>
            <td><span className={`standard-state ${row.state}`}>{row.state}</span>
              {row.eligibility.evidence_only ? <span className="standard-evidence">EVIDENCE ONLY</span> : null}
            </td>
            <td>{row.reuse.reused_stage_count} reused · {row.reuse.recompute_stage_count} redo</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function SubjectWorkspace({
  detail,
  plot,
  viewKind,
  onView,
  cursor,
  onCursor,
}: {
  detail: StandardSubjectDetailV2;
  plot: StandardPlotViewV2 | null;
  viewKind: StandardViewKindV2;
  onView: (view: StandardViewKindV2) => void;
  cursor: number;
  onCursor: (time: number) => void;
}) {
  const domain = detail.time_domain;
  return (
    <div className="standard-workspace">
      <div className="standard-subject-meta">
        <div><span>Selected</span><strong>{detail.subject.label}</strong></div>
        <div><span>Absolute interval</span><strong>{domain.absolute_start_utc} – {domain.absolute_end_utc}</strong></div>
        <div><span>Timing uncertainty</span><strong>±{domain.timing_uncertainty_s.toFixed(6)} s</strong></div>
      </div>
      {detail.subject.state_reasons.map((reason) => (
        <p className="standard-reason" key={`${reason.code}-${reason.message}`}>{reason.code}: {reason.message}</p>
      ))}
      <div className="standard-path-expansions" aria-label="Receiver path expansions">
        {detail.receiver_path_expansions.map((path) => {
          const evidence = detail.receiver_path_evidence.find((item) => item.receiver_path.path_id === path.receiver_paths[0]?.path_id);
          return <article key={path.subject_id}>
            <strong>{path.label}</strong><span><span className={`standard-state ${path.state}`}>{path.state}</span>
              {path.eligibility.evidence_only ? <span className="standard-evidence">EVIDENCE ONLY</span> : null}
              {evidence ? ` · ${(evidence.coverage_fraction * 100).toFixed(1)}% coverage` : " · coverage unavailable"}</span>
            <small>{path.receiver_paths[0]?.scope.stream_id} · RX{path.receiver_paths[0]?.scope.receiver_id}</small>
            <small>{evidence?.calibration_state === "applicable" ? `${evidence.calibration_id} · ±${evidence.frequency_uncertainty_hz} Hz` : "calibration unavailable"}</small>
            <small>{evidence?.quality_state ?? "quality unavailable"} · {evidence?.continuity_gap_count ?? "—"} gaps</small>
          </article>
        })}
      </div>
      <nav className="standard-view-tabs" aria-label="Standard analysis views">
        {detail.views.map((view) => (
          <button
            type="button"
            key={view.view_kind}
            aria-current={view.view_kind === viewKind ? "page" : undefined}
            disabled={view.state === "unavailable"}
            onClick={() => onView(view.view_kind)}
          >{viewLabels[view.view_kind]}</button>
        ))}
      </nav>
      <SharedTimeControl domain={domain} cursor={cursor} onCursor={onCursor} />
      {plot ? <StandardPlot plot={plot} cursor={cursor} /> : <p>Loading bounded {viewLabels[viewKind]} data…</p>}
      <TrajectoryTable detail={detail} />
      <StageTable detail={detail} />
      <div className="standard-limitations">
        {detail.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}
      </div>
    </div>
  );
}

function SharedTimeControl({
  domain,
  cursor,
  onCursor,
}: {
  domain: StandardSubjectDetailV2["time_domain"];
  cursor: number;
  onCursor: (value: number) => void;
}) {
  return (
    <label className="standard-time-control">
      <span>Shared time cursor: {cursor.toFixed(3)} s</span>
      <input
        aria-label="Shared analysis time cursor"
        type="range"
        min={domain.elapsed_start_s}
        max={domain.elapsed_end_s}
        step="0.001"
        value={cursor}
        onChange={(event) => onCursor(Number(event.target.value))}
      />
      <small>{domain.elapsed_start_s.toFixed(3)} s</small><small>{domain.elapsed_end_s.toFixed(3)} s</small>
    </label>
  );
}

function StandardPlot({ plot, cursor }: { plot: StandardPlotViewV2; cursor: number }) {
  if (plot.state === "unavailable") return <p>{plot.reason}</p>;
  return <div>
    <div className="standard-lanes"><strong>Receiver paths:</strong>
      <ul aria-label="Receiver path lanes">
        {plot.receiver_path_ids.map((pathId, index) => (
          <li
            aria-label={`Lane ${index + 1}: ${pathId}`}
            className={`standard-lane lane-${index}`}
            key={pathId}
          >
            <span>Lane {index + 1}</span><code>{pathId}</code>
          </li>
        ))}
      </ul>
    </div>
    {plot.view_kind === "waterfall" ? <WaterfallView plot={plot} cursor={cursor} />
      : plot.view_kind === "cfo_trajectory" ? <CfoView plot={plot} cursor={cursor} />
      : <MetricView plot={plot} cursor={cursor} />}
  </div>;
}

function MetricView({ plot, cursor }: { plot: StandardPlotViewV2; cursor: number }) {
  const min = plot.vertical_axis.full_source_min;
  const max = plot.vertical_axis.full_source_max;
  const span = max - min || 1;
  const domain = plot.time_domain;
  const x = (time: number) => (time - domain.elapsed_start_s) / (domain.elapsed_end_s - domain.elapsed_start_s) * 1000;
  return (
    <figure className="standard-plot">
      <figcaption>{viewLabels[plot.view_kind]} · {plot.returned_point_count}/{plot.source_point_count} points</figcaption>
      <svg role="img" aria-label={`${viewLabels[plot.view_kind]} versus shared time`} data-axis-min={min} data-axis-max={max} viewBox="0 0 1000 240" preserveAspectRatio="none">
        {plot.series.map((series) => (
          <polyline
            key={series.series_id}
            className={`standard-series standard-lane lane-${plot.receiver_path_ids.indexOf(series.receiver_path_id)}`}
            data-receiver-path-id={series.receiver_path_id}
            points={series.points.map((point) => `${x(point.time_s)},${220 - (point.value - min) / span * 200}`).join(" ")}
          />
        ))}
        <line className="standard-cursor" x1={x(cursor)} x2={x(cursor)} y1="0" y2="240" />
      </svg>
      <small>Time (s), shared domain · {plot.vertical_axis.label} ({plot.vertical_axis.unit}) {min} to {max} · {plot.reason}</small>
    </figure>
  );
}

function WaterfallView({ plot, cursor }: { plot: StandardPlotViewV2; cursor: number }) {
  const minFrequency = plot.horizontal_axis.full_source_min;
  const maxFrequency = plot.horizontal_axis.full_source_max;
  const minPower = plot.color_axis?.full_source_min ?? 0;
  const maxPower = plot.color_axis?.full_source_max ?? 1;
  const domain = plot.time_domain;
  const y = (time: number) => (time - domain.elapsed_start_s) / (domain.elapsed_end_s - domain.elapsed_start_s) * 240;
  return (
    <figure className="standard-plot">
      <figcaption>Waterfall · frequency horizontal, shared elapsed time vertical</figcaption>
      <svg role="img" aria-label="Frequency versus shared time waterfall" data-frequency-min={minFrequency} data-frequency-max={maxFrequency} data-power-min={minPower} data-power-max={maxPower} viewBox="0 0 1000 240" preserveAspectRatio="none">
        {plot.waterfall_cells.map((cell, index) => (
          <circle
            key={`${cell.time_s}-${cell.frequency_hz}-${index}`}
            data-receiver-path-id={cell.receiver_path_id}
            className={`standard-lane lane-${plot.receiver_path_ids.indexOf(cell.receiver_path_id)}`}
            cx={(cell.frequency_hz - minFrequency) / (maxFrequency - minFrequency || 1) * 1000}
            cy={y(cell.time_s)}
            r="8"
            fill={`hsl(${220 - (cell.power_db - minPower) / (maxPower - minPower || 1) * 200} 80% 55%)`}
          />
        ))}
        <line className="standard-cursor horizontal" x1="0" x2="1000" y1={y(cursor)} y2={y(cursor)} />
      </svg>
      <small>Frequency (Hz) → · elapsed time (s) ↓ · power (dB) color</small>
    </figure>
  );
}

function CfoView({ plot, cursor }: { plot: StandardPlotViewV2; cursor: number }) {
  const domain = plot.time_domain;
  const min = plot.vertical_axis.full_source_min;
  const max = plot.vertical_axis.full_source_max;
  const x = (time: number) => (time - domain.elapsed_start_s) / (domain.elapsed_end_s - domain.elapsed_start_s) * 1000;
  const y = (value: number) => 220 - (value - min) / (max - min || 1) * 200;
  return (
    <figure className="standard-plot">
      <figcaption>GLRT64 CFO observations and linear/quadratic/cubic candidate trajectories</figcaption>
      <svg role="img" aria-label="Candidate CFO trajectories versus shared time" data-axis-min={min} data-axis-max={max} viewBox="0 0 1000 240" preserveAspectRatio="none">
        {plot.cfo_observations.map((point) => <circle className={`standard-lane lane-${plot.receiver_path_ids.indexOf(point.receiver_path_id)}`} key={point.observation_id} data-receiver-path-id={point.receiver_path_id} cx={x(point.time_s)} cy={y(point.baseband_cfo_hz)} r="5" />)}
        {plot.trajectory_curves.map((curve) => (
          <polyline key={curve.trajectory_id} data-receiver-path-id={curve.receiver_path_id} className={`trajectory standard-lane lane-${plot.receiver_path_ids.indexOf(curve.receiver_path_id)} degree-${curve.degree}`} points={curve.points.map((point) => `${x(point.time_s)},${y(point.value)}`).join(" ")} />
        ))}
        <line className="standard-cursor" x1={x(cursor)} x2={x(cursor)} y1="0" y2="240" />
      </svg>
      <small>Shared time (s) · baseband CFO (Hz) · candidate evidence only</small>
    </figure>
  );
}

function TrajectoryTable({ detail }: { detail: StandardSubjectDetailV2 }) {
  return (
    <details className="standard-table"><summary>Trajectory report ({detail.trajectories.length}/{detail.trajectory_source_count})</summary>
      <table aria-label="Trajectory report"><thead><tr><th scope="col">Algorithm</th><th scope="col">Path</th><th scope="col">Degree</th><th scope="col">Coefficients (Hz)</th><th scope="col">RMS</th><th scope="col">Correction</th></tr></thead>
        <tbody>{detail.trajectories.map((trajectory) => <tr key={trajectory.trajectory_id}>
          <td>{trajectory.algorithm}</td><td>{trajectory.receiver_path_id}</td><td>{trajectory.degree}</td>
          <td>{trajectory.coefficients_hz.join(", ")}</td><td>{trajectory.residual_rms_hz}</td>
          <td>{trajectory.selected_for_correction ? `selected · gain ${trajectory.corrected_glrt64_gain}` : trajectory.status}</td>
        </tr>)}</tbody>
      </table>
    </details>
  );
}

function StageTable({ detail }: { detail: StandardSubjectDetailV2 }) {
  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    detail.stages.forEach((stage) => { result[stage.disposition] = (result[stage.disposition] ?? 0) + 1; });
    return result;
  }, [detail.stages]);
  return (
    <details className="standard-table"><summary>Stage execution ({Object.entries(counts).map(([key, value]) => `${value} ${key}`).join(" · ")})</summary>
      <table aria-label="Stage execution"><thead><tr><th scope="col">Stage</th><th scope="col">Disposition</th><th scope="col">Runtime</th><th scope="col">Reason</th></tr></thead>
        <tbody>{detail.stages.map((stage) => <tr key={`${stage.subject_id}-${stage.stage_key}`}>
          <td>{stage.stage_key}</td><td>{stage.disposition}</td><td>{stage.runtime_seconds ?? "—"}</td><td>{stage.reason}</td>
        </tr>)}</tbody>
      </table>
    </details>
  );
}
