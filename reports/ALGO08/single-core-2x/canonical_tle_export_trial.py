"""Time canonical serialization of one complete verified orbital catalogue."""
import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from sgp4 import exporter
from leo.sky.propagation import element_line_checksum, parse_element_sets


def measure(snapshot):
    raw = snapshot.read_bytes()
    if sha256(raw).hexdigest() != snapshot.stem.split("-")[1]:
        raise ValueError("Unexpected snapshot digest")
    catalogue = parse_element_sets(raw.decode("ascii"))
    results = []
    for method in ("original", "table", "table", "original"):
        context = patch.object(exporter, "compute_checksum", element_line_checksum) if method == "table" else nullcontext()
        with context:
            start = process_time()
            lines = [exporter.export_tle(satellite) for satellite in catalogue.satellites]
            elapsed = process_time() - start
        digest = sha256("".join(line + "\n" for pair in lines for line in pair).encode("ascii")).hexdigest()
        results.append(dict(method=method, cpu_s=elapsed, sha256=digest))
    if len({row["sha256"] for row in results}) != 1:
        raise ValueError("Exported orbital records changed")
    return dict(snapshot=snapshot.name, records=len(catalogue), results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    print(json.dumps(measure(parser.parse_args().snapshot), indent=2))
