import importlib.util
import json
from pathlib import Path

import pytest

source = Path(__file__).resolve().parents[2] / "reports/2026_11_20_ds30_fast/freeze_ds30.py"
spec = importlib.util.spec_from_file_location("freeze_ds30", source)
freeze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze)


def acquisition(root, start, chunks=()):
    doc = dict(
        kind="short_window_iq_recording",
        created_utc_ns=start + 2,
        timing=dict(first_sample_estimate_utc_ns=start),
        chunks=list(chunks),
    )
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(doc))
    sha = freeze.digest(manifest.read_bytes())
    pairs = sorted((c["compressed_sha256"], c["index_sha256"]) for c in chunks)
    identity = (json.dumps(pairs, separators=(",", ":")) if pairs else json.dumps([sha])).encode()
    return dict(
        case_id="case",
        captured_utc_ns=start,
        window_count=0,
        source_inputs=[],
        tracking_inputs=[],
        recording_metadata=[],
        raw_recording=dict(
            segments=[dict(path=str(manifest), sha256=sha)],
            identity_sha256=freeze.digest(identity),
            chunks=list(chunks),
        ),
    )


def test_first_sample_at_lower_endpoint_is_included_even_when_empty(tmp_path):
    m = acquisition(tmp_path, freeze.START)
    assert freeze.verify_member(m) == m["raw_recording"]["identity_sha256"]


@pytest.mark.parametrize("stamp", [freeze.START - 1, freeze.CUTOFF])
def test_interval_rejects_prior_and_upper_endpoint(tmp_path, stamp):
    with pytest.raises(ValueError, match="outside"):
        freeze.verify_member(acquisition(tmp_path, stamp))


def test_full_content_identity_and_metadata_are_independently_checked(tmp_path):
    m = acquisition(tmp_path, freeze.START + 1, [{"compressed_sha256": "c", "index_sha256": "i"}])
    assert freeze.verify_member(m) == m["raw_recording"]["identity_sha256"]
    m["raw_recording"]["identity_sha256"] = "wrong"
    with pytest.raises(ValueError, match="identity"):
        freeze.verify_member(m)
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="changed source"):
        freeze.verify_member(m)
