"""Bounded optional adaptive-scan association stage over qualified evidence ports."""

import math
import time
from typing import Protocol

from leo.analysis.t1_at import associate
from leo.analysis.t1_at_discovery import discover_modes
from leo.analysis.t1_at_prediction import T1AtPredictor
from leo.contracts.digests import canonical_digest
from leo.contracts.scanner_tracking import TrackingInput
from leo.contracts.t1_at import T1AtInputV1, T1AtProductV1
from leo.contracts.t1_at_prediction import T1AtDiscoveryData


class T1AtInputs(Protocol):
    def load(self, session_id: str) -> T1AtInputV1 | T1AtDiscoveryData: ...


class T1AtProducts(Protocol):
    def load(self, prepared_input_sha256: str) -> T1AtProductV1 | None: ...
    def save(self, product: T1AtProductV1) -> None: ...


class T1AtService:
    def __init__(self, *, inputs: T1AtInputs, products: T1AtProducts):
        self.inputs, self.products = inputs, products

    def run(self, capture: TrackingInput, *, maximum_seconds: float = 120) -> T1AtProductV1:
        if not math.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
            raise ValueError("T1-AT budget must be in (0, 1800] seconds")
        if capture.capture_mode != "adaptive" or not capture.qualified:
            raise ValueError("T1-AT requires a qualified adaptive capture")
        started = time.monotonic()
        source = self.inputs.load(capture.session_id)
        prepared = source.manifest.evidence if isinstance(source, T1AtDiscoveryData) else source
        if (
            prepared.session_id != capture.session_id
            or prepared.input_manifest_sha256 != capture.input_manifest_sha256
            or prepared.analysis_manifest_sha256 != capture.analysis_manifest_sha256
        ):
            raise ValueError("T1-AT prepared evidence does not bind this capture/analysis")
        input_digest = canonical_digest(
            (source.manifest if isinstance(source, T1AtDiscoveryData) else prepared).model_dump(
                mode="json"
            )
        )
        cached = self.products.load(input_digest)
        if cached is not None:
            if (
                cached.session_id != capture.session_id
                or cached.input_manifest_sha256 != capture.input_manifest_sha256
                or cached.analysis_manifest_sha256 != capture.analysis_manifest_sha256
                or cached.prepared_input_sha256 != input_digest
            ):
                raise ValueError("cached T1-AT product authority differs")
            return cached
        if isinstance(source, T1AtDiscoveryData):
            predictor = T1AtPredictor(source)
            remaining = maximum_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("T1-AT preparation budget exhausted")
            modes = discover_modes(
                predictor.candidates, source.numbers, predictor, maximum_seconds=remaining
            )
            prepared = prepared.model_copy(
                update=dict(fitted_c_modes=modes["fitted-c"], zero_c_modes=modes["zero-c"])
            )
        remaining = maximum_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("T1-AT discovery budget exhausted")
        result = associate(prepared, maximum_seconds=remaining)
        product = T1AtProductV1.model_validate(
            {
                **result,
                "input_manifest_sha256": prepared.input_manifest_sha256,
                "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
                "prepared_input_sha256": input_digest,
            }
        )
        self.products.save(product)
        return product
