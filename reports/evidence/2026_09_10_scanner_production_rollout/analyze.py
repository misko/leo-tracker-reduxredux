"""Read-only verification of this one production recording; no radio access."""

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import httpx
import matplotlib.pyplot as plt
import numpy as np

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_glrt import ScannerGlrtStore

root = Path("/srv/bulk/leo/qualification/scanner-a2731551/attempt-3")
session_id = "scan-hop-f6f9037314e87e27"
store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
try:
    capture = store.verify(session_id)
finally:
    store.close()
receipt = capture.manifest.receipt
glrt = ScannerGlrtStore.open_read_only(Path("/srv/bulk/leo")).read(session_id)
assert glrt is not None and glrt.evidence is not None
rows = glrt.evidence.results
rate = receipt.plan.geometry.sample_rate_hz
assert rate == receipt.plan.geometry.bandwidth_hz == 2500000
assert receipt.plan.geometry.valid_visit_ms == 120
assert receipt.plan.geometry.nominal_duration_seconds == 300
assert receipt.plan.geometry.receiver_ids == (0, 1)
assert receipt.terminal.state == "completed" and receipt.source_span_attested
assert receipt.valid_duty_ppm >= 900000
assert receipt.unclassified_sample_count == receipt.unreceived_tail_sample_count == 0
assert glrt.evidence.delivery_complete and glrt.evidence.dropped_results == 0
assert len(rows) == receipt.complete_visit_count
evaluated = [r for r in rows if r.confirmation_end > r.confirmation_start]


def stats(values):
    return (
        dict(
            count=len(values),
            mean=float(np.mean(values)),
            p99=float(np.percentile(values, 99)),
            maximum=float(max(values)),
        )
        if values
        else dict(count=0)
    )


events = receipt.events[: receipt.complete_visit_count]
steady = events[1:]
summary = dict(
    session_id=session_id,
    manifest_sha256=capture.manifest_sha256,
    full_iq_verified=True,
    terminal_state=receipt.terminal.state,
    source_seconds=receipt.duty_denominator_sample_count / rate,
    valid_seconds=receipt.valid_sample_count / rate,
    valid_duty_percent=receipt.valid_duty_ppm / 10000,
    complete_visits=receipt.complete_visit_count,
    receiver_ids=list(receipt.plan.geometry.receiver_ids),
    sample_rate_hz=rate,
    bandwidth_hz=receipt.plan.geometry.bandwidth_hz,
    glrt_results=len(rows),
    delivery_complete=glrt.evidence.delivery_complete,
    dropped_results=glrt.evidence.dropped_results,
    verdicts=dict(Counter(r.verdict for r in rows)),
    masks=dict(Counter(r.search_window_mask for r in rows)),
    cpu_ms_evaluated=stats([r.cpu_ms for r in evaluated]),
    wall_ms_evaluated=stats([r.wall_ms for r in evaluated]),
    scheduler_reasons=dict(Counter(str(e.decision.reason) for e in events)),
    visits_by_target=dict(Counter(e.target_index for e in events)),
    retune_ms=stats(
        [(e.transition_after_counter - e.transition_before_counter) * 1000 / rate for e in steady]
    ),
    scheduler_lateness_ms=stats(
        [(e.transition_before_counter - e.invalid_start_counter) * 1000 / rate for e in steady]
    ),
    guard_ms=stats(
        [(e.valid_start_counter - e.transition_after_counter) * 1000 / rate for e in steady]
    ),
    unclassified_samples=receipt.unclassified_sample_count,
    unreceived_tail_samples=receipt.unreceived_tail_sample_count,
)
responses = {}
prefix = f"/api/v1/scanner/adaptive-sessions/{session_id}"
with httpx.Client(base_url="http://127.0.0.1:8090", timeout=30) as client:
    for url in ("/api/v1/scanner/adaptive-sessions?limit=5", prefix, prefix + "/glrt"):
        response = client.get(url)
        assert response.status_code == 200, (url, response.status_code)
        assert client.head(url).status_code == 200
        responses[url] = response.json()
assert responses[prefix]["capture"]["input_manifest_sha256"] == capture.manifest_sha256
assert responses[prefix + "/glrt"]["input_manifest_sha256"] == capture.manifest_sha256
summary["deployed_get_head_verified"] = True
for name, value in (
    ("summary.json", summary),
    ("public-glrt.json", glrt.model_dump(mode="json")),
    ("deployed-api.json", responses),
):
    with (root / name).open("x") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
origin = receipt.terminal.first_counter
times = np.array([(e.valid_start_counter - origin) / rate for e in events])
targets = np.array([e.target_index for e in events])
by_visit = {r.visit: r for r in rows}
positive = np.array([by_visit[e.visit_index].verdict == "starlink" for e in events])
full = np.array([by_visit[e.visit_index].search_window_mask == 63 for e in events])
fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True, constrained_layout=True)
axes[0].scatter(
    times[~positive],
    targets[~positive],
    s=5,
    color="#8a9ba8",
    label="No qualifying positive; absence not established",
)
axes[0].scatter(
    times[positive], targets[positive], s=9, color="#087e66", label="Lightweight GLRT candidate"
)
axes[0].set_yticks(range(8), [f"CH{i % 4 + 1}{'L' if i < 4 else 'U'}" for i in range(8)])
axes[0].invert_yaxis()
axes[0].set_title(
    f"Production 2.5 MS/s · {session_id}\n"
    "Actual 120 ms visits; RX1 detection, both receivers recorded"
)
axes[0].legend(fontsize=8, ncol=2, loc="upper right")
bins = np.arange(0, 301, 10)
duty, coverage = [], []
for lo, hi in zip(bins[:-1], bins[1:], strict=False):
    duty.append(
        float(
            np.maximum(0, np.minimum(times + 0.12, hi) - np.maximum(times, lo)).sum()
            / (hi - lo)
            * 100
        )
    )
    selection = (times >= lo) & (times < hi)
    coverage.append(float(full[selection].mean() * 100) if selection.any() else float("nan"))
axes[1].plot((bins[:-1] + bins[1:]) / 2, duty, label="Valid IQ capture duty", color="#245f86")
axes[1].plot(
    (bins[:-1] + bins[1:]) / 2, coverage, label="Full temporal-screen coverage", color="#ba6b1b"
)
axes[1].axhline(90, color="gray", linestyle=":", label="90% capture target")
axes[1].set_ylim(0, 105)
axes[1].set_ylabel("Percent per 10 s bin")
axes[1].legend(fontsize=8, ncol=3)
axes[2].scatter(
    [(r.valid_start - origin) / rate for r in evaluated],
    [r.cpu_ms for r in evaluated],
    s=4,
    color="#6a58a5",
    alpha=0.5,
    label="ARM worker CPU / evaluated dwell",
)
axes[2].axhline(100, color="#a5443e", linestyle="--", label="100 ms compute target")
axes[2].set_ylabel("CPU time (ms)")
axes[2].set_xlabel("Source-counter time since RF start (s)")
axes[2].legend(fontsize=8)
for axis in axes:
    axis.set_xlim(0, 300)
    axis.grid(alpha=0.15)
fig.savefig(root / "production-timeline.png", dpi=160)
plt.close(fig)
print(json.dumps(summary, indent=2))
