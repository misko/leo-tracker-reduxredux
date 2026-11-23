"""Run the installed graph with the short receiver's genuine saved packets."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from aperture_trial import archive_identity, machine, read
from full_short_raw import RECIPE_SHA
from joint_publication import run


HERE = Path(__file__).resolve().parent
PHYSICAL = Path("/var/tmp/leo-full-short-DS30-0016-pair")
SOUTH = Path("/var/tmp/leo-full-short-south-transfer-final")


def inputs(case):
    if case == "physical":
        pair = json.loads(gzip.decompress((HERE / "measurements/full-short-DS30-0016-raw.json.gz").read_bytes()))
        source, request = pair["runs"]["candidate"], pair["request"]
        return (Path(request["recording"]), request["archive"], Path(request["region_file"]),
                PHYSICAL / source["detection"]["path"], source["detection"]["native_sha256"],
                source["publication"]["receipt"]["region"])
    from full_short_south import INSIDE, checked
    pair = checked(INSIDE, "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0")
    study = read(HERE / "measurements/full-short-south.json")
    source = study["cases"]["far" if case == "south-far" else "containing"]
    detection, = (SOUTH / "containing/fast-scan-automatic-work").glob("*/detections.json")
    region = SOUTH / "far-offer.json" if case == "south-far" else Path(pair["region"])
    return Path(pair["recording"]), study["archive"], region, detection, source["native_pin"], source["receipt"]["region"]


def replay(case, root):
    recording, archive, region, packet, pin, offer = inputs(case)
    host = machine()
    if host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"] or set(host["threads"].values()) != {"1"}:
        raise ValueError("Expected the single low-priority benchmark slot")
    if "sha256:" + sha256(packet.read_bytes()).hexdigest() != pin:
        raise ValueError("The selected native packet differs from the original short run")
    args = SimpleNamespace(recording=recording, archive=Path(archive["root"]), region=region, saved=packet,
                           saved_digest=pin, output=root, verify_images=True, optimized_full_catalogue=True)
    run(args, saved_receiver=RECIPE_SHA, early_regional=True, keep_selected_rows=True)
    # The publisher validates the canonical packet and manifest before inference.
    # Geographic and catalogue binding are checked before admitting a scored row.
    report = read(root / "joint-research-receipt.json")
    if report["receipt"]["region"] != offer or archive_identity(args.archive) != archive or report["saved_digest"] != pin:
        raise ValueError("Saved graph replay changed its offer, archive or native binding")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=("physical", "south-inside", "south-far"))
    cli.add_argument("output", type=Path)
    options = cli.parse_args()
    replay(options.case, options.output)
