import { useEffect, useMemo, useState } from "react";

import { getStandardSubject, getStandardSubjects, standardPngUrl } from "./standard-api";
import type {
  StandardSubjectDetailV2,
  StandardSubjectHierarchyV2,
  StandardSubjectSummaryV2,
  StandardViewKindV2,
} from "./standard-contracts";
import "./standard-analysis.css";

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
  cfo_trajectory: "CFO trajectories — linear, quadratic, cubic",
  qam: "Known-pilot QAM response",
};

const canonicalExclusionTags = ["QUALIFICATION", "CALIBRATION", "ACCEPTANCE"] as const;

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
  const [tabs, setTabs] = useState<StandardSubjectSummaryV2[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setHierarchy(null);
    setDetail(null);
    setTabs([]);
    getStandardSubjects(sessionId, includeTest, controller.signal)
      .then((result) => {
        validateHierarchyTruth(result);
        setHierarchy(result);
        setSelectedId(result.rows.find((row) => row.subject_kind === "paired")?.subject_id
          ?? result.rows[0]?.subject_id
          ?? null);
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
    getStandardSubject(sessionId, selectedId, includeTest, controller.signal)
      .then((result) => {
        validateSubjectTruth(result.subject);
        result.receiver_path_expansions.forEach(validateSubjectTruth);
        setDetail(result);
        if (result.subject.subject_kind === "paired") {
          setTabs([...result.receiver_path_expansions, {
            ...result.subject,
            label: `Combined ${result.receiver_path_expansions.length}-path`,
          }]);
        } else if (tabs.length === 0) {
          setTabs([result.subject]);
        }
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [includeTest, selectedId, sessionId, tabs.length]);

  if (error) return <section className="standard-error" role="alert">{error}</section>;
  if (!hierarchy) return <section className="standard-loading">Loading Standard image artifacts…</section>;

  return (
    <section className="standard-analysis standard-image-analysis" aria-label="Standard analysis image artifacts">
      <header className="standard-heading">
        <div><span>STANDARD GLRT64 PIPELINE</span><h3>Analysis image artifacts</h3></div>
        <EvidenceBadge hierarchy={hierarchy} />
      </header>
      <p className="standard-image-intro">
        Each receiver path is analyzed independently. The combined tab aligns all four paths on one shared time domain.
      </p>
      <SubjectTabs tabs={tabs} selectedId={selectedId} onSelect={setSelectedId} />
      {!detail ? <p>Loading image gallery…</p> : (
        <>
          <PngGallery
            sessionId={sessionId}
            includeTest={includeTest}
            detail={detail}
          />
          <TrajectoryTable detail={detail} />
        </>
      )}
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
  const cfoAt = (row: StandardSubjectDetailV2["trajectories"][number], time: number) =>
    row.coefficients_hz.reduce(
      (total, coefficient, degree) => total + coefficient * ((time - row.reference_time_s) ** degree),
      0,
    );
  const nearestDifference = (
    row: StandardSubjectDetailV2["trajectories"][number],
    radio: string,
  ) => {
    const ownRadio = radioByPath.get(row.receiver_path_id);
    if (ownRadio === radio) return "reference";
    const peers = detail.trajectories.filter((candidate) =>
      radioByPath.get(candidate.receiver_path_id) === radio && candidate.degree === row.degree);
    if (peers.length === 0) return "—";
    const difference = peers
      .map((peer) => cfoAt(peer, row.reference_time_s) - cfoAt(row, row.reference_time_s))
      .sort((left, right) => Math.abs(left) - Math.abs(right))[0];
    return `Δ ${formatSignedHz(difference)}`;
  };
  return (
    <section className="standard-trajectory-table" aria-label="Tracking detections">
      <header>
        <div><span>GLRT64 TRACKING OUTPUT</span><h4>All fitted CFO trajectories</h4></div>
        <small>{detail.trajectories.length} of {detail.trajectory_source_count} shown</small>
      </header>
      <div className="standard-table-scroll">
        <table>
          <thead><tr>
            <th>Track</th><th>Receiver</th><th>Order</th><th>CFO at t₀</th><th>Doppler at t₀</th><th>Full equation</th>
            {radioLabels.map((radio) => <th key={radio}>{radio}<br /><small>nearest same-order ΔCFO</small></th>)}
            <th>Support</th><th>Residual RMS</th><th>Status</th>
          </tr></thead>
          <tbody>{detail.trajectories.map((row) => (
            <tr key={`${row.receiver_path_id}:${row.trajectory_id}`}>
              <td><code>{row.trajectory_id}</code></td>
              <td>{row.receiver_path_id}</td>
              <td>{polynomialName(row.degree)} ({row.degree})</td>
              <td>{formatSignedHz(row.coefficients_hz[0] ?? 0)}</td>
              <td>{formatSignedRate(row.coefficients_hz[1] ?? 0)}</td>
              <td><code>{polynomialEquation(row.coefficients_hz, row.reference_time_s)}</code></td>
              {radioLabels.map((radio) => <td key={radio}>{nearestDifference(row, radio)}</td>)}
              <td>{row.support_count}</td>
              <td>{row.residual_rms_hz.toFixed(2)} Hz</td>
              <td>{row.status}{row.corrected_glrt64_gain === null ? "" : ` · GLRT Δ ${row.corrected_glrt64_gain.toFixed(3)}`}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p>Cross-radio columns are display-only nearest same-order CFO differences at each row’s reference epoch; they are not an attribution or phase-coherence claim.</p>
    </section>
  );
}

function polynomialName(degree: 1 | 2 | 3) {
  return degree === 1 ? "linear" : degree === 2 ? "quadratic" : "cubic";
}

function polynomialEquation(coefficients: number[], referenceTime: number) {
  const terms = coefficients.map((coefficient, degree) => {
    const value = Math.abs(coefficient).toPrecision(7);
    const sign = degree === 0 ? (coefficient < 0 ? "−" : "") : (coefficient < 0 ? " − " : " + ");
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

function EvidenceBadge({ hierarchy }: { hierarchy: StandardSubjectHierarchyV2 }) {
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
  tabs: StandardSubjectSummaryV2[];
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
          <small>{tab.state}</small>
        </button>
      ))}
    </nav>
  );
}

function PngGallery({
  sessionId,
  includeTest,
  detail,
}: {
  sessionId: string;
  includeTest: boolean;
  detail: StandardSubjectDetailV2;
}) {
  const descriptors = useMemo(
    () => new Map(detail.views.map((view) => [view.view_kind, view])),
    [detail.views],
  );
  return (
    <div className="standard-png-gallery">
      {galleryOrder.map((kind) => {
        const descriptor = descriptors.get(kind);
        if (!descriptor || descriptor.state === "unavailable") return null;
        const url = standardPngUrl(sessionId, detail.subject.subject_id, kind, includeTest);
        return (
          <figure className={`standard-png-card ${kind}`} key={kind}>
            <figcaption>
              <div><strong>{viewLabels[kind]}</strong><small>{axisDescription(kind)}</small></div>
              <a href={url} download>Open PNG</a>
            </figcaption>
            <img
              src={url}
              alt={`${viewLabels[kind]} for ${detail.subject.label}`}
              loading={kind === "waterfall" ? "eager" : "lazy"}
            />
          </figure>
        );
      })}
      <footer className="standard-image-note">
        <strong>{detail.subject.label}</strong>
        <span>{detail.time_domain.elapsed_start_s.toFixed(3)}–{detail.time_domain.elapsed_end_s.toFixed(3)} s shared elapsed time</span>
        <span>PNG images are rendered from verified bounded Standard presentation products; raw IQ is never served to the browser.</span>
      </footer>
    </div>
  );
}

function axisDescription(kind: StandardViewKindV2) {
  if (kind === "waterfall") return "frequency → · elapsed time ↓ · color = power";
  if (kind === "glrt64") return "elapsed time → · independent response scales · GLRT64 alone proposes tracks";
  if (kind === "cfo_trajectory") return "elapsed time → · CFO ↑ · fitted degree 1/2/3 curves";
  return "elapsed time → · response ↑";
}

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
