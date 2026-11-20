import subprocess

import pytest

from leo.analysis.research import phase_linear_geometry as reference
from tools.pipeline_eval.qualification import projector_archive_arm as audit
from tools.pipeline_eval.qualification.projector_arm import vectors
from tools.pipeline_eval.variants import orbit_projector


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    path = tmp_path_factory.mktemp("projection-fixture") / "projector"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-ffp-contract=off",
            audit.HARNESS,
            orbit_projector.KERNEL,
            "-lm",
            "-o",
            path,
        ],
        check=True,
    )
    return path


def test_standalone_projection_preserves_scores_and_array_sizes(executable, tmp_path):
    bank, times, phases = vectors()
    center = (62.1, -147.2)
    prepared = orbit_projector.prepare(bank, times, phases)
    original = reference.phase_linear_frequency(
        reference.prepare_phase_geometry(bank, times, phases), *center
    )
    fixture = tmp_path / "input.bin"
    shape = audit.write_fixture(fixture, prepared, center)
    assert fixture.stat().st_size == audit.HEADER.size + prepared.bytes
    expected = dict(
        compact_prepared_bytes=prepared.bytes, output_bytes=sum(a.nbytes for a in original)
    )
    output, memory = audit._run([executable], tmp_path, fixture, expected)
    assert memory["array_allocations"] == 1
    assert all(
        error <= limit
        for error, limit in zip(audit._errors(output, original, shape), audit.LIMITS, strict=True)
    )


def test_standalone_projection_rejects_truncation_overflow_and_trailing_bytes(executable, tmp_path):
    bank, times, _ = vectors()
    fixture = tmp_path / "input.bin"
    audit.write_fixture(fixture, orbit_projector.prepare(bank, times), (0.0, 0.0))
    payload = fixture.read_bytes()
    fields = list(audit.HEADER.unpack_from(payload))
    fields[1] = 2**62
    exaggerated = audit.HEADER.pack(*fields) + payload[audit.HEADER.size :]
    for data in (payload[:-8], payload + b"x", exaggerated):
        result = subprocess.run([executable], input=data, capture_output=True, check=False)
        assert result.returncode == 2
        assert not result.stdout
