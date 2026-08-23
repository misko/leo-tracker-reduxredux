import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  getGlobe,
  getSkyDome,
  getSkyObjectDetail,
  getSkyObjectTleComparison,
  getSkySites,
  getSkySnapshots,
  SkyUnavailableError,
} from "./sky-api";
import type {
  GlobeFrameSetV1,
  SkySiteRowV1,
  SkySnapshotListV1,
  SkyViewFrameSetV1,
  SkyViewObjectDetailV1,
  SkyViewTleComparisonV1,
  SkyViewTrackV1,
  TleSnapshotRefV1,
} from "./sky-contracts";
import { rotateGlobe } from "./sky-interaction";
import {
  domeTrackPaths,
  interpolateHorizonTrack,
  interpolateSeries,
  interpolateTrack,
} from "./sky-interpolate";

const NS_PER_S = 1_000_000_000;
const SLIDER_HALF_WIDTH_S = 60;
const GLOBE_LIMIT = 12_000;

/** Everything drawn here is predicted from published element sets. */
const EVIDENCE_NOTE =
  "Predicted from published element sets. Not a detection, attribution or identification.";

function toIsoZ(utcNs: number): string {
  return new Date(utcNs / 1_000_000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function parseIsoZ(value: string): number | null {
  const parsed = Date.parse(value.endsWith("Z") ? value : `${value}Z`);
  return Number.isFinite(parsed) ? parsed * 1_000_000 : null;
}

export function SkyInterface() {
  const [mode, setMode] = useState<"globe" | "dome">("globe");
  const [anchorText, setAnchorText] = useState(() => toIsoZ(Date.now() * 1_000_000));
  const [anchorNs, setAnchorNs] = useState(() => Date.now() * 1_000_000);
  const [offsetS, setOffsetS] = useState(0);
  const [sites, setSites] = useState<SkySiteRowV1[]>([]);
  const [snapshots, setSnapshots] = useState<SkySnapshotListV1 | null>(null);
  const [pin, setPin] = useState<{ lat: number; lon: number; alt: number; label: string } | null>(
    null,
  );
  const [latText, setLatText] = useState("");
  const [lonText, setLonText] = useState("");
  const [maskDeg, setMaskDeg] = useState(10);
  const [downlinkGhz, setDownlinkGhz] = useState(11.7);
  const [globe, setGlobe] = useState<GlobeFrameSetV1 | null>(null);
  const [dome, setDome] = useState<SkyViewFrameSetV1 | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getSkySites(controller.signal)
      .then((body) => setSites(body.sites))
      .catch(() => setSites([]));
    getSkySnapshots(controller.signal)
      .then(setSnapshots)
      .catch(() => setSnapshots(null));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    getGlobe(anchorNs, GLOBE_LIMIT, controller.signal)
      .then(setGlobe)
      .catch((reason: Error) => {
        if (reason.name === "AbortError") return;
        setGlobe(null);
        setError(
          reason instanceof SkyUnavailableError
            ? reason.message
            : "The globe could not be loaded.",
        );
      });
    return () => controller.abort();
  }, [anchorNs]);

  useEffect(() => {
    if (!pin) {
      setDome(null);
      return;
    }
    const controller = new AbortController();
    getSkyDome(anchorNs, pin.lat, pin.lon, pin.alt, maskDeg, controller.signal)
      .then(setDome)
      .catch((reason: Error) => {
        if (reason.name === "AbortError") return;
        setDome(null);
        setError(
          reason instanceof SkyUnavailableError
            ? reason.message
            : "The sky view could not be loaded.",
        );
      });
    return () => controller.abort();
  }, [anchorNs, pin, maskDeg]);

  const displayNs = anchorNs + offsetS * NS_PER_S;

  const applyAnchor = useCallback(() => {
    const parsed = parseIsoZ(anchorText.trim());
    if (parsed === null) {
      setError("Enter a UTC instant such as 2026-08-20T15:03:17Z.");
      return;
    }
    setError(null);
    setAnchorNs(parsed);
    setOffsetS(0);
  }, [anchorText]);

  const pinFromInputs = useCallback(() => {
    const lat = Number.parseFloat(latText);
    const lon = Number.parseFloat(lonText);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
      setError("Latitude must be between -90 and 90.");
      return;
    }
    if (!Number.isFinite(lon) || lon <= -180 || lon > 180) {
      setError("Longitude must be greater than -180 and at most 180.");
      return;
    }
    setError(null);
    setPin({ lat, lon, alt: 0, label: `${lat.toFixed(5)},${lon.toFixed(5)}` });
    setMode("dome");
  }, [latText, lonText]);

  return (
    <main className="workspace sky-workspace" aria-label="Sky interface">
      <section className="panel sky-controls">
        <PanelHeading title="Sky" subtitle="Predicted orbital geometry" />
        <div className="sky-control-row">
          <label>
            Anchor (UTC)
            <input
              aria-label="Anchor instant"
              value={anchorText}
              onChange={(event) => setAnchorText(event.target.value)}
              onBlur={applyAnchor}
              onKeyDown={(event) => {
                if (event.key === "Enter") applyAnchor();
              }}
            />
          </label>
          <label>
            Latitude
            <input
              aria-label="Observer latitude"
              inputMode="decimal"
              value={latText}
              onChange={(event) => setLatText(event.target.value)}
            />
          </label>
          <label>
            Longitude
            <input
              aria-label="Observer longitude"
              inputMode="decimal"
              value={lonText}
              onChange={(event) => setLonText(event.target.value)}
            />
          </label>
          <button type="button" onClick={pinFromInputs}>
            Look up from here
          </button>
          <label>
            Reviewed site
            <select
              aria-label="Reviewed observer site"
              value=""
              onChange={(event) => {
                const site = sites.find((item) => item.name === event.target.value);
                if (!site) return;
                setLatText(site.latitude_deg.toFixed(6));
                setLonText(site.longitude_deg.toFixed(6));
                setPin({
                  lat: site.latitude_deg,
                  lon: site.longitude_deg,
                  alt: site.altitude_m,
                  label: site.label,
                });
                setMode("dome");
              }}
            >
              <option value="">Choose…</option>
              {sites.map((site) => (
                <option key={site.name} value={site.name}>
                  {site.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="sky-control-row">
          <div className="sky-mode" role="group" aria-label="View mode">
            <button
              type="button"
              aria-pressed={mode === "globe"}
              onClick={() => setMode("globe")}
            >
              Globe
            </button>
            <button
              type="button"
              aria-pressed={mode === "dome"}
              onClick={() => setMode("dome")}
              disabled={!pin}
            >
              Ground to sky
            </button>
          </div>
          <label className="sky-slider">
            Time {offsetS >= 0 ? "+" : ""}
            {offsetS} s
            <input
              type="range"
              aria-label="Time offset in seconds"
              min={-SLIDER_HALF_WIDTH_S}
              max={SLIDER_HALF_WIDTH_S}
              step={1}
              value={offsetS}
              onChange={(event) => setOffsetS(Number.parseInt(event.target.value, 10))}
            />
          </label>
          <span className="sky-instant" aria-label="Displayed instant">
            {toIsoZ(displayNs)}
          </span>
          {mode === "dome" ? (
            <>
              <label>
                Mask
                <select
                  aria-label="Horizon mask"
                  value={String(maskDeg)}
                  onChange={(event) => setMaskDeg(Number.parseInt(event.target.value, 10))}
                >
                  {[0, 5, 10, 20, 30].map((value) => (
                    <option key={value} value={value}>
                      {value}°
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Downlink (GHz)
                <input
                  type="number"
                  aria-label="Downlink frequency in GHz"
                  min="0.001"
                  max="300"
                  step="0.1"
                  value={downlinkGhz}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    if (value > 0 && value <= 300) setDownlinkGhz(value);
                  }}
                />
              </label>
            </>
          ) : null}
        </div>

        {error ? <p className="sky-error">{error}</p> : null}
        <SnapshotProvenance
          active={(mode === "dome" ? dome?.snapshot : globe?.snapshot) ?? null}
          archived={snapshots}
        />
      </section>

      {mode === "globe" ? (
        <GlobePanel frames={globe} displayNs={displayNs} pin={pin} />
      ) : (
        <DomePanel
          frames={dome}
          anchorNs={anchorNs}
          displayNs={displayNs}
          pin={pin}
          maskDeg={maskDeg}
          downlinkHz={downlinkGhz * 1e9}
        />
      )}
    </main>
  );
}

function PanelHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="panel-heading">
      <span className="panel-eyebrow">{subtitle}</span>
      <h2>{title}</h2>
    </header>
  );
}

/**
 * Name the snapshot the geometry on screen was actually computed from.
 *
 * The archive listing is fetched independently and its newest entry is not
 * necessarily the one a view used: each endpoint resolves the snapshot nearest
 * the selected anchor, so for a historical anchor the newest entry would
 * attribute the drawing to the wrong provider, time and digest. The rendered
 * frame set carries its own reference, and that is the only honest source.
 */
function SnapshotProvenance({
  active,
  archived,
}: {
  active: TleSnapshotRefV1 | null;
  archived: SkySnapshotListV1 | null;
}) {
  if (!active) {
    const empty = !archived || archived.snapshots.length === 0;
    return (
      <p className="sky-provenance">
        {empty
          ? "No element-set snapshot is available."
          : "Waiting for the view to report the snapshot it used…"}
      </p>
    );
  }
  const collected = new Date(active.collected_utc_ns / 1_000_000)
    .toISOString()
    .replace("T", " ")
    .slice(0, 19);
  return (
    <p className="sky-provenance" aria-label="Element set provenance">
      <strong>TLE record used for this view:</strong> {tleSourceLabel(active.provider)} ({active.provider}) · local
      snapshot collected {collected} UTC · {active.digest.slice(0, 23)}… ·{" "}
      {active.object_count.toLocaleString()} satellite records · selected as the snapshot nearest
      the anchor
      {archived && archived.source_count > 1
        ? ` · ${archived.source_count} archived snapshots on disk`
        : ""}
    </p>
  );
}

function GlobePanel({
  frames,
  displayNs,
  pin,
}: {
  frames: GlobeFrameSetV1 | null;
  displayNs: number;
  pin: { lat: number; lon: number } | null;
}) {
  const mount = useRef<HTMLDivElement | null>(null);
  const scene = useRef<GlobeScene | null>(null);

  useEffect(() => {
    if (!mount.current) return undefined;
    const created = createGlobeScene(mount.current);
    scene.current = created;
    return () => {
      created?.dispose();
      scene.current = null;
    };
  }, []);

  useEffect(() => {
    scene.current?.setFrames(frames);
  }, [frames]);

  useEffect(() => {
    scene.current?.setInstant(displayNs);
  }, [displayNs, frames]);

  useEffect(() => {
    scene.current?.setPin(pin);
  }, [pin, frames]);

  return (
    <section className="panel sky-canvas-panel" aria-label="Globe view">
      <div className="sky-canvas" ref={mount} aria-label="Orbital globe" />
      <div className="sky-readout">
        <span aria-label="Rendered object count">
          {frames ? `${frames.returned_object_count.toLocaleString()} objects` : "Loading…"}
        </span>
        {frames?.truncated ? (
          <span>
            of {frames.source_object_count.toLocaleString()} — the rest are not drawn
          </span>
        ) : null}
        <span>{EVIDENCE_NOTE}</span>
        <span>Drag to rotate · wheel to zoom</span>
      </div>
    </section>
  );
}

function DomePanel({
  frames,
  anchorNs,
  displayNs,
  pin,
  maskDeg,
  downlinkHz,
}: {
  frames: SkyViewFrameSetV1 | null;
  anchorNs: number;
  displayNs: number;
  pin: { lat: number; lon: number; alt: number; label: string } | null;
  maskDeg: number;
  downlinkHz: number;
}) {
  const [selectedCatalog, setSelectedCatalog] = useState<number | null>(null);
  const [detail, setDetail] = useState<SkyViewObjectDetailV1 | null>(null);
  const [comparison, setComparison] = useState<SkyViewTleComparisonV1 | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedCatalog || !frames || !pin) {
      setDetail(null);
      setComparison(null);
      setDetailError(null);
      setComparisonError(null);
      return;
    }
    const controller = new AbortController();
    setDetail(null);
    setComparison(null);
    setDetailError(null);
    setComparisonError(null);
    getSkyObjectDetail(
      anchorNs,
      pin.lat,
      pin.lon,
      pin.alt,
      selectedCatalog,
      downlinkHz,
      frames.snapshot.provider,
      frames.snapshot.digest,
      controller.signal,
    )
      .then(setDetail)
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setDetailError("Satellite detail could not be loaded.");
      });
    getSkyObjectTleComparison(
      anchorNs,
      pin.lat,
      pin.lon,
      pin.alt,
      selectedCatalog,
      frames.snapshot.provider,
      frames.snapshot.digest,
      controller.signal,
    )
      .then(setComparison)
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") {
          setComparisonError("The satellite's archived TLE comparison could not be loaded.");
        }
      });
    return () => controller.abort();
  }, [selectedCatalog, frames, pin, anchorNs, downlinkHz]);

  const visible = useMemo(() => {
    if (!frames) return [];
    return frames.tracks
      .map((track) => {
        const point = interpolateHorizonTrack(
          track.azimuth_deg,
          track.elevation_deg,
          track.range_km,
          frames.knot_utc_ns,
          displayNs,
        );
        return {
          track,
          azimuth: point.azimuth,
          elevation: point.elevation,
          range: point.range,
          x: point.domeX,
          y: point.domeY,
        };
      })
      .filter((item) => item.elevation > maskDeg);
  }, [frames, displayNs, maskDeg]);

  const trajectories = useMemo(
    () =>
      frames?.tracks.flatMap((track) =>
        domeTrackPaths(
          track.azimuth_deg,
          track.elevation_deg,
          track.range_km,
          frames.knot_utc_ns,
          maskDeg,
        ).map((path, index) => ({ track, path, index })),
      ) ?? [],
    [frames, maskDeg],
  );

  if (!pin) {
    return (
      <section className="panel" aria-label="Ground to sky view">
        <p>Enter a position, or choose a reviewed site, to look up from it.</p>
      </section>
    );
  }

  return (
    <section className="panel sky-canvas-panel" aria-label="Ground to sky view">
      <svg viewBox="-1.15 -1.15 2.3 2.3" className="sky-dome" aria-label="All-sky chart">
        <circle cx="0" cy="0" r="1" className="dome-horizon" />
        <circle cx="0" cy="0" r="0.6667" className="dome-ring" />
        <circle cx="0" cy="0" r="0.3333" className="dome-ring" />
        <line x1="-1" y1="0" x2="1" y2="0" className="dome-ring" />
        <line x1="0" y1="-1" x2="0" y2="1" className="dome-ring" />
        <text x="0" y="-1.04" className="dome-label" textAnchor="middle">N</text>
        <text x="1.04" y="0.03" className="dome-label" textAnchor="start">E</text>
        <text x="0" y="1.1" className="dome-label" textAnchor="middle">S</text>
        <text x="-1.04" y="0.03" className="dome-label" textAnchor="end">W</text>
        {trajectories.map((item) => (
          <path
            key={`${item.track.catalog_number}:${item.index}`}
            d={item.path}
            className={`dome-trajectory${selectedCatalog === item.track.catalog_number ? " selected" : ""}`}
            onClick={() => setSelectedCatalog(item.track.catalog_number)}
          >
            <title>{`${item.track.object_name} trajectory over 120 seconds`}</title>
          </path>
        ))}
        {visible.map((item) => (
          <circle
            key={item.track.catalog_number}
            cx={item.x}
            cy={-item.y}
            r={0.012}
            className={`dome-object${selectedCatalog === item.track.catalog_number ? " selected" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={`Select ${item.track.object_name}`}
            onClick={() => setSelectedCatalog(item.track.catalog_number)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSelectedCatalog(item.track.catalog_number);
              }
            }}
          >
            <title>{`${item.track.object_name} · az ${item.azimuth.toFixed(1)}° el ${item.elevation.toFixed(1)}°`}</title>
          </circle>
        ))}
      </svg>
      <div className="sky-readout">
        <span aria-label="Observer position">{pin.label}</span>
        <span aria-label="Visible object count">{visible.length} above {maskDeg}°</span>
        {frames?.truncated ? <span>list truncated</span> : null}
        <span>{EVIDENCE_NOTE}</span>
      </div>
      <DomeTable visible={visible} onSelect={setSelectedCatalog} selected={selectedCatalog} />
      {selectedCatalog && !detail && !detailError ? <p>Loading satellite detail…</p> : null}
      {detailError ? <p className="sky-error">{detailError}</p> : null}
      {detail ? <SatelliteDetail detail={detail} displayNs={displayNs} /> : null}
      {selectedCatalog && !comparison && !comparisonError ? (
        <p>Loading the latest TLE entries for this satellite…</p>
      ) : null}
      {comparisonError ? <p className="sky-error">{comparisonError}</p> : null}
      {comparison ? <TlePositionComparison comparison={comparison} /> : null}
    </section>
  );
}

function DomeTable({
  visible,
  onSelect,
  selected,
}: {
  visible: { track: SkyViewTrackV1; azimuth: number; elevation: number; range: number }[];
  onSelect: (catalogNumber: number) => void;
  selected: number | null;
}) {
  const rows = [...visible].sort((a, b) => b.elevation - a.elevation).slice(0, 12);
  return (
    <div className="sky-table-scroll">
      <table className="sky-table" aria-label="Visible objects">
        <thead>
          <tr>
            <th>Starlink satellite</th>
            <th>Azimuth</th>
            <th>Elevation</th>
            <th>Range</th>
            <th title="Average predicted Doppler rate over the full 120-second window at 10.825 GHz">
              Avg predicted rate <small>CH1 center · 10.825 GHz</small>
            </th>
            <th title="Average predicted Doppler rate over the full 120-second window at 12.575 GHz">
              Avg predicted rate <small>CH8 center · 12.575 GHz</small>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.track.catalog_number} className={selected === row.track.catalog_number ? "selected" : undefined}>
              <td>
                <button type="button" className="sky-object-link" onClick={() => onSelect(row.track.catalog_number)}>
                  {row.track.object_name}
                </button>
              </td>
              <td>{row.azimuth.toFixed(1)}°</td>
              <td>{row.elevation.toFixed(1)}°</td>
              <td>{row.range.toFixed(0)} km</td>
              <td>{formatSignedRate(predictedDopplerRate(row.track, 1))}</td>
              <td>{formatSignedRate(predictedDopplerRate(row.track, 8))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function predictedDopplerRate(track: SkyViewTrackV1, channel: 1 | 8): number {
  const prediction = track.predicted_doppler_rates.find(
    (item) => item.starlink_channel === channel,
  );
  return prediction?.average_rate_hz_s ?? Number.NaN;
}

function SatelliteDetail({ detail, displayNs }: { detail: SkyViewObjectDetailV1; displayNs: number }) {
  const shift = interpolateSeries(detail.doppler_shift_hz, detail.knot_utc_ns, displayNs);
  const minimum = Math.min(...detail.doppler_shift_hz);
  const maximum = Math.max(...detail.doppler_shift_hz);
  const width = 600;
  const height = 120;
  const span = Math.max(maximum - minimum, 1);
  const zeroY = Math.max(0, Math.min(height, height - ((0 - minimum) / span) * height));
  const points = detail.doppler_shift_hz
    .map((value, index) => {
      const x = (index / (detail.doppler_shift_hz.length - 1)) * width;
      const y = height - ((value - minimum) / span) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const orbit = detail.orbit;
  return (
    <section className="sky-object-detail" aria-label="Selected satellite details">
      <header><h3>{detail.object_name}</h3><span>NORAD {detail.catalog_number}</span></header>
      <dl className="sky-orbit-grid">
        <div><dt>Inclination</dt><dd>{orbit.inclination_deg.toFixed(3)}°</dd></div>
        <div><dt>Period</dt><dd>{orbit.period_minutes.toFixed(2)} min</dd></div>
        <div><dt>Perigee / apogee</dt><dd>{orbit.perigee_altitude_km.toFixed(0)} / {orbit.apogee_altitude_km.toFixed(0)} km</dd></div>
        <div><dt>Eccentricity</dt><dd>{orbit.eccentricity.toFixed(7)}</dd></div>
        <div><dt>RAAN</dt><dd>{orbit.right_ascension_deg.toFixed(3)}°</dd></div>
        <div><dt>Argument of perigee</dt><dd>{orbit.argument_of_perigee_deg.toFixed(3)}°</dd></div>
        <div><dt>Mean anomaly</dt><dd>{orbit.mean_anomaly_deg.toFixed(3)}°</dd></div>
        <div><dt>Mean motion</dt><dd>{orbit.mean_motion_rev_day.toFixed(5)} rev/day</dd></div>
        <div><dt>Element epoch</dt><dd>{toIsoZ(orbit.element_epoch_utc_ns)}</dd></div>
      </dl>
      <div className="sky-doppler-heading">
        <h4>Expected Doppler · 120-second window</h4>
        <span aria-label="Current expected Doppler">{formatSignedHz(shift)} at {(detail.downlink_frequency_hz / 1e9).toFixed(3)} GHz</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="sky-doppler-plot" aria-label="Expected Doppler over 120 seconds" preserveAspectRatio="none">
        <line x1="0" y1={zeroY} x2={width} y2={zeroY} />
        <polyline points={points} />
      </svg>
      <div className="sky-doppler-range"><span>−60 s · {formatSignedHz(detail.doppler_shift_hz[0])}</span><span>+60 s · {formatSignedHz(detail.doppler_shift_hz.at(-1) ?? 0)}</span></div>
      <p>{EVIDENCE_NOTE}</p>
    </section>
  );
}

function TlePositionComparison({
  comparison,
}: {
  comparison: SkyViewTleComparisonV1;
}) {
  return (
    <section className="sky-tle-comparison" aria-label="Satellite TLE position comparison">
      <header>
        <div>
          <span className="panel-eyebrow">ELEMENT-SET SENSITIVITY</span>
          <h4>Latest TLE records for {comparison.object_name}</h4>
        </div>
        <span>{toIsoZ(comparison.anchor_utc_ns)}</span>
      </header>
      <p>
        Each row propagates one of the latest five unique local TLE entries at the same instant
        and observer. Differences are relative to the exact TLE used by the sky view: element{" "}
        <code title={comparison.view_element_digest}>
          {comparison.view_element_digest.slice(7, 19)}…
        </code>, epoch {toIsoZ(comparison.view_element_epoch_utc_ns)}.
      </p>
      <div className="sky-table-scroll">
        <table className="sky-table sky-tle-table" aria-label="Latest satellite TLE entries">
          <thead>
            <tr>
              <th>Local TLE entry</th>
              <th>Element epoch</th>
              <th>Predicted position</th>
              <th>Δ 3D position</th>
              <th>Δ look angle</th>
              <th>Δ range</th>
              <th>Element SHA-256</th>
            </tr>
          </thead>
          <tbody>
            {comparison.entries.map((entry) => (
              <tr
                key={entry.element_digest}
                className={entry.is_view_element ? "selected" : undefined}
              >
                <td>
                  <strong>{entry.source_label}</strong>
                  <small>{formatUtcNs(entry.collected_utc_ns)}</small>
                  {entry.is_view_element ? <em>Used by view</em> : null}
                </td>
                <td>{formatUtcNs(entry.element_epoch_utc_ns)}</td>
                <td>
                  az {entry.azimuth_deg.toFixed(3)}° · el {entry.elevation_deg.toFixed(3)}°
                  <small>{entry.range_km.toFixed(3)} km range</small>
                </td>
                <td>{formatDistance(entry.position_difference_km)}</td>
                <td>{formatAngleDifference(entry.look_angle_difference_deg)}</td>
                <td>{formatSignedDistance(entry.range_difference_km)}</td>
                <td>
                  <code title={entry.element_digest}>{entry.element_digest.slice(7, 19)}…</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tle-note">
        Searched {comparison.searched_snapshot_count.toLocaleString()} of{" "}
        {comparison.archive_snapshot_count.toLocaleString()} local snapshots
        {comparison.search_truncated ? " (newest bounded search)" : ""}. Duplicate element sets
        from repeated downloads are shown once.
      </p>
    </section>
  );
}

function tleSourceLabel(provider: TleSnapshotRefV1["provider"]): string {
  return provider === "space-track"
    ? "Space-Track"
    : "Hugging Face · juliensimon/starlink-tle-latest";
}

function formatUtcNs(utcNs: number): string {
  return new Date(utcNs / 1_000_000)
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d{3}Z$/, " UTC");
}

function formatDistance(valueKm: number): string {
  return valueKm < 1 ? `${(valueKm * 1_000).toFixed(1)} m` : `${valueKm.toFixed(3)} km`;
}

function formatAngleDifference(valueDeg: number): string {
  return valueDeg < 0.01
    ? `${(valueDeg * 3_600).toFixed(2)} arcsec`
    : `${valueDeg.toFixed(4)}°`;
}

function formatSignedDistance(valueKm: number): string {
  const sign = valueKm >= 0 ? "+" : "−";
  const magnitude = Math.abs(valueKm);
  return magnitude < 1
    ? `${sign}${(magnitude * 1_000).toFixed(1)} m`
    : `${sign}${magnitude.toFixed(3)} km`;
}

function formatSignedHz(value: number): string {
  const sign = value >= 0 ? "+" : "−";
  return `${sign}${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })} Hz`;
}

function formatSignedRate(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const sign = value >= 0 ? "+" : "−";
  return `${sign}${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 1 })} Hz/s`;
}

interface GlobeScene {
  setFrames(frames: GlobeFrameSetV1 | null): void;
  setInstant(utcNs: number): void;
  setPin(pin: { lat: number; lon: number } | null): void;
  dispose(): void;
}

/**
 * Build the three.js globe.
 *
 * Deliberately a vector graticule rather than a photographic texture: it is
 * lighter, carries no image licensing question, stays crisp at any zoom, and
 * reads as an instrument rather than a picture.
 */
function createGlobeScene(mount: HTMLElement): GlobeScene | null {
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch {
    // No WebGL context available; the readout beside the canvas still reports
    // the object count, so the panel degrades rather than breaking.
    return null;
  }
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 100, 200_000);
  camera.position.set(0, 8_000, 22_000);
  camera.lookAt(0, 0, 0);

  const earthRadius = 6_378.137;
  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(earthRadius, 48, 32),
    new THREE.MeshBasicMaterial({ color: 0x0d1b26, transparent: true, opacity: 0.92 }),
  );
  scene.add(sphere);
  scene.add(
    new THREE.LineSegments(
      new THREE.WireframeGeometry(new THREE.SphereGeometry(earthRadius * 1.001, 24, 16)),
      new THREE.LineBasicMaterial({ color: 0x2f6f96, transparent: true, opacity: 0.35 }),
    ),
  );

  const points = new THREE.BufferGeometry();
  const cloud = new THREE.Points(
    points,
    new THREE.PointsMaterial({ color: 0xffd27f, size: 90, sizeAttenuation: true }),
  );
  scene.add(cloud);

  const pinMesh = new THREE.Mesh(
    new THREE.SphereGeometry(120, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0xff6b4a }),
  );
  pinMesh.visible = false;
  scene.add(pinMesh);

  mount.appendChild(renderer.domElement);

  let frames: GlobeFrameSetV1 | null = null;
  let instant = 0;
  let raf = 0;
  let rotationX = 0.15;
  let rotationY = 0;
  let dragging = false;
  let pointerX = 0;
  let pointerY = 0;
  let cameraDistance = 22_000;

  const canvas = renderer.domElement;
  canvas.style.touchAction = "none";
  const pointerDown = (event: PointerEvent) => {
    dragging = true;
    pointerX = event.clientX;
    pointerY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("dragging");
  };
  const pointerMove = (event: PointerEvent) => {
    if (!dragging) return;
    const next = rotateGlobe(
      { x: rotationX, y: rotationY },
      event.clientX - pointerX,
      event.clientY - pointerY,
    );
    rotationX = next.x;
    rotationY = next.y;
    pointerX = event.clientX;
    pointerY = event.clientY;
  };
  const pointerUp = (event: PointerEvent) => {
    dragging = false;
    canvas.classList.remove("dragging");
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  };
  const wheel = (event: WheelEvent) => {
    event.preventDefault();
    cameraDistance = Math.max(
      12_000,
      Math.min(60_000, cameraDistance * Math.exp(event.deltaY * 0.001)),
    );
  };
  canvas.addEventListener("pointerdown", pointerDown);
  canvas.addEventListener("pointermove", pointerMove);
  canvas.addEventListener("pointerup", pointerUp);
  canvas.addEventListener("pointercancel", pointerUp);
  canvas.addEventListener("wheel", wheel, { passive: false });

  const resize = () => {
    const width = mount.clientWidth || 640;
    const height = mount.clientHeight || 420;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  resize();
  const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
  observer?.observe(mount);

  const rebuild = () => {
    if (!frames || frames.tracks.length === 0) {
      points.setAttribute("position", new THREE.BufferAttribute(new Float32Array(0), 3));
      return;
    }
    const positions = new Float32Array(frames.tracks.length * 3);
    frames.tracks.forEach((track, index) => {
      const point = interpolateTrack(
        track.positions,
        frames!.knot_utc_ns,
        instant,
        frames!.quantum_km,
      );
      positions[index * 3] = point.x;
      positions[index * 3 + 1] = point.z;
      positions[index * 3 + 2] = -point.y;
    });
    points.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    points.computeBoundingSphere();
  };

  const loop = () => {
    scene.rotation.x = rotationX;
    scene.rotation.y = rotationY;
    camera.position.set(0, cameraDistance * 0.34, cameraDistance);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);

  return {
    setFrames(next) {
      frames = next;
      rebuild();
    },
    setInstant(utcNs) {
      instant = utcNs;
      rebuild();
    },
    setPin(pin) {
      if (!pin) {
        pinMesh.visible = false;
        return;
      }
      const lat = (pin.lat * Math.PI) / 180;
      const lon = (pin.lon * Math.PI) / 180;
      pinMesh.position.set(
        earthRadius * Math.cos(lat) * Math.cos(lon),
        earthRadius * Math.sin(lat),
        -earthRadius * Math.cos(lat) * Math.sin(lon),
      );
      pinMesh.visible = true;
    },
    dispose() {
      cancelAnimationFrame(raf);
      observer?.disconnect();
      canvas.removeEventListener("pointerdown", pointerDown);
      canvas.removeEventListener("pointermove", pointerMove);
      canvas.removeEventListener("pointerup", pointerUp);
      canvas.removeEventListener("pointercancel", pointerUp);
      canvas.removeEventListener("wheel", wheel);
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    },
  };
}
