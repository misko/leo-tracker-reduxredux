import { useEffect, useState } from "react";
import { getQualificationCampaign, getQualificationCampaigns } from "./api";
import type {
  QualificationCalibrationEvidenceV1,
  QualificationCampaignDetailV1,
  QualificationCampaignListItemV1,
  QualificationResultStatus,
  QualificationStratumV1,
} from "./contracts.generated";

export function QualificationCampaignBrowser() {
  const [campaigns, setCampaigns] = useState<QualificationCampaignListItemV1[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<QualificationCampaignDetailV1 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getQualificationCampaigns(controller.signal)
      .then((response) => {
        setCampaigns(response.items);
        setSelectedId((current) => current ?? response.items[0]?.campaign_id ?? null);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setDetail(null);
    getQualificationCampaign(selectedId, controller.signal)
      .then((campaign) => {
        setDetail(campaign);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [selectedId]);

  return (
    <main className="qualification-workspace">
      <aside className="campaign-browser" aria-label="WP11 qualification campaigns">
        <div className="browser-header">
          <div>
            <p className="section-label">WP11 CAMPAIGNS</p>
            <strong>{campaigns.length} authoritative</strong>
          </div>
          {loading ? <span className="loading-pulse">Loading</span> : null}
        </div>
        <div className="campaign-list">
          {campaigns.map((campaign) => (
            <button
              type="button"
              className={`campaign-row ${campaign.campaign_id === selectedId ? "selected" : ""}`}
              aria-pressed={campaign.campaign_id === selectedId}
              key={campaign.campaign_id}
              onClick={() => setSelectedId(campaign.campaign_id)}
            >
              <div className="row-topline">
                <ResultBadge status={campaign.result_status} />
                <time>{formatUtc(campaign.sealed_at)}</time>
              </div>
              <strong>{campaign.campaign_id}</strong>
              <span className="session-id">authoritative sealed</span>
              <div className="row-footer">
                <span>{campaign.observed_session_count} / 30 sessions</span>
                <span>{campaign.observed_stream_count} / 40 streams</span>
              </div>
            </button>
          ))}
          {!loading && campaigns.length === 0 ? (
            <p className="empty-list">No sealed qualification campaigns.</p>
          ) : null}
        </div>
      </aside>
      <section className="qualification-detail" aria-label="WP11 qualification detail">
        <CandidateOnlyNotice />
        {error ? (
          <div className="error-banner" role="alert">
            <strong>Unable to load qualification evidence</strong><span>{error}</span>
          </div>
        ) : null}
        {detail ? <CampaignDetail campaign={detail} /> : (
          <div className="empty-detail">
            <strong>{loading ? "Loading campaigns…" : "Select a campaign"}</strong>
            <span>Bounded authoritative campaign evidence will appear here.</span>
          </div>
        )}
      </section>
    </main>
  );
}

function CandidateOnlyNotice() {
  return (
    <aside className="candidate-only-notice" aria-label="Permanent scientific limitation">
      <strong>Candidate-only evidence</strong>
      <span>
        These results measure known-pilot candidate recovery only. They do not establish
        Starlink specificity, satellite attribution, or payload decoding.
      </span>
    </aside>
  );
}

function CampaignDetail({ campaign }: { campaign: QualificationCampaignDetailV1 }) {
  return (
    <div className="campaign-detail-content">
      <header className="campaign-heading">
        <div>
          <div className="heading-badges">
            <ResultBadge status={campaign.result_status} />
            <span className="badge status-complete">authoritative sealed</span>
            {campaign.production_accepted ? (
              <span className="badge status-complete">production accepted</span>
            ) : <span className="badge status-no_result">not production accepted</span>}
          </div>
          <h2>{campaign.campaign_id}</h2>
          <p>{campaign.reason}</p>
        </div>
        <dl className="campaign-accounting">
          <div><dt>Mathematical eligibility</dt><dd>{yesNo(campaign.mathematical_eligible)}</dd></div>
          <div><dt>Sessions</dt><dd>{campaign.observed_session_count} / {campaign.expected_session_count}</dd></div>
          <div><dt>Streams</dt><dd>{campaign.observed_stream_count} / {campaign.expected_stream_count}</dd></div>
          <div><dt>Sealed</dt><dd>{formatUtc(campaign.sealed_at)}</dd></div>
        </dl>
      </header>

      <section className="panel qualification-panel" aria-labelledby="strata-heading">
        <header className="panel-heading">
          <div><span>FOUR PREDECLARED STRATA</span><h3 id="strata-heading">Recovery and confidence</h3></div>
          <small>{campaign.strata.length} strata</small>
        </header>
        <div className="strata-grid">
          {campaign.strata.map((stratum) => <StratumCard stratum={stratum} key={stratum.stratum_id} />)}
        </div>
      </section>

      <section className="panel qualification-panel" aria-labelledby="calibration-heading">
        <header className="panel-heading">
          <div><span>AUTHORITATIVE PROVENANCE</span><h3 id="calibration-heading">Receiver calibration ranges</h3></div>
          <small>{campaign.calibrations.length} calibrations</small>
        </header>
        <div className="calibration-list">
          {campaign.calibrations.map((calibration) => (
            <CalibrationCard calibration={calibration} key={calibration.frequency_calibration_id} />
          ))}
        </div>
      </section>

      <section className="panel seal-panel" aria-labelledby="seal-heading">
        <header className="panel-heading">
          <div><span>IMMUTABLE BINDINGS</span><h3 id="seal-heading">Campaign seal</h3></div>
          <small>{campaign.pipeline_release_ids.length} releases</small>
        </header>
        <div className="seal-grid">
          <Evidence label="Pipeline releases" value={campaign.pipeline_release_ids.join(", ")} />
          <Evidence label="Capture" value={`${campaign.capture.logical_uri} · ${campaign.capture.digest}`} />
          <Evidence label="Outer seal" value={`${campaign.outer_seal.logical_uri} · ${campaign.outer_seal.digest}`} />
          <Evidence label="Outer sealed" value={formatNs(campaign.outer_sealed_utc_ns)} />
          <Evidence label="Release evidence" value={campaign.current_release_evidence_digest} />
        </div>
      </section>
    </div>
  );
}

function StratumCard({ stratum }: { stratum: QualificationStratumV1 }) {
  const recovery = stratum.recovery;
  return (
    <article className="stratum-card">
      <header><div><span>STRATUM</span><h4>{stratum.stratum_id}</h4></div><ResultBadge status={stratum.status} /></header>
      <p>{stratum.reason}</p>
      <div className="stratum-metrics">
        <Evidence label="Sessions" value={`${stratum.observed_session_count} / ${stratum.expected_session_count}`} />
        <Evidence label="Associated positives" value={`${stratum.associated_reference_positive_count} / ${stratum.reference_positive_count}`} />
        <Evidence label="Recovery" value={formatPercent(recovery.point_estimate)} />
        <Evidence label="Wilson lower" value={formatPercent(recovery.wilson_lower_bound)} />
        <Evidence label="Clopper–Pearson lower" value={formatPercent(recovery.clopper_pearson_lower_bound)} />
        <Evidence label="Confidence method" value={`${recovery.method} · ${formatPercent(recovery.confidence_level)}`} />
      </div>
      <div className="qam-strip">
        <strong>QAM noninferiority</strong>
        <ResultBadge status={qamStatus(stratum.qam.noninferiority_passed)} />
        <span>{stratum.qam.native_recovery_count} / {stratum.qam.reference_positive_count} recovered</span>
        <span>mean Δ {formatSignedPercent(stratum.qam.mean_accuracy_difference)}</span>
        <span>lower bound {formatSignedPercent(stratum.qam.accuracy_difference_lower_bound)}</span>
        <small>{stratum.qam.interval_method}</small>
      </div>
    </article>
  );
}

function CalibrationCard({ calibration }: { calibration: QualificationCalibrationEvidenceV1 }) {
  return (
    <article className="calibration-card">
      <header>
        <div><span>CALIBRATION</span><h4>{calibration.calibration_id}</h4></div>
        <strong>{calibration.radio_id} · RX{calibration.receiver_id}</strong>
      </header>
      <div className="calibration-grid">
        <Evidence label="Empirical center" value={`${formatNumber(calibration.center_hz)} Hz`} />
        <Evidence label="Uncertainty range" value={`${formatNumber(calibration.uncertainty_lower_hz)} to ${formatNumber(calibration.uncertainty_upper_hz)} Hz`} />
        <Evidence label="Receiver path" value={calibration.physical_receiver_id} />
        <Evidence label="Hardware epoch" value={calibration.hardware_epoch_id} />
        <Evidence label="Radio serial" value={calibration.radio_serial} />
        <Evidence label="Coverage" value={`${calibration.session_count} sessions · ${calibration.stream_count} streams`} />
        <Evidence label="Validity" value={`${formatNs(calibration.valid_from_utc_ns)} → ${calibration.valid_until_utc_ns === null ? "open" : formatNs(calibration.valid_until_utc_ns)}`} />
        <Evidence label="Method" value={calibration.method} />
      </div>
      <code>{calibration.evidence_uri}</code>
      <code>{calibration.evidence_digest}</code>
    </article>
  );
}

function Evidence({ label, value }: { label: string; value: string }) {
  return <div className="qualification-evidence"><span>{label}</span><strong>{value}</strong></div>;
}

function ResultBadge({ status }: { status: QualificationResultStatus | "insufficient" }) {
  return <span className={`result-badge result-${status}`}>{status}</span>;
}

function qamStatus(value: boolean | null): QualificationResultStatus {
  return value === null ? "inconclusive" : value ? "pass" : "fail";
}

function yesNo(value: boolean): string {
  return value ? "eligible" : "not eligible";
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number | null): string {
  if (value === null) return "—";
  const percentage = value * 100;
  return `${percentage >= 0 ? "+" : ""}${percentage.toFixed(2)} pp`;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function formatUtc(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    hour12: false, timeZone: "UTC",
  }).format(new Date(value));
}

function formatNs(value: number): string {
  return new Date(value / 1_000_000).toISOString().replace(".000Z", "Z");
}
