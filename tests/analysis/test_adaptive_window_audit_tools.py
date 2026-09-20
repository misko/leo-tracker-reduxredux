from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from tools.audit_adaptive_window import verify_png
from tools.inspect_adaptive_no_tracks import gap_runs
from tools.report_adaptive_window_audit import eligibility


def test_gap_runs_preserve_exact_four_second_boundary():
    assert gap_runs([0, 4_000_000_000, 8_000_000_001]) == [
        {"observations": 2, "span_s": 4.0},
        {"observations": 1, "span_s": 0.0},
    ]


@pytest.mark.parametrize(
    "observations,span,expected",
    [(14, 7, "eligible"), (13, 7, "sparse"), (14, 6.99, "short"), (8, 4, "short+sparse")],
)
def test_eligibility_boundaries(observations, span, expected):
    assert eligibility({"observation_count": observations, "span_s": span}) == expected


def test_png_audit_rejects_wrong_digest_and_dimensions(tmp_path):
    buffer = BytesIO()
    Image.new("RGB", (30, 20)).save(buffer, format="PNG")
    content = buffer.getvalue()
    path = tmp_path / "figure.png"
    path.write_bytes(content)
    digest = "sha256:" + sha256(content).hexdigest()
    assert verify_png("", path.as_uri(), digest, (30, 20))["verified"]
    assert not verify_png("", path.as_uri(), "sha256:" + "0" * 64)["verified"]
    assert not verify_png("", path.as_uri(), digest, (20, 30))["verified"]
