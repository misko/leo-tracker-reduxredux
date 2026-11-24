from hashlib import sha256
import json
import os

import pytest

from reports.ALGO08.v3.raw_product_clocks import product_clocks


def test_clock_splits_require_the_original_bytes_and_publication_order(tmp_path):
    entries = {}
    begin = 1_700_000_000_000_000_000

    def put(key, obj, offset):
        path = tmp_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(obj).encode()
        path.write_bytes(body)
        os.utime(path, ns=(begin + offset, begin + offset))
        entries[key] = sha256(body).hexdigest()
        return path

    put("candidate-clock.json", {"clock": {"started_unix_ns": begin, "elapsed_s": 6, "exit_code": 0}}, 0)
    detections = put("candidate/receiver/detections.json", {}, 2_000_000_000)
    put("candidate/solver/terminal.json", {
        "decision": "ok", "native_sha256": "sha256:" + entries["candidate/receiver/detections.json"]
    }, 5_000_000_000)
    seal = json.dumps(entries).encode()
    (tmp_path / "prediction-seal.json").write_bytes(seal)
    pin = sha256(seal).hexdigest()
    result = product_clocks(tmp_path, pin, "candidate")
    assert [result[k] for k in ("launch_to_detections_s", "detections_to_terminal_s", "terminal_to_exit_s")] == [2, 3, 1]
    os.utime(detections, ns=(begin, begin + 7_000_000_000))
    with pytest.raises(ValueError, match="order"):
        product_clocks(tmp_path, pin, "candidate")
    detections.write_text('{"other": 1}')
    with pytest.raises(ValueError, match="differs from seal"):
        product_clocks(tmp_path, pin, "candidate")
