import { useEffect, useMemo, useState } from "react";

import {
  getStandardInvestigation,
  getStandardNativePngArtifactInventory,
  getStandardReplayAudit,
  getStandardTrackGateAudit,
  getStandardSubject,
  getStandardSubjects,
  standardInvestigationPngUrl,
  standardPngUrl,
  standardTrajectoryArtifactUrl,
} from "./standard-api";
import { assertMatchingStandardMajor } from "./standard-contract-validation";
import type { StandardInvestigationGalleryV1 } from "./standard-api";
import type { AnalysisLane } from "./standard-api";
import type {
  StandardNativeSubjectDetailV3,
  StandardNativeSubjectDetailV4,
  StandardNativeSubjectDetailV5,
  StandardNativePngArtifactInventoryV4,
  StandardNativePngArtifactInventoryV5,
  StandardNativePngArtifactInventoryV6,
  StandardNativePngArtifactInventoryV7,
  StandardNativeSubjectSummaryV3,
  StandardNativeSubjectSummaryV4,
  StandardNativeSubjectSummaryV5,
  StandardSubjectDetail,
  StandardSubjectDetailV2,
  StandardReplayAuditV1,
  StandardTrackGateAuditV1,
  StandardSubjectHierarchy,
  StandardSubjectHierarchyV2,
  StandardSubjectSummary,
  StandardSubjectSummaryV2,
  StandardViewKindV2,
} from "./standard-contracts";
import "./standard-analysis.css";

type StandardNativeDetail =
  | StandardNativeSubjectDetailV3
  | StandardNativeSubjectDetailV4
  | StandardNativeSubjectDetailV5;
type StandardNativeInventory =
  | StandardNativePngArtifactInventoryV4
  | StandardNativePngArtifactInventoryV5
  | StandardNativePngArtifactInventoryV6
  | StandardNativePngArtifactInventoryV7;

const galleryOrder: StandardViewKindV2[] = [
  "waterfall",
  "glrt64",
  "cfo_trajectory",
];

const viewLabels: Record<StandardViewKindV2, string> = {
  quality: "Signal quality",
  power: "Power over time",
  waterfall: "Waterfall — frequency × time",
  glrt64: "Pilot detector comparison — GLRT64, Symbolwise, Anchor-8",
  cfo_trajectory: "CFO trajectories — Hough-seeded robust linear segments",
  qam: "Known-pilot QAM response",
};

const canonicalExclusionTags = ["QUALIFICATION", "CALIBRATION", "ACCEPTANCE"] as const;

