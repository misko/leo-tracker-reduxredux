"""Compare all-track regional evidence from existing digest-verified native detections."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.contracts.algo08_region import Algo08Region
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from tools.pipeline_eval.variants.experimental.regional_reassignment import evaluate, summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "track_config", "offer"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared SHA-256")
    offer = Algo08Region.parse(json.loads(args.offer.read_bytes()))
    region = SearchRegion(offer.center, offer.width_km)
    began = process_time()
    tracks = prepare_tracks(json.loads(raw), TrackConfig(**json.loads(args.track_config.read_bytes())["config"]))
    tracks_cpu = process_time() - began
    began = process_time()
    cutoff = tracks["metadata"]["causal_cutoff_utc_ns"]
    catalogue = causal_catalogue(TleArchiveReader(args.archive), cutoff, element_parser=ElementParser())
    catalogue_cpu = process_time() - began
    began = process_time()
    result = evaluate(tracks, catalogue.catalogue, region)
    result.update(offer=offer.document(), native_sha256=digest, verdict=summarize(result["points"]),
                  snapshots=sorted({row["snapshot_digest"] for row in catalogue.provenance}),
                  cpu_s=dict(graph=tracks_cpu, catalogue=catalogue_cpu, probes=process_time() - began))
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
