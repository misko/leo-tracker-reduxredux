import pytest

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.errors import BundleCorruptionError
from tests.storage.test_adaptive_hop_history import publish_capture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_pinned_source_reads_actual_ci16_lazily_and_closes(tmp_path, rate, mode):
    capture = publish_capture(tmp_path, rate=rate, mode=mode, count=30)
    store = AdaptiveHopIqStore(tmp_path, read_only=True)
    inputs = AdaptiveHopAnalysisInputStore(store)
    assert inputs.session_ids() == (capture.session_id,)
    with inputs.source(capture.session_id) as source:
        assert source.input_manifest_sha256 == capture.manifest_sha256
        samples = source.read_visit(25)
        assert samples[0, 0] == 26 + 2j
        assert samples[0, 1] == ((2 if mode == "adaptive" else 1) + 10) - 3j
        assert samples.shape == (rate * 120 // 1000, 2)
        with pytest.raises(ValueError, match="complete retained"):
            source.read_visit(29)
    with pytest.raises(RuntimeError, match="closed"):
        source.read_visit(0)
    store.close()


def test_corrupted_late_chunk_fails_before_analysis_and_closes_source(tmp_path):
    capture = publish_capture(tmp_path, count=10)
    path = (
        tmp_path
        / "scanner-adaptive-recordings"
        / capture.session_id
        / capture.manifest.chunks[1].relative_path
    )
    path.write_bytes(b"damaged")
    store = AdaptiveHopIqStore(tmp_path, read_only=True)
    with (
        pytest.raises(BundleCorruptionError),
        AdaptiveHopAnalysisInputStore(store).source(capture.session_id) as source,
    ):
        source.read_visit(0)
        source.read_visit(8)
    with pytest.raises(RuntimeError, match="closed"):
        source.read_visit(0)
    store.close()
