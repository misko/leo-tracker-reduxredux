"""Manifest-verified adapters from both scanner layouts to the tracking port."""

from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisConfigurationV1
from leo.scanner.adaptive_hop_products import AdaptiveHopAnalysisBindingV1
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.errors import BundleNotFoundError
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2


def _candidate(value) -> TrackingCandidate:
    return TrackingCandidate(
        **{key: getattr(value, key) for key in TrackingCandidate.__dataclass_fields__}
    )


class ScannerTrackingInputStore:
    def __init__(self, root: Path):
        self.fixed = PersistentHopIqStore.open_read_only(root)
        self.fixed_analysis = PersistentHopAnalysisStoreV2.open_read_only(root)
        self.adaptive = AdaptiveHopIqStore(root, read_only=True)
        self.adaptive_analysis = AdaptiveHopAnalysisStore(root, read_only=True)

    def close(self) -> None:
        self.adaptive.close()
        self.adaptive_analysis.close()

    def session_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.fixed.session_ids(), *self.adaptive.session_ids())))

    def captured_at(self, session_id: str) -> int:
        if self.adaptive.contains_session(session_id):
            return self.adaptive.inspect(session_id).manifest.created_utc_ns
        return self.fixed.inspect(session_id).manifest.created_utc_ns

    def load(self, session_id: str) -> TrackingInput:
        if self.adaptive.contains_session(session_id):
            return self._adaptive(session_id)
        published = self.fixed.inspect(session_id)
        manifest = published.manifest
        receipt = manifest.receipt
        analysis = self.fixed_analysis.inspect(session_id)
        if analysis.manifest.input_manifest_sha256 != published.manifest_sha256:
            raise ValueError("fixed analysis does not bind capture digest")
        chunks = self.fixed_analysis.published_chunks(session_id)
        expected = tuple(dict.fromkeys(v.sweep_index for v in receipt.visits))
        if tuple(c.sweep_index for c in chunks) != expected:
            raise ValueError("fixed analysis lacks complete sweep inventory")
        starts, cursor = {}, 0
        for visit in receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        visits = {v.visit_index: v for v in receipt.visits}
        probes = []
        for chunk in chunks:
            if chunk.input_manifest_sha256 != published.manifest_sha256:
                raise ValueError("fixed chunk capture digest differs")
            for p in chunk.probes:
                v = visits[p.visit_index]
                if p.target != v.target or p.target_index != v.target_index:
                    raise ValueError("fixed probe target differs from capture")
                probes.append(
                    TrackingProbe(
                        v.visit_index,
                        p.receiver_id,
                        p.probe_index,
                        p.probe_start_ms,
                        p.target.channel,
                        p.target.edge.value,
                        float(p.target.rf_center_hz - v.actual_if_offset_hz),
                        v.valid_device_sample_counter,
                        starts[v.visit_index],
                        tuple(_candidate(c) for c in p.fractional_candidates),
                    )
                )
        if len(probes) != (
            len(visits)
            * len(published.manifest.receiver_ids)
            * chunks[0].scheduled_probe_count_per_receiver_visit
        ):
            raise ValueError("fixed probe coverage is incomplete")
        return TrackingInput(
            session_id,
            "fixed",
            receipt.plan.sample_rate_hz,
            receipt.radio_id,
            receipt.stream_generation,
            published.manifest_sha256,
            analysis.manifest_sha256,
            canonical_digest(
                {"capture": published.manifest_sha256, "iq": manifest.uncompressed_sha256}
            ),
            getattr(manifest, "timing", None),
            receipt.capture_outcome == "complete" and receipt.continuity_attested,
            tuple(probes),
            chunks[0].configuration.probe_ms,
        )

    def _adaptive(self, session_id: str) -> TrackingInput:
        published = self.adaptive.inspect(session_id)
        manifest, receipt = published.manifest, published.manifest.receipt
        binding = AdaptiveHopAnalysisBindingV1(
            input_manifest_sha256=published.manifest_sha256,
            receipt=receipt,
            configuration=AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
                probe_stride_ms=120,
            ),
        )
        probes, cursor = [], 0
        with self.adaptive_analysis.job(binding) as job:
            metrics = job.manifest()
            if metrics is None:
                raise BundleNotFoundError("adaptive metrics are not complete")
            for product in job.published_visits():
                event = receipt.events[product.visit_index]
                for p in product.probes:
                    probes.append(
                        TrackingProbe(
                            product.visit_index,
                            p.receiver_id,
                            p.probe_index,
                            p.probe_start_ms,
                            product.target.channel,
                            product.target.edge.value,
                            float(product.target.rf_center_hz - event.actual_if_offset_hz),
                            product.valid_start_counter,
                            cursor,
                            tuple(_candidate(c) for c in p.candidates),
                        )
                    )
                cursor += product.valid_end_counter - product.valid_start_counter
        return TrackingInput(
            session_id,
            "adaptive",
            receipt.plan.geometry.sample_rate_hz,
            receipt.radio_id,
            f"adaptive-iio-{receipt.stream_generation:016x}" if receipt.stream_generation else "",
            published.manifest_sha256,
            canonical_digest(metrics.model_dump(mode="json")),
            canonical_digest(
                {"capture": published.manifest_sha256, "iq": manifest.uncompressed_sha256}
            ),
            manifest.timing,
            receipt.terminal.state == "completed" and receipt.source_span_attested,
            tuple(probes),
        )