export function StandardAnalysis({
  sessionId,
  includeTest,
  lane = "standard",
}: {
  sessionId: string;
  includeTest: boolean;
  lane?: AnalysisLane;
}) {
  const [hierarchy, setHierarchy] = useState<StandardSubjectHierarchy | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<StandardSubjectDetail | null>(null);
  const [tabs, setTabs] = useState<StandardSubjectSummary[]>([]);
  const [investigation, setInvestigation] = useState<StandardInvestigationGalleryV1 | null>(null);
  const [replayAudit, setReplayAudit] = useState<StandardReplayAuditV1 | null>(null);
  const [trackGateAudit, setTrackGateAudit] = useState<StandardTrackGateAuditV1 | null>(null);
  const [nativePngInventory, setNativePngInventory] = useState<
    StandardNativeInventory | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setHierarchy(null);
    setSelectedId(null);
    setDetail(null);
    setTabs([]);
    setInvestigation(null);
    setReplayAudit(null);
    setTrackGateAudit(null);
    setNativePngInventory(null);
    getStandardSubjects(sessionId, includeTest, controller.signal, lane)
      .then((result) => {
        validateHierarchyTruth(result);
        setHierarchy(result);
        setSelectedId(result.rows.find((row) => row.subject_kind === "paired")?.subject_id
          ?? result.rows[0]?.subject_id
          ?? null);
        setError(null);
        if (lane === "standard" && result.schema_version === 2) {
          getStandardInvestigation(sessionId, controller.signal)
            .then(setInvestigation)
            .catch((reason: Error) => {
              if (reason.name !== "AbortError") setError(reason.message);
            });
        }
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [includeTest, lane, sessionId]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setDetail(null);
    setNativePngInventory(null);
    getStandardSubject(sessionId, selectedId, includeTest, controller.signal, lane)
      .then((result) => {
        if (!hierarchy) throw new Error("Standard hierarchy is unavailable for subject validation");
        assertMatchingStandardMajor(hierarchy, result);
        validateDetailTruth(result);
        setDetail(result);
        if (result.schema_version !== 2) {
          setTabs((current) => {
            const subjects = new Map(
              [...current, ...result.receiver_path_expansions, ...hierarchy.rows]
                .map((subject) => [subject.subject_id, subject]),
            );
            const ordered = [...subjects.values()];
            return [
              ...ordered.filter((subject) => subject.subject_kind === "receiver_path"),
              ...ordered.filter((subject) => subject.subject_kind === "radio"),
              ...ordered.filter((subject) => subject.subject_kind === "paired"),
            ];
          });
        } else if (result.subject.subject_kind === "paired") {
          setTabs([...result.receiver_path_expansions, {
            ...result.subject,
            label: `Combined ${result.receiver_path_expansions.length}-path`,
          }]);
        } else {
          setTabs((current) => current.length === 0 ? [result.subject] : current);
        }
        setError(null);
        if (result.schema_version !== 2 && lane === "standard") {
          getStandardNativePngArtifactInventory(
            sessionId,
            result.subject.subject_id,
            includeTest,
            controller.signal,
          )
            .then((inventory) => {
              if (inventory !== null && !nativeInventoryMatchesDetail(inventory, result)) {
                throw new Error("Standard native PNG inventory crossed its selected subject");
              }
              setNativePngInventory(inventory);
            })
            .catch((reason: Error) => {
              if (reason.name !== "AbortError") setNativePngInventory(null);
            });
        }
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    if (hierarchy?.schema_version === 2) {
      getStandardReplayAudit(sessionId, selectedId, includeTest, controller.signal, lane)
        .then(setReplayAudit)
        .catch((reason: Error) => {
          if (reason.name !== "AbortError") setReplayAudit(null);
        });
      getStandardTrackGateAudit(sessionId, selectedId, includeTest, controller.signal, lane)
        .then(setTrackGateAudit)
        .catch((reason: Error) => {
          if (reason.name !== "AbortError") setTrackGateAudit(null);
        });
    } else {
      setReplayAudit(null);
      setTrackGateAudit(null);
    }
    return () => controller.abort();
  }, [hierarchy, includeTest, lane, selectedId, sessionId]);

  if (error) return <section className="standard-error" role="alert">{error}</section>;
  if (!hierarchy) return <section className="standard-loading">Loading {lane === "standard" ? "Standard" : "Research"} image artifacts…</section>;

  return (
    <section className="standard-analysis standard-image-analysis" aria-label="Standard analysis image artifacts">
      <header className="standard-heading">
        <div><span>{nativeRateLabel(hierarchy, lane)}</span><h3>{hierarchy.schema_version !== 2 ? "Standard native analysis" : `${lane === "standard" ? "Standard" : "Research"} analysis image artifacts`}</h3></div>
        <EvidenceBadge hierarchy={hierarchy} />
      </header>
      <p className="standard-image-intro">
        {hierarchy.schema_version !== 2
          ? "Native-rate evidence keeps the full device-time axis. Invalid zero-filled samples remain explicitly unavailable and no stateful operation crosses a continuity boundary."
          : "Each receiver path is analyzed independently. The combined tab aligns all four paths on one shared time domain."}
      </p>
      <SubjectTabs tabs={tabs} selectedId={selectedId} onSelect={setSelectedId} />
      {!detail ? <p>Loading image gallery…</p> : (
        detail.schema_version !== 2 ? (
          <NativeAnalysisDetail
            sessionId={sessionId}
            detail={detail}
            pngInventory={nativePngInventory}
          />
        ) : <>
          <PngGallery
            sessionId={sessionId}
            includeTest={includeTest}
            detail={detail}
            investigation={investigation}
            lane={lane}
          />
          <SegmentFitTables audit={trackGateAudit} />
          <TrackGateTables audit={trackGateAudit} />
          {!trackGateAudit ? <ReplayAuditTable audit={replayAudit} /> : null}
        </>
      )}
    </section>
  );
}

function NativeAnalysisDetail({
  sessionId,
  detail,
  pngInventory,
}: {
  sessionId: string;
  detail: StandardNativeDetail;
  pngInventory: StandardNativeInventory | null;
}) {
  const terminal = detail.subject.terminal;
  const statistics = terminal.sufficient_statistics;
  const opportunities = terminal.terminal_opportunities;
  const qam = terminal.qam_statistics;
  const tracks = terminal.terminal_tracks;
  return (
    <>
      <section className="standard-native-summary" aria-label="Native validity and scientific summary">
        <header>
          <div>
            <span>CURRENT · {formatEnum(detail.subject.coverage_status)}</span>
            <h4>{detail.subject.label}</h4>
          </div>
          <strong>{formatPercent(terminal.coverage_fraction)} valid coverage</strong>
        </header>
        <div className="standard-native-summary-grid">
          <article>
            <span>VALIDITY COVERAGE</span>
            <strong>{formatEnum(terminal.coverage_status)}</strong>
            <dl>
              <div><dt>Expected samples</dt><dd>{formatCount(terminal.expected_complex_sample_count)}</dd></div>
              <div><dt>Valid samples</dt><dd>{formatCount(terminal.valid_complex_sample_count)}</dd></div>
              <div><dt>Missing samples</dt><dd>{formatCount(terminal.missing_complex_sample_count)}</dd></div>
              <div><dt>Valid UTC intervals</dt><dd>{terminal.valid_utc_intervals.length}</dd></div>
            </dl>
          </article>
          <article>
            <span>SCIENTIFIC DISPOSITION</span>
            <strong>{formatEnum(terminal.scientific_disposition)}</strong>
            <p>Processing is Current independently of this scientific result. Candidate evidence makes no source-attribution or payload claim.</p>
          </article>
          <article>
            <span>VALID-SAMPLE SUFFICIENT STATISTICS</span>
            <strong>{formatCount(statistics.valid_complex_sample_count)} complex samples</strong>
            <dl>
              <div><dt>Receiver paths</dt><dd>{statistics.receiver_path_count}</dd></div>
              <div><dt>Energy sum (CI16²)</dt><dd>{formatCount(statistics.energy_sum_ci16_squared)}</dd></div>
              <div><dt>Clipped samples</dt><dd>{formatCount(statistics.clipped_complex_sample_count)} · {formatPercent(statistics.clipped_complex_fraction)}</dd></div>
              <div><dt>Mean power / full scale²</dt><dd>{statistics.mean_power_full_scale_squared.toExponential(4)}</dd></div>
              <div><dt>Constant IQ</dt><dd>{statistics.constant_iq ? "yes" : "no"}</dd></div>
            </dl>
          </article>
          <article>
            <span>PROBE OPPORTUNITIES</span>
            <strong>{opportunities.analyzed_count} / {opportunities.scheduled_count} analyzed</strong>
            <dl>
              <div><dt>Candidate / no candidate</dt><dd>{opportunities.candidate_count} / {opportunities.no_candidate_count}</dd></div>
              <div><dt>Scientifically insufficient</dt><dd>{opportunities.insufficient_count}</dd></div>
              <div><dt>Gap excluded</dt><dd>{opportunities.gap_excluded_count}</dd></div>
              <div><dt>Boundary excluded</dt><dd>{opportunities.continuity_boundary_excluded_count}</dd></div>
              <div><dt>Outside span</dt><dd>{opportunities.outside_span_count}</dd></div>
            </dl>
          </article>
          <article>
            <span>KNOWN-PILOT QAM STATISTICS</span>
            <strong>{qam.qam_result_count} result{qam.qam_result_count === 1 ? "" : "s"}</strong>
            <dl>
              <div><dt>Frames / symbols</dt><dd>{qam.frame_count} / {formatCount(qam.symbol_count)}</dd></div>
              <div><dt>Correct symbols</dt><dd>{formatCount(qam.correct_symbol_count)}</dd></div>
              <div><dt>Hard-symbol accuracy</dt><dd>{formatOptionalDecimal(qam.hard_symbol_accuracy, true)}</dd></div>
              <div><dt>RMS EVM</dt><dd>{formatOptionalDecimal(qam.rms_evm, false)}</dd></div>
            </dl>
          </article>
          <article>
            <span>RESET-LOCAL TRACK ACCOUNTING</span>
            <strong>{tracks.returned_trajectory_count} returned trajectories</strong>
            <dl>
              <div><dt>Continuity segments</dt><dd>{tracks.segment_count}</dd></div>
              <div><dt>Analyzed segments</dt><dd>{tracks.analyzed_segment_count}</dd></div>
              <div><dt>Source / truncated</dt><dd>{tracks.source_trajectory_count} / {tracks.truncated_trajectory_count}</dd></div>
              <div><dt>Cross-segment association</dt><dd>prohibited</dd></div>
            </dl>
          </article>
        </div>
        <div className="standard-native-invariants" aria-label="Native gap-safety invariants">
          <span>Valid samples only</span>
          <span>State resets at every boundary</span>
          <span>No cross-gap operation</span>
          <span>Reducers merge sufficient statistics</span>
        </div>
      </section>
      {detail.schema_version === 4 || detail.schema_version === 5 ? (
        <NativeRfAuthority detail={detail} />
      ) : null}
      <NativePathCoverage evidence={detail.receiver_path_evidence} />
      <NativePngGallery
        detail={detail}
        sessionId={sessionId}
        inventory={pngInventory}
      />
      <footer className="standard-native-limitations">
        <strong>Interpretation limits</strong>
        <ul>{detail.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
      </footer>
    </>
  );
}

function NativeRfAuthority({
  detail,
}: {
  detail: StandardNativeSubjectDetailV4 | StandardNativeSubjectDetailV5;
}) {
  const production = detail.schema_version === 5;
  return (
    <section
      className="standard-native-paths"
      aria-label={production ? "Production RF coverage authority" : "Mixed-rate RF coverage authority"}
    >
      <header>
        <div>
          <span>SEALED RF / IF AUTHORITY</span>
          <h4>
            {production
              ? `${formatEnum(detail.subject.eligibility.dwell_class)} · ${formatEnum(detail.subject.eligibility.tuning_branch)} tuning · no resampling`
              : "Same Starlink channel and edge · independent native-rate passbands · no resampling"}
          </h4>
        </div>
      </header>
      <div>{detail.subject.eligibility.legs.map((leg) => (
        <article key={`${leg.stream_id}:${leg.radio_id}`}>
          <strong>{leg.radio_id} · {(leg.sample_rate_hz / 1_000_000).toFixed(1)} MS/s</strong>
          <span>
            Channel {leg.starlink_channel} {leg.starlink_edge} · analog BW {formatMhz(leg.rf_bandwidth_hz)}
          </span>
          <small>
            Tune {formatMhz(leg.tuned_center_frequency_hz)} IF · pilot {formatMhz(leg.pilot_if_center_frequency_hz)} IF
          </small>
          <small>
            Captured {formatMhz(leg.captured_if_start_hz)}–{formatMhz(leg.captured_if_stop_hz)} IF inside {formatMhz(leg.channel_if_start_hz)}–{formatMhz(leg.channel_if_stop_hz)} channel
          </small>
          {leg.schema_version === 5 ? (
            <small>
              RX{leg.receiver_ids.join(" + RX")} · {formatEnum(leg.gain_controller_mode)} · metadata ABI {leg.metadata_abi_version}
            </small>
          ) : null}
        </article>
      ))}</div>
    </section>
  );
}

function NativePathCoverage({
  evidence,
}: {
  evidence: StandardNativeDetail["receiver_path_evidence"];
}) {
  return (
    <section className="standard-native-paths" aria-label="Receiver-path continuity coverage">
      <header><div><span>DEVICE-AXIS VALIDITY</span><h4>Receiver-path continuity coverage</h4></div></header>
      <div>{evidence.map((path) => (
        <article key={path.receiver_path.path_id}>
          <strong>{path.receiver_path.radio_label} {path.receiver_path.receiver_label}</strong>
          <span>{formatPercent(path.terminal.coverage_fraction)} valid · {formatEnum(path.terminal.coverage_status)}</span>
          <small>{path.continuity_segment_count} segment{path.continuity_segment_count === 1 ? "" : "s"} · {path.continuity_boundary_count} reset boundar{path.continuity_boundary_count === 1 ? "y" : "ies"}</small>
          <small>{path.terminal.valid_utc_intervals.length} valid UTC interval{path.terminal.valid_utc_intervals.length === 1 ? "" : "s"} · invalid zero-fill excluded</small>
        </article>
      ))}</div>
    </section>
  );
}

function NativePngGallery({
  detail,
  sessionId,
  inventory,
}: {
  detail: StandardNativeDetail;
  sessionId: string;
  inventory: StandardNativeInventory | null;
}) {
  if (inventory !== null) {
    return (
      <section className="standard-png-gallery" aria-label="Registered native image artifacts">
        {inventory.artifacts.map((artifact) => (
          <figure className={`standard-png-card ${artifact.name}`} key={artifact.name}>
            <figcaption>
              <div>
                <strong>{artifact.label}</strong>
                <small>{artifact.description} · {formatEnum(detail.subject.coverage_status)}</small>
              </div>
              <a href={artifact.href} download>Open PNG</a>
            </figcaption>
            <img
              src={artifact.href}
              alt={`${artifact.label} for ${detail.subject.label}`}
              loading={artifact.name === "waterfall" ? "eager" : "lazy"}
            />
          </figure>
        ))}
      </section>
    );
  }
  const registeredViews = detail.views.flatMap((view) =>
    view.png_available && view.png_href !== null ? [{ ...view, png_href: view.png_href }] : []);
  const alternateAvailable = detail.available_artifacts.includes("cfo-alternate");
  if (registeredViews.length === 0 && !alternateAvailable) {
    return (
      <section className="standard-native-empty" aria-label="Registered native image artifacts">
        No registered native PNG products are available for this subject.
      </section>
    );
  }
  return (
    <section className="standard-png-gallery" aria-label="Registered native image artifacts">
      {registeredViews.map((view) => (
        <figure className={`standard-png-card ${view.view_kind}`} key={view.view_kind}>
          <figcaption>
            <div>
              <strong>{viewLabels[view.view_kind]}</strong>
              <small>{axisDescription(view.view_kind)} · {formatEnum(view.state)}</small>
            </div>
            <a href={view.png_href} download>Open PNG</a>
          </figcaption>
          <img
            src={view.png_href}
            alt={`${viewLabels[view.view_kind]} for ${detail.subject.label}`}
            loading={view.view_kind === "waterfall" ? "eager" : "lazy"}
          />
        </figure>
      ))}
      {alternateAvailable ? (
        <figure className="standard-png-card cfo-alternate">
          <figcaption>
            <div>
              <strong>Alternate Hough CFO candidates</strong>
              <small>Registered reset-local research-only geometry</small>
            </div>
            <a href={standardTrajectoryArtifactUrl(
              sessionId,
              detail.subject.subject_id,
              "cfo-alternate",
            )} download>Open PNG</a>
          </figcaption>
          <img
            src={standardTrajectoryArtifactUrl(
              sessionId,
              detail.subject.subject_id,
              "cfo-alternate",
            )}
            alt={`Alternate Hough CFO candidates for ${detail.subject.label}`}
            loading="lazy"
          />
        </figure>
      ) : null}
    </section>
  );
}

function formatEnum(value: string) {
  return value.replaceAll("_", " ");
}

function formatCount(value: number) {
  return value.toLocaleString("en-GB");
}

function formatPercent(value: number) {
  return `${(100 * value).toFixed(value >= 0.99995 ? 2 : 3)}%`;
}

function formatOptionalDecimal(value: string | null, asPercent: boolean) {
  if (value === null) return "unavailable";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return asPercent ? formatPercent(parsed) : parsed.toPrecision(6);
}

function TrackGateTables({ audit }: { audit: StandardTrackGateAuditV1 | null }) {
  if (!audit) return null;
  const stages = audit.stages.filter((stage) =>
    stage.stage_key !== "trajectory-fit" && stage.stage_key !== "dealias-refinement");
  return (
    <section className="standard-track-gates" aria-label="Track gate decisions">
      <header className="standard-track-gates-heading">
        <div><span>SEALED STANDARD DECISIONS</span><h4>Track-by-track gate audit</h4></div>
        <small>{stages.length} decision stages</small>
      </header>
      <p>Every cell is projected from the persisted product as either an active threshold or an audit metric. Pass/drop describes that stage; display-only tracks cannot drive automatic IQ correction.</p>
      {stages.map((stage) => <GateStageTable key={stage.stage_key} stage={stage} heading={stage.label} />)}
    </section>
  );
}

function SegmentFitTables({ audit }: { audit: StandardTrackGateAuditV1 | null }) {
  if (!audit) return null;
  const original = audit.stages.find((stage) => stage.stage_key === "trajectory-fit");
  const huber = audit.stages.find((stage) => stage.stage_key === "dealias-refinement");
  const currentLinear = original?.label === "Original Hough segments"
    && huber?.label === "Huber residual refinement";
  return (
    <section className="standard-track-gates" aria-label="Hough and Huber segment tables">
      <header className="standard-track-gates-heading">
        <div><span>SEGMENT LINEAGE</span><h4>{currentLinear ? "Original Hough and final Huber segments" : "Persisted segment lineage"}</h4></div>
        <small>{currentLinear ? "seed-preserving refinement" : "legacy analysis product"}</small>
      </header>
      <p>{currentLinear
        ? "The first table is the accepted initial/residual-Hough geometry. For every Hough seed admitted to de-alias refinement, the second preserves its segment identity and represented probes while selecting one candidate/alias per probe and applying MAD-scaled Huber IRLS; it does not discover or split segments."
        : "These tables display the persisted fitting and de-alias products without relabelling historical polynomial results as Huber-linear output."}</p>
      {original ? <GateStageTable stage={original} heading={currentLinear ? "Original Hough segments" : original.label} /> : null}
      {huber ? <GateStageTable stage={huber} heading={currentLinear ? "Huber residual segments (final)" : huber.label} /> : null}
    </section>
  );
}

function GateStageTable({
  stage,
  heading,
}: {
  stage: StandardTrackGateAuditV1["stages"][number];
  heading: string;
}) {
  const columns = [...new Map(stage.rows.flatMap((row) => row.gates).map((gate) => [gate.gate_key, gate.label])).entries()];
  return (
    <section className="standard-trajectory-table standard-gate-stage" aria-label={`${heading} table`}>
      <header>
        <div><span>{stage.stage_key.replaceAll("-", " ").toUpperCase()}</span><h5>{heading}</h5></div>
        <small>{stage.rows.length} of {stage.source_track_count} shown{stage.truncated ? " · truncated" : ""}</small>
      </header>
      <p>{stage.description}</p>
      <div className="standard-table-scroll"><table aria-label={`${heading} table`}>
        <thead><tr><th>Segment</th><th>Receiver</th>{columns.map(([key, label]) => <th key={key}>{label}</th>)}<th>Disposition</th><th>Reason</th></tr></thead>
        <tbody>{stage.rows.map((row) => {
          const byKey = new Map(row.gates.map((gate) => [gate.gate_key, gate]));
          return <tr key={`${row.receiver_path_id}:${row.track_id}`}>
            <td><code title={row.track_id}>{shortTrackId(row.track_id)}</code></td>
            <td>{row.receiver_path_id}</td>
            {columns.map(([key]) => {
              const gate = byKey.get(key);
              return <td key={key}>{gate ? <GateCell gate={gate} /> : "—"}</td>;
            })}
            <td><span className={`standard-gate-disposition ${row.disposition}`}>{row.disposition.replace("_", " ")}</span></td>
            <td>{row.reason}</td>
          </tr>;
        })}</tbody>
      </table></div>
      {stage.limitation ? <p className="standard-gate-limitation">Limitation: {stage.limitation}</p> : null}
    </section>
  );
}

function GateCell({ gate }: { gate: StandardTrackGateAuditV1["stages"][number]["rows"][number]["gates"][number] }) {
  return <div className={`standard-gate-cell ${gate.verdict}`} title={gate.criterion}>
    <strong>{gate.verdict === "not_applicable" ? "N/A" : gate.verdict}</strong>
    <span>{gate.value}</span>
    <small>{gate.criterion}</small>
  </div>;
}

function shortTrackId(value: string) {
  const compact = value.replace("sha256:", "");
  return compact.length > 22 ? `${compact.slice(0, 10)}…${compact.slice(-7)}` : compact;
}

function ReplayAuditTable({ audit }: { audit: StandardReplayAuditV1 | null }) {
  if (!audit) return null;
  return (
    <section className="standard-trajectory-table" aria-label="CFO replay audit metrics">
      <header><div><span>AUDIT-ONLY HARMFUL-BLOCK METRICS</span><h4>CFO replay eligibility</h4></div><small>{audit.rows.length} of {audit.source_row_count} shown</small></header>
      <div className="standard-table-scroll"><table aria-label="CFO replay audit metrics">
        <thead><tr><th>Branch</th><th>Alias</th><th>Tier</th><th>Probes / blocks</th><th>Coverage</th><th>Corrected margin</th><th>Harmful blocks</th><th>Maximum run</th><th>Final</th><th>Reasons</th></tr></thead>
        <tbody>{audit.rows.map((row) => <tr key={`${row.receiver_path_id}:${row.branch_id}:${row.alias_index}`}>
          <td><code>{row.branch_id.slice(7, 15)}</code></td><td>{row.alias_index}</td><td>{row.tier.replace("_", " ")}</td>
          <td>{row.evaluated_probe_count} / {row.evaluated_block_count}</td><td>{row.block_coverage_ratio.toFixed(3)}</td>
          <td>{row.median_block_corrected_margin === null ? "—" : row.median_block_corrected_margin.toFixed(6)}</td>
          <td>{row.harmful_block_count}</td><td>{row.maximum_consecutive_harmful_blocks}</td>
          <td>{row.retained_in_final ? "retained" : "excluded"}</td><td>{row.reasons.join("; ")}</td>
        </tr>)}</tbody>
      </table></div>
      <p>Harmful-block count and maximum run are retained for audit and never veto replay or final selection.</p>
    </section>
  );
}

function AlternateTrackTable({ detail }: { detail: StandardSubjectDetailV2 }) {
  const tracks = detail.alternate_tracks ?? [];
  const sourceCount = detail.alternate_track_source_count ?? 0;
  if (sourceCount === 0) {
    return (
      <section className="standard-trajectory-table" aria-label="Alternate CFO line candidates">
        <header><div><span>RESEARCH-ONLY GEOMETRY</span><h4>Alternate CFO line candidates</h4></div></header>
        <p>No alternate-track product is published for this subject. Standard trajectory selection is unchanged.</p>
      </section>
    );
  }
  return (
    <section className="standard-trajectory-table" aria-label="Alternate CFO line candidates">
      <header>
        <div><span>WEIGHTED ALIAS-AWARE HOUGH · RESEARCH ONLY</span><h4>Alternate CFO line candidates</h4></div>
        <small>{tracks.length} of {sourceCount} shown</small>
      </header>
      <div className="standard-table-scroll"><table aria-label="Alternate CFO line candidates">
        <thead><tr><th>Track</th><th>Receiver</th><th>Support</th><th>Span</th><th>Slope</th><th>Acceleration</th><th>Intercept mod alias</th><th>Residual RMS</th><th>Max gap</th><th>Confidence</th><th>Status</th></tr></thead>
        <tbody>{tracks.map((row) => <tr key={`${row.receiver_path_id}:${row.track_id}`}>
          <td><code>{row.track_id.slice(0, 18)}…</code></td><td>{row.receiver_path_id}</td>
          <td>{row.support_count} ({row.weighted_support.toFixed(1)} weighted)</td>
          <td>{row.span_s.toFixed(3)} s</td><td>{formatSignedRate(row.slope_hz_per_s)}</td>
          <td>{row.acceleration_hz_per_s2.toFixed(1)} Hz/s²</td><td>{formatSignedHz(row.intercept_mod_alias_hz)}</td>
          <td>{row.residual_rms_hz.toFixed(2)} Hz</td><td>{row.maximum_gap_s.toFixed(3)} s</td>
          <td>{row.confidence.replace("_", " ")}</td><td>{row.status.replace("_", " ")}</td>
        </tr>)}</tbody>
      </table></div>
      <p>These deterministic geometric candidates do not feed automatic CFO correction, final detection, attribution, or Standard trajectory selection.</p>
    </section>
  );
}

function TrajectoryTable({ detail }: { detail: StandardSubjectDetailV2 }) {
  const radioByPath = new Map(
    detail.receiver_path_expansions.flatMap((subject) =>
      subject.receiver_paths.map((path) => [path.path_id, path.radio_label] as const)),
  );
  const radioLabels = [...new Set(detail.receiver_path_expansions.flatMap((subject) =>
    subject.receiver_paths.map((path) => path.radio_label)))];
  const derivatives = (row: StandardSubjectDetailV2["trajectories"][number]) => {
    const reversed = [...row.coefficients_hz].reverse();
    return {
      cfo: reversed[0] ?? 0,
      slope: reversed[1] ?? 0,
      acceleration: 2 * (reversed[2] ?? 0),
      jerk: 6 * (reversed[3] ?? 0),
    };
  };
  const nearestDerivativeDifference = (
    row: StandardSubjectDetailV2["trajectories"][number],
    radio: string,
  ) => {
    const ownRadio = radioByPath.get(row.receiver_path_id);
    if (ownRadio === radio) return "reference";
    const peers = detail.trajectories.filter((candidate) =>
      radioByPath.get(candidate.receiver_path_id) === radio && candidate.degree === row.degree);
    if (peers.length === 0) return "—";
    const own = derivatives(row);
    const difference = peers
      .map((peer) => {
        const candidate = derivatives(peer);
        const delta = {
          slope: candidate.slope - own.slope,
          acceleration: candidate.acceleration - own.acceleration,
          jerk: candidate.jerk - own.jerk,
        };
        const score = Math.abs(delta.slope) / Math.max(Math.abs(own.slope), 1)
          + Math.abs(delta.acceleration) / Math.max(Math.abs(own.acceleration), 1)
          + Math.abs(delta.jerk) / Math.max(Math.abs(own.jerk), 1);
        return { delta, score };
      })
      .sort((left, right) => left.score - right.score)[0].delta;
    return `Δv ${formatSignedRate(difference.slope)} · Δa ${formatSignedDerivative(difference.acceleration, 2)} · Δj ${formatSignedDerivative(difference.jerk, 3)}`;
  };
  return (
    <section className="standard-trajectory-table" aria-label="Tracking detections">
      <header>
        <div><span>GLRT64 TRACKING OUTPUT</span><h4>All fitted CFO trajectories</h4></div>
        <small>{detail.trajectories.length} of {detail.trajectory_source_count} shown</small>
      </header>
      <div className="standard-table-scroll">
        <table aria-label="Tracking detections">
          <thead><tr>
            <th>Track</th><th>Receiver</th><th>Order</th><th>CFO at t₀</th><th>Doppler slope</th><th>Acceleration</th><th>Jerk</th><th>Full equation</th>
            {radioLabels.map((radio) => <th key={radio}>{radio}<br /><small>nearest same-order derivative agreement</small></th>)}
            <th>Support</th><th>Residual RMS</th><th>Status</th>
          </tr></thead>
          <tbody>{detail.trajectories.map((row) => (
            <tr key={`${row.receiver_path_id}:${row.trajectory_id}`}>
              <td><code>{row.trajectory_id}</code></td>
              <td>{row.receiver_path_id}</td>
              <td>{polynomialName(row.degree)} ({row.degree})</td>
              <td>{formatSignedHz(derivatives(row).cfo)}</td>
              <td>{formatSignedRate(derivatives(row).slope)}</td>
              <td>{formatSignedDerivative(derivatives(row).acceleration, 2)}</td>
              <td>{formatSignedDerivative(derivatives(row).jerk, 3)}</td>
              <td><code>{polynomialEquation(row.coefficients_hz, row.reference_time_s)}</code></td>
              {radioLabels.map((radio) => <td key={radio}>{nearestDerivativeDifference(row, radio)}</td>)}
              <td>{row.support_count}</td>
              <td>{row.residual_rms_hz.toFixed(2)} Hz</td>
              <td>{row.status}{row.corrected_glrt64_gain === null ? "" : ` · GLRT Δ ${row.corrected_glrt64_gain.toFixed(3)}`}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p>Cross-radio agreement ignores absolute CFO offset and compares only slope, acceleration, and jerk for the nearest same-order fit. It is not an attribution or phase-coherence claim.</p>
    </section>
  );
}

function polynomialName(degree: 1 | 2 | 3) {
  return degree === 1 ? "linear" : degree === 2 ? "quadratic" : "cubic";
}

function polynomialEquation(coefficients: number[], referenceTime: number) {
  const highestDegree = coefficients.length - 1;
  const terms = coefficients.map((coefficient, index) => {
    const degree = highestDegree - index;
    const value = Math.abs(coefficient).toPrecision(7);
    const sign = index === 0 ? (coefficient < 0 ? "−" : "") : (coefficient < 0 ? " − " : " + ");
    if (degree === 0) return `${sign}${value}`;
    return `${sign}${value}·(t−${referenceTime.toFixed(6)})${degree === 1 ? "" : `^${degree}`}`;
  });
  return `CFO(t) = ${terms.join("")} Hz`;
}

function formatSignedHz(value: number) {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)} Hz`;
}

function formatSignedRate(value: number) {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)} Hz/s`;
}

function formatSignedDerivative(value: number, order: 2 | 3) {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)} Hz/s${order === 2 ? "²" : "³"}`;
}

function EvidenceBadge({ hierarchy }: { hierarchy: StandardSubjectHierarchy }) {
  if (hierarchy.schema_version !== 2) {
    const coverage = hierarchy.rows.some((row) => row.coverage_status !== "complete")
      ? "partial coverage"
      : "complete coverage";
    const science = [...new Set(hierarchy.rows.map((row) => row.scientific_disposition))]
      .map(formatEnum)
      .join(" / ");
    return (
      <div className={`standard-eligibility ordinary ${coverage === "partial coverage" ? "partial" : ""}`}>
        <strong>LIVE · CURRENT · {coverage.toUpperCase()}</strong>
        <small>{science} scientific disposition · candidate evidence only</small>
      </div>
    );
  }
  return (
    <div className={`standard-eligibility ${hierarchy.eligibility.evidence_only ? "test" : "ordinary"}`}>
      <strong>{hierarchy.source_type}{hierarchy.eligibility.evidence_only ? " · TEST EVIDENCE" : " · CURRENT"}</strong>
      <small>Candidate evidence only · no attribution or payload claim</small>
    </div>
  );
}

function SubjectTabs({
  tabs,
  selectedId,
  onSelect,
}: {
  tabs: StandardSubjectSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (tabs.length === 0) return <p>Loading receiver-path tabs…</p>;
  return (
    <nav className="standard-image-tabs" aria-label="Receiver path image tabs">
      {tabs.map((tab, index) => (
        <button
          key={tab.subject_id}
          type="button"
          aria-current={tab.subject_id === selectedId ? "page" : undefined}
          onClick={() => onSelect(tab.subject_id)}
        >
          <span>{index === tabs.length - 1 && tab.subject_kind === "paired" ? "Combined 4-path" : tab.label}</span>
          <small>{isNativeSubject(tab)
            ? `${tab.state} · ${formatEnum(tab.coverage_status)}`
            : tab.state}</small>
        </button>
      ))}
    </nav>
  );
}

function isNativeSubject(
  subject: StandardSubjectSummary,
): subject is StandardNativeSubjectSummaryV3 | StandardNativeSubjectSummaryV4 | StandardNativeSubjectSummaryV5 {
  return "coverage_status" in subject;
}

function PngGallery({
  sessionId,
  includeTest,
  detail,
  investigation,
  lane,
}: {
  sessionId: string;
  includeTest: boolean;
  detail: StandardSubjectDetailV2;
  investigation: StandardInvestigationGalleryV1 | null;
  lane: AnalysisLane;
}) {
  const descriptors = useMemo(
    () => new Map(detail.views.map((view) => [view.view_kind, view])),
    [detail.views],
  );
  const selectedInvestigation = investigation?.images?.find(
    (image) => image.subject_id === detail.subject.subject_id,
  );
  return (
    <div className="standard-png-gallery">
      {selectedInvestigation ? (
        <section className="standard-cfo-comparison" aria-label="Original and widened CFO search comparison">
          <header>
            <div><strong>Original vs widened upper-edge CFO search</strong><small>Exploratory comparison · candidate evidence only</small></div>
            <span>±1.2 MHz · 20 kHz coarse · 250 Hz fine · 50 Hz conditioned</span>
          </header>
          <div>
            <figure>
              <figcaption>Original Standard analysis · lower-edge template</figcaption>
              <img
                src={standardPngUrl(sessionId, detail.subject.subject_id, "glrt64", includeTest, lane)}
                alt={`Original Standard pilot search for ${detail.subject.label}`}
              />
            </figure>
            <figure>
              <figcaption>{selectedInvestigation.label}</figcaption>
              <img
                src={standardInvestigationPngUrl(sessionId, selectedInvestigation.image_id)}
                alt={`Widened upper-edge pilot search for ${detail.subject.label}`}
              />
            </figure>
          </div>
          <p>This is a bounded follow-up investigation, not the sealed current Standard result. GLRT64 alone proposes trajectories; Symbolwise and Anchor-8 are diagnostic comparisons.</p>
        </section>
      ) : null}
      {galleryOrder.map((kind) => {
        const descriptor = descriptors.get(kind);
        if (!descriptor || descriptor.state === "unavailable" || (kind === "glrt64" && selectedInvestigation)) return null;
        const url = standardPngUrl(sessionId, detail.subject.subject_id, kind, includeTest, lane);
        const legacyPolynomial = kind === "cfo_trajectory"
          && detail.trajectories.some((trajectory) => trajectory.degree !== 1);
        const label = legacyPolynomial
          ? "Legacy CFO trajectories — persisted polynomial models"
          : viewLabels[kind];
        return (
          <figure className={`standard-png-card ${kind}`} key={kind}>
            <figcaption>
              <div><strong>{label}</strong><small>{axisDescription(kind, legacyPolynomial)}</small></div>
              <a href={url} download>Open PNG</a>
            </figcaption>
            <img
              src={url}
              alt={`${label} for ${detail.subject.label}`}
              loading={kind === "waterfall" ? "eager" : "lazy"}
            />
          </figure>
        );
      })}
      {detail.subject.subject_kind === "paired" ? (
        <PairedAlternateCfoGallery
          sessionId={sessionId}
          receiverPaths={detail.receiver_path_expansions}
          lane={lane}
        />
      ) : null}
      {([
        ["cfo-dealiased", "De-aliased CFO trajectories", "Canonical modulo-alias branches before absolute-lift replay"],
        [
          "cfo-final",
          "Final replay-classified CFO candidates",
          "Solid tracks are correction-eligible; dashed tracks are retained display-only geometry",
        ],
        ...(detail.subject.subject_kind === "receiver_path"
          ? [
              ["cfo-alternate", "Alternate Hough CFO candidates", "Research-only line geometry over persisted GLRT64 evidence"],
              [
                "full-capture-glrt20ms",
                "Independent 20 ms GLRT and local Doppler rate",
                "Fresh 20 ms/10 ms-stride acquisition, Hough segments, and constant-rate local slope diagnostics",
              ],
              [
                "trajectory-accounting",
                "Trajectory-conditioned replay accounting",
                "Same-component baselines; unmatched evaluations explicit; physical probes counted once",
              ],
              [
                "pilot-doppler",
                "Pilot Doppler qualification overview",
                "Phase, carrier-rate state, segment resets, and like-for-like residual comparisons",
              ],
              [
                "pilot-carrier-tracking",
                "Frame CFO and carrier-rate tracking (A + C)",
                "Frame-level CFO residual and rate state, with qualified 50–75 ms regions highlighted",
              ],
              [
                "pilot-segment-rates",
                "Doppler rates across 50–75 ms segment regions",
                "Direct local slopes, uncertainty, Kalman agreement, and the frozen reference for every segment",
              ],
            ] as const
          : []),
      ] as const).map(([artifactName, label, description]) => {
        const url = standardTrajectoryArtifactUrl(
          sessionId,
          detail.subject.subject_id,
          artifactName,
          lane,
        );
        return (
          <figure className={`standard-png-card ${artifactName}`} key={artifactName}>
            <figcaption>
              <div><strong>{label}</strong><small>{description}</small></div>
              <a href={url} download>Open PNG</a>
            </figcaption>
            <img
              src={url}
              alt={`${label} for ${detail.subject.label}`}
              loading="lazy"
            />
          </figure>
        );
      })}
      <footer className="standard-image-note">
        <strong>{detail.subject.label}</strong>
        <span>{detail.time_domain.elapsed_start_s.toFixed(3)}–{detail.time_domain.elapsed_end_s.toFixed(3)} s shared elapsed time</span>
        <span>PNG images are served from verified immutable {lane === "standard" ? "Standard" : "Research"} presentation products; raw IQ is never served to the browser.</span>
      </footer>
    </div>
  );
}

function PairedAlternateCfoGallery({
  sessionId,
  receiverPaths,
  lane,
}: {
  sessionId: string;
  receiverPaths: StandardSubjectSummaryV2[];
  lane: AnalysisLane;
}) {
  return (
    <section className="standard-paired-alternate" aria-label="Paired receiver-path Hough CFO candidates">
      <header>
        <div>
          <strong>Alternate Hough CFO candidates by receiver path</strong>
          <small>Research-only line geometry over each path's persisted GLRT64 evidence</small>
        </div>
        <span>{receiverPaths.length} independent path artifacts</span>
      </header>
      <div>
        {receiverPaths.map((path) => {
          const url = standardTrajectoryArtifactUrl(
            sessionId,
            path.subject_id,
            "cfo-alternate",
            lane,
          );
          return (
            <figure key={path.subject_id}>
              <figcaption>
                <strong>{path.label}</strong>
                <a href={url} download>Open PNG</a>
              </figcaption>
              <img
                src={url}
                alt={`Alternate Hough CFO candidates for ${path.label}`}
                loading="lazy"
              />
            </figure>
          );
        })}
      </div>
      <p>These are the registered child receiver-path products, shown together for comparison. No joint or cross-radio Hough product is inferred.</p>
    </section>
  );
}

function axisDescription(kind: StandardViewKindV2, legacyPolynomial = false) {
  if (kind === "waterfall") return "frequency → · elapsed time ↓ · color = power";
  if (kind === "glrt64") return "elapsed time → · independent response scales · GLRT64 alone proposes tracks";
  if (kind === "cfo_trajectory") return legacyPolynomial
    ? "elapsed time → · CFO ↑ · historical persisted polynomial curves"
    : "elapsed time → · CFO ↑ · robust degree-1 segments";
  return "elapsed time → · response ↑";
}

function nativeRateLabel(hierarchy: StandardSubjectHierarchy, lane: AnalysisLane): string {
  if (hierarchy.schema_version === 3) {
    return `STANDARD · NATIVE · ${(hierarchy.eligibility.sample_rate_hz / 1_000_000).toFixed(1)} MS/s`;
  }
  if (hierarchy.schema_version === 4 || hierarchy.schema_version === 5) {
    const rates = [...new Set(hierarchy.eligibility.legs.map((leg) => leg.sample_rate_hz))]
      .sort((left, right) => left - right)
      .map((rate) => (rate / 1_000_000).toFixed(1))
      .join(" + ");
    const mode = hierarchy.schema_version === 5
      ? formatEnum(hierarchy.eligibility.dwell_class).toUpperCase()
      : "MIXED";
    return `STANDARD · NATIVE · ${mode} ${rates} MS/s`;
  }
  return lane === "standard" ? "STANDARD · 2×20 MS / 50 MS" : "RESEARCH · 3×20 MS / 50 MS";
}

function nativeInventoryMatchesDetail(
  inventory: StandardNativeInventory,
  detail: StandardNativeDetail,
): boolean {
  if (inventory.session_id !== detail.subject.session_id
    || inventory.subject_id !== detail.subject.subject_id
    || inventory.subject_kind !== detail.subject.subject_kind) {
    return false;
  }
  if (detail.schema_version === 3) {
    return inventory.schema_version === 4
      && inventory.sample_rate_hz === detail.subject.eligibility.sample_rate_hz;
  }
  const expectedInventoryVersion = detail.schema_version === 4 ? 5 : 6;
  if (inventory.schema_version !== expectedInventoryVersion) return false;
  const streamIds = new Set(
    detail.subject.receiver_paths.map((path) => path.scope.stream_id),
  );
  const expectedRates = [...new Set(
    detail.subject.eligibility.legs
      .filter((leg) => streamIds.has(leg.stream_id))
      .map((leg) => leg.sample_rate_hz),
  )].sort((left, right) => left - right);
  return expectedRates.length === inventory.sample_rates_hz.length
    && expectedRates.every((rate, index) => rate === inventory.sample_rates_hz[index]);
}

function formatMhz(valueHz: number): string {
  return `${(valueHz / 1_000_000).toFixed(4)} MHz`;
}

function validateHierarchyTruth(hierarchy: StandardSubjectHierarchy) {
  if (hierarchy.schema_version !== 2) {
    if (hierarchy.source_type !== "LIVE" || hierarchy.eligibility.source_type !== "LIVE") {
      throw new Error("Standard native Current presentation must describe a LIVE capture");
    }
    hierarchy.rows.forEach((row) => {
      if (row.state !== "current" || !row.ordinary_current) {
        throw new Error("Standard native promoted subject is not Current");
      }
      if (JSON.stringify(row.eligibility) !== JSON.stringify(hierarchy.eligibility)) {
        throw new Error("Standard native subject eligibility differs from hierarchy authority");
      }
      if (row.coverage_status !== row.terminal.coverage_status
        || row.scientific_disposition !== row.terminal.scientific_disposition) {
        throw new Error("Standard native subject summary differs from terminal evidence");
      }
    });
    return;
  }
  validateEligibilityTruth(hierarchy.eligibility);
  if (hierarchy.source_type !== hierarchy.eligibility.source_type) {
    throw new Error("Standard eligibility source does not match the hierarchy");
  }
  hierarchy.rows.forEach((row) => {
    validateEligibilityTruth(row.eligibility);
    validateSubjectTruth(row);
  });
}

function validateDetailTruth(detail: StandardSubjectDetail) {
  if (detail.schema_version !== 2) {
    const expectedPaths = detail.subject.receiver_paths.map((path) => path.path_id);
    const expandedPaths = detail.receiver_path_expansions.map(
      (subject) => subject.receiver_paths[0]?.path_id,
    );
    const evidencePaths = detail.receiver_path_evidence.map(
      (evidence) => evidence.receiver_path.path_id,
    );
    if (expectedPaths.length !== expandedPaths.length
      || expectedPaths.some((path, index) => path !== expandedPaths[index])
      || expectedPaths.some((path, index) => path !== evidencePaths[index])) {
      throw new Error("Standard native detail path inventories do not match");
    }
    return;
  }
  validateSubjectTruth(detail.subject);
  detail.receiver_path_expansions.forEach(validateSubjectTruth);
}

function validateEligibilityTruth(eligibility: StandardSubjectHierarchyV2["eligibility"]) {
  const orderedExclusions = canonicalExclusionTags.filter((tag) => eligibility.exclusion_tags.includes(tag));
  if (eligibility.exclusion_tags.length !== orderedExclusions.length
    || !eligibility.exclusion_tags.every((value, index) => value === orderedExclusions[index])) {
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
  const codedReasons = subject.state_reasons.filter((reason) => reason.code !== null);
  if ((subject.state === "stale" && codedReasons.length !== subject.state_reasons.length)
    || (subject.state === "stale" && subject.state_reasons.length === 0)
    || (subject.state !== "stale" && codedReasons.length > 0)) {
    throw new Error("Standard subject state and stale reasons are incompatible");
  }
}
