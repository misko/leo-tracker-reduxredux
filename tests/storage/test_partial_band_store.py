import gzip
import io
from types import SimpleNamespace as NS

import numpy as np
import pytest
from PIL import Image

from leo.application.partial_band import binding_for_capture, replay_partial_band
from leo.contracts.partial_band import PartialBandConfigurationV1
from leo.storage.partial_band import PartialBandStore


class Captures:
    def __init__(self):
        self.visits = tuple(
            NS(
                event=NS(
                    target=NS(channel=i + 1, edge="upper"),
                    valid_start_counter=1000 + i * 175000,
                    actual_lo_frequency_hz=1350000000,
                ),
                valid_sample_count=150000,
            )
            for i in range(2)
        )
        self.capture = NS(
            session_id="scan-fw-0123456789abcdef",
            manifest_sha256="sha256:" + "a" * 64,
            manifest=NS(
                receipt=NS(
                    plan=NS(
                        geometry=NS(
                            sample_rate_hz=1250000, bandwidth_hz=1250000, receiver_ids=(0, 1)
                        )
                    ),
                    visits=self.visits,
                    terminal=NS(first_counter=1000),
                )
            ),
        )
        self.reads = []

    def inspect(self, session_id):
        assert session_id == self.capture.session_id
        return self.capture

    def reader(self, session_id, *, expected):
        assert expected == self.capture
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read_visit_ci16(self, index):
        self.reads.append(index)
        return self.visits[index], np.zeros((150000, 2, 2), dtype="<i2")


def test_replay_resume_and_complete_artifacts(tmp_path):
    captures = Captures()
    sid, source = captures.capture.session_id, captures.capture.manifest_sha256
    products = PartialBandStore(tmp_path, read_only=False)
    assert products.status(sid, source).state == "not_started"
    first = replay_partial_band(
        captures=captures, products=products, session_id=sid, maximum_visits=1, maximum_workers=1
    )
    assert first["state"] == "partial"
    assert captures.reads == [0]
    second = replay_partial_band(
        captures=captures, products=products, session_id=sid, maximum_workers=1
    )
    assert second["state"] == "figures_ready"
    assert second["probe_count"] == 24 and second["candidate_probe_count"] == 0
    assert captures.reads == [0, 1]
    status = products.status(sid, source)
    for artifact in status.manifest.artifacts:
        raw = products.artifact(sid, source, artifact.name, artifact.sha256)
        if artifact.name.endswith(".png"):
            Image.open(io.BytesIO(raw)).verify()
        if artifact.name == "probes.jsonl.gz":
            assert len(gzip.decompress(raw).splitlines()) == 24
    replay_partial_band(captures=captures, products=products, session_id=sid, maximum_workers=1)
    assert captures.reads == [0, 1]
    destination = tmp_path / "publication"
    destination.mkdir()
    published = PartialBandStore(destination, read_only=False)
    assert published.import_completed(products, sid, source) == status.manifest
    assert published.status(sid, source).manifest == status.manifest
    assert products.status(sid, "sha256:" + "b" * 64).state == "not_started"
    with pytest.raises(ValueError, match="digest"):
        products.artifact(sid, source, "coverage.png", "sha256:" + "b" * 64)
    with pytest.raises(ValueError):
        products.status("../escape", source)
    next(p for p in tmp_path.rglob("coverage.png") if destination not in p.parents).unlink()
    with pytest.raises(ValueError, match="missing"):
        products.status(sid, source)


def test_missing_checkpoint_cannot_seal_and_read_only_cannot_write(tmp_path):
    binding = binding_for_capture(Captures().capture)
    with (
        PartialBandStore(tmp_path, read_only=False).writer(binding) as job,
        pytest.raises(ValueError, match="incomplete"),
    ):
        job.finish({})
    with pytest.raises(PermissionError), PartialBandStore(tmp_path).writer(binding):
        pass


def test_partial_band_replay_rejects_parallel_workers():
    with pytest.raises(ValueError, match="bounded partial-band replay budget"):
        replay_partial_band(
            captures=None,
            products=None,
            session_id="scan-fw-0123456789abcdef",
            maximum_workers=2,
        )


def test_different_configuration_has_separate_identity():
    captures = Captures()
    a = binding_for_capture(captures.capture)
    b = binding_for_capture(captures.capture, PartialBandConfigurationV1(filter_cutoff_hz=500000))
    assert a.digest != b.digest
