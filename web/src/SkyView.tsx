import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  getGlobe,
  getSkyDome,
  getSkySites,
  getSkySnapshots,
  SkyUnavailableError,
} from "./sky-api";
import type {
  GlobeFrameSetV1,
  SkySiteRowV1,
  SkySnapshotListV1,
  SkyViewFrameSetV1,
} from "./sky-contracts";
import { domeProjection, interpolateAzimuth, interpolateSeries, interpolateTrack } from "./sky-interpolate";

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
          ) : null}
        </div>

        {error ? <p className="sky-error">{error}</p> : null}
        <SnapshotProvenance snapshots={snapshots} />
      </section>

      {mode === "globe" ? (
        <GlobePanel frames={globe} displayNs={displayNs} pin={pin} />
      ) : (
        <DomePanel frames={dome} displayNs={displayNs} pin={pin} maskDeg={maskDeg} />
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

function SnapshotProvenance({ snapshots }: { snapshots: SkySnapshotListV1 | null }) {
  if (!snapshots || snapshots.snapshots.length === 0) {
    return <p className="sky-provenance">No element-set snapshot is available.</p>;
  }
  const newest = snapshots.snapshots[snapshots.snapshots.length - 1];
  return (
    <p className="sky-provenance" aria-label="Element set provenance">
      {newest.provider} · collected {newest.collected_utc.replace("T", " ").slice(0, 19)} UTC ·{" "}
      {newest.digest.slice(0, 23)}…
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
      </div>
    </section>
  );
}

function DomePanel({
  frames,
  displayNs,
  pin,
  maskDeg,
}: {
  frames: SkyViewFrameSetV1 | null;
  displayNs: number;
  pin: { lat: number; lon: number; label: string } | null;
  maskDeg: number;
}) {
  const visible = useMemo(() => {
    if (!frames) return [];
    return frames.tracks
      .map((track) => {
        const azimuth = interpolateAzimuth(track.azimuth_deg, frames.knot_utc_ns, displayNs);
        const elevation = interpolateSeries(track.elevation_deg, frames.knot_utc_ns, displayNs);
        const range = interpolateSeries(track.range_km, frames.knot_utc_ns, displayNs);
        return { track, azimuth, elevation, range, ...domeProjection(azimuth, elevation) };
      })
      .filter((item) => item.elevation > maskDeg);
  }, [frames, displayNs, maskDeg]);

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
        {visible.map((item) => (
          <circle
            key={item.track.catalog_number}
            cx={item.x}
            cy={-item.y}
            r={0.012}
            className="dome-object"
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
      <DomeTable visible={visible} />
    </section>
  );
}

function DomeTable({
  visible,
}: {
  visible: { track: { object_name: string; catalog_number: number }; azimuth: number; elevation: number; range: number }[];
}) {
  const rows = [...visible].sort((a, b) => b.elevation - a.elevation).slice(0, 12);
  return (
    <table className="sky-table" aria-label="Visible objects">
      <thead>
        <tr>
          <th>Object</th>
          <th>Azimuth</th>
          <th>Elevation</th>
          <th>Range</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.track.catalog_number}>
            <td>{row.track.object_name}</td>
            <td>{row.azimuth.toFixed(1)}°</td>
            <td>{row.elevation.toFixed(1)}°</td>
            <td>{row.range.toFixed(0)} km</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
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
  let rotation = 0;

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
    rotation += 0.0006;
    scene.rotation.y = rotation;
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
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    },
  };
}
