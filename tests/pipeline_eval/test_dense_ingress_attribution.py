import json
from unittest.mock import patch

import numpy as np
import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.contracts.short_window_recording import ShortWindowIndexV1
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.dense_ingress_attribution import batch_rows, bind_index_parser, line_rows


def observation(path):
    rows = []
    try:
        for row in ShortWindowReader(path).windows(stop_sequence=3):
            rows.append((row.index, row.samples.tobytes()))
    except BundleCorruptionError as error:
        return rows, str(error), type(error.__cause__)
    return rows, None, None


@pytest.fixture(params=(1, 2))
def sealed(request, tmp_path):
    rate = 2_500_000 if request.param == 1 else 10_000_000
    writer = ShortWindowWriter(tmp_path, "signed", configuration={"window_ms": 20, "sample_rate_hz": rate},
                               radio={"id": "test"}, receiver_ids=(0, 1), chunk_windows=2,
                               schema_version=request.param)
    for i in range(4):
        writer.append(sequence=i, target_id="carrier", samples=np.full((24, 2, 2), i, dtype="<i2"),
                      acquisition={"sequence": i, "utf8": "測定"}, powers=({}, {}))
    return writer.finish(stop_reason="max_visits")


@pytest.mark.parametrize("damage", (None, "compressed", "index", "index_syntax", "window", "member"))
def test_preserves_index_authority_and_full_closed_member(sealed, damage):
    manifest = sealed / "manifest.json"
    doc = json.loads(manifest.read_bytes())
    chunk = doc["chunks"][-1]
    if damage == "compressed":
        payload = sealed / chunk["payload_relative_path"]
        payload.write_bytes(payload.read_bytes()[:-2])
    elif damage in ("index", "index_syntax", "window"):
        index = sealed / chunk["index_relative_path"]
        lines = index.read_bytes().splitlines()
        if damage == "index_syntax":
            lines[-1] += b",{}"
        else:
            lines[-1] = canonical_json_bytes(json.loads(lines[-1]) | {"iq_sha256": "sha256:" + "0" * 64})
        data = b"\n".join(lines) + b"\n"
        index.write_bytes(data)
        if damage != "index":
            chunk.update(index_sha256=sha256_digest(data), index_bytes=len(data))
    elif damage == "member":
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
    manifest.write_bytes(canonical_json_bytes(doc))

    reference = observation(sealed)
    with patch.object(ShortWindowReader, "windows", bind_index_parser(ShortWindowReader.windows, batch_rows)):
        assert observation(sealed) == reference
    if damage is None:
        assert len(reference[0]) == 3 and reference[1] is None
    else:
        assert reference[1]


@pytest.mark.parametrize("model", (ShortWindowIndexV1, ShortWindowIndexV2))
def test_invalid_json_preserves_original_first_validation_error(model):
    payload = b"{}\r\n\xff\r\n"
    with pytest.raises(ValidationError) as reference:
        line_rows(payload, model)
    with pytest.raises(ValidationError) as candidate:
        batch_rows(payload, model)
    assert candidate.value.errors() == reference.value.errors()
