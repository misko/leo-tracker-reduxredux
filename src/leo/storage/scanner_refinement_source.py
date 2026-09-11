"""Read-only adapters for bounded comparison probes in fixed and adaptive IQ."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from leo.analysis.starlink.refinement_comparison import RefinementProbe
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.errors import BundleNotFoundError
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import persisted_persistent_hop_analysis_source


@dataclass(frozen=True)
class ScannerComparisonSource:
    session_id: str
    session_kind: Literal["fixed", "adaptive"]
    input_manifest_sha256: str
    sample_rate_hz: int
    probe_ids: tuple[str, ...]
    read_probe: Callable[[str], RefinementProbe]


def select_visits(targets: list[int]) -> tuple[int, ...]:
    selected: list[int] = []
    for target in sorted(set(targets)):
        indices = [i for i, value in enumerate(targets) if value == target]
        # Interior thirds avoid selecting only the acquisition start/end.
        selected.extend(indices[i] for i in sorted({len(indices) // 3, 2 * len(indices) // 3}))
    return tuple(sorted(selected))


def comparison_session_ids(root: Path) -> tuple[str, ...]:
    fixed_store = PersistentHopIqStore.open_read_only(root)
    fixed = [
        (fixed_store.inspect(s).manifest.created_utc_ns, s) for s in fixed_store.session_ids()[:10]
    ]
    adaptive = AdaptiveHopIqStore(root, read_only=True)
    try:
        recent = sorted(
            ((s.manifest.created_utc_ns, s.session_id) for s in adaptive.iter_sessions()),
            reverse=True,
        )[:10]
        return tuple(s for _, s in sorted(fixed + recent, reverse=True))
    finally:
        adaptive.close()


@contextmanager
def comparison_source(root: Path, session_id: str) -> Iterator[ScannerComparisonSource]:
    fixed = PersistentHopIqStore.open_read_only(root)
    try:
        source = persisted_persistent_hop_analysis_source(fixed, session_id)
    except BundleNotFoundError:
        source = None
    if source is not None:
        fs = source.sample_rate_hz
        chosen = select_visits([v.target_index for v in source.visits])
        keys = {f"{session_id}:{v}:{rx}": (v, rx) for v in chosen for rx in source.receiver_ids}

        def read_fixed(key: str) -> RefinementProbe:
            visit, rx = keys[key]
            span = source.visits[visit]
            values = source.reader.read_valid_ci16(span.payload_sample_start, round(fs * 0.021))
            col = source.receiver_ids.index(rx)
            return RefinementProbe(
                key,
                visit,
                rx,
                span.target_index,
                (
                    span.valid_device_sample_counter
                    - source.receipt.session_start_device_sample_counter
                )
                / fs,
                fs,
                span.target.edge.value,
                values[:, col, 0].astype(float) + 1j * values[:, col, 1].astype(float),
            )

        yield ScannerComparisonSource(
            session_id, "fixed", source.input_manifest_sha256, fs, tuple(keys), read_fixed
        )
        return
    adaptive = AdaptiveHopIqStore(root, read_only=True)
    try:
        with adaptive.reader(session_id) as reader:
            capture = reader.session
            receipt = capture.manifest.receipt
            fs = receipt.plan.geometry.sample_rate_hz
            chosen = select_visits([v.event.target_index for v in receipt.visits])
            receivers = receipt.plan.geometry.receiver_ids
            keys = {f"{session_id}:{v}:{rx}": (v, rx) for v in chosen for rx in receivers}

            def read_adaptive(key: str) -> RefinementProbe:
                index, rx = keys[key]
                visit, raw = reader.read_visit_ci16(index)
                values = raw[: round(fs * 0.021), receivers.index(rx)]
                return RefinementProbe(
                    key,
                    index,
                    rx,
                    visit.event.target_index,
                    (visit.event.valid_start_counter - receipt.terminal.first_counter) / fs,
                    fs,
                    visit.event.target.edge.value,
                    values[:, 0].astype(float) + 1j * values[:, 1].astype(float),
                )

            yield ScannerComparisonSource(
                session_id, "adaptive", capture.manifest_sha256, fs, tuple(keys), read_adaptive
            )
    finally:
        adaptive.close()
