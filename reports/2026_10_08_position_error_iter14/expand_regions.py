"""Apply the frozen additive region experiment uniformly to all development scans."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_10_08_position_error_iter06"
sys.path.insert(0, str(SOURCE))
import regions  # noqa: E402

if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == protocol["runner_sha256"]
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == digest
    regions.HERE = HERE
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        if label in protocol["reused"]:
            for relative, digest in protocol["reused"][label].items():
                assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == digest
            print(label, "reuse sealed region experiment", flush=True)
        else:
            regions.run(label, [25])
