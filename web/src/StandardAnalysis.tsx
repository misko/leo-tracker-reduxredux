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
  "qam",
  "cfo_trajectory",
  "power",
  "quality",
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
        <PngGallery
          sessionId={sessionId}
          includeTest={includeTest}
          detail={detail}
        />
      )}
    </section>
  );
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
