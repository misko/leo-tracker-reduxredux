import { useCallback, useEffect, useState } from "react";
import { getTleArchive, SkyUnavailableError } from "./sky-api";
import type { TleArchiveListV1 } from "./sky-contracts";

export function TleInterface() {
  const [archive, setArchive] = useState<TleArchiveListV1 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    return getTleArchive(signal)
      .then(setArchive)
      .catch((reason: Error) => {
        if (reason.name === "AbortError") return;
        setArchive(null);
        setError(
          reason instanceof SkyUnavailableError
            ? reason.message
            : "The local TLE archive could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <main className="workspace tle-workspace" aria-label="TLE archive">
      <section className="panel tle-panel">
        <header className="panel-heading tle-heading">
          <div>
            <span className="panel-eyebrow">LOCAL ORBITAL SOURCE INVENTORY</span>
            <h2>TLE archive</h2>
          </div>
          <button type="button" onClick={() => void load()} disabled={loading}>
            {loading ? "Reading archive…" : "Refresh"}
          </button>
        </header>
        <p className="tle-intro">
          Immutable local snapshots, newest first. “Local update” is when the collector wrote
          the verified source response to disk; satellite counts are read from each file.
        </p>
        {error ? <p className="sky-error">{error}</p> : null}
        {archive ? (
          <>
            <div className="tle-summary" aria-label="TLE archive summary">
              <span><strong>{archive.source_count.toLocaleString()}</strong> snapshots on disk</span>
              <span><strong>{providerCount(archive, "space-track")}</strong> Space-Track in table</span>
              <span><strong>{providerCount(archive, "huggingface")}</strong> Hugging Face in table</span>
              <span className="tle-root">Root <code>{archive.archive_root}</code></span>
            </div>
            {archive.truncated ? (
              <p className="tle-note">
                Showing the newest {archive.returned_count.toLocaleString()} of {archive.source_count.toLocaleString()} snapshots.
              </p>
            ) : null}
            <div className="sky-table-scroll">
              <table className="sky-table tle-table" aria-label="Local TLE snapshots">
                <thead>
                  <tr>
                    <th>Local update (UTC)</th>
                    <th>Satellites covered</th>
                    <th>Source</th>
                    <th>Snapshot SHA-256</th>
                    <th>Size</th>
                  </tr>
                </thead>
                <tbody>
                  {archive.snapshots.map((snapshot) => (
                    <tr key={`${snapshot.provider}:${snapshot.collected_utc_ns}:${snapshot.digest}`}>
                      <td>
                        <time dateTime={snapshot.collected_utc}>{formatUtc(snapshot.collected_utc_ns)}</time>
                        <small>{formatAge(snapshot.collected_utc_ns)}</small>
                      </td>
                      <td>{snapshot.satellite_count.toLocaleString()}</td>
                      <td>
                        <a href={snapshot.source_url} target="_blank" rel="noreferrer">
                          {snapshot.source_label}
                        </a>
                        <small>{snapshot.provider}</small>
                      </td>
                      <td><code title={snapshot.digest}>{shortDigest(snapshot.digest)}</code></td>
                      <td>{formatBytes(snapshot.byte_size)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : loading ? <p>Reading verified TLE files…</p> : null}
      </section>
    </main>
  );
}

function providerCount(
  archive: TleArchiveListV1,
  provider: "space-track" | "huggingface",
): number {
  return archive.snapshots.filter((snapshot) => snapshot.provider === provider).length;
}

function formatUtc(utcNs: number): string {
  return new Date(utcNs / 1_000_000).toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}

function formatAge(utcNs: number): string {
  const seconds = Math.max(0, (Date.now() - utcNs / 1_000_000) / 1_000);
  if (seconds < 90) return `${Math.round(seconds)} seconds ago`;
  if (seconds < 5_400) return `${Math.round(seconds / 60)} minutes ago`;
  if (seconds < 129_600) return `${Math.round(seconds / 3_600)} hours ago`;
  return `${Math.round(seconds / 86_400)} days ago`;
}

function shortDigest(digest: string): string {
  return `${digest.slice(7, 19)}…${digest.slice(-8)}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1_024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1_024).toFixed(1)} KiB`;
  return `${(bytes / 1_048_576).toFixed(2)} MiB`;
}
