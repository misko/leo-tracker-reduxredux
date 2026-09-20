import numpy as np
import pytest

from leo.cli.firmware_adaptive_import import _timing
from leo.scanner.host_adaptive_ports import HostAdaptiveHopVisitBlock
from leo.storage.adaptive_hop import AdaptiveHopIqStore, HostAdaptiveHopIqManifestV6
from tests.cli.test_counter_utc_import import counter_document


@pytest.mark.parametrize("rate", [10_000_000, 15_000_000, 20_000_000])
def test_counter_timing_manifest_seals_without_changing_old_versions(tmp_path, rate):
    document, receipt = counter_document(rate)
    timing = _timing(document, receipt)
    store = AdaptiveHopIqStore(tmp_path)
    try:
        writer = store.begin(receipt.session_id, receipt.plan)
        try:
            for visit in receipt.visits:
                samples = np.zeros((receipt.plan.geometry.valid_visit_samples, 1), np.complex64)
                writer.append(HostAdaptiveHopVisitBlock(samples, (0,), visit))
            published = writer.finish(receipt, timing=timing)
            assert isinstance(published.manifest, HostAdaptiveHopIqManifestV6)
            assert store.verify(receipt.session_id) == published
            assert store.inspect(receipt.session_id).manifest.timing == timing
        finally:
            writer.abort()
    finally:
        store.close()
