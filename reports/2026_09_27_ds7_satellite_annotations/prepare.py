"""Resolve frozen DS7 products and catalogue identities; never read raw IQ."""

import hashlib
import json
from pathlib import Path


def digest(p):
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    root = Path(__file__).resolve().parents[2]
    out = Path(__file__).parent / "local"
    out.mkdir(exist_ok=True)
    ds7 = root / "reports/2026_09_27_ds7_post_ds6"
    manifest = json.loads((ds7 / "manifest.json").read_text())
    tracks = {}
    for p in sorted(root.glob("reports/2026_09_27_ds7_wave*/**/*tracks.json")):
        tracks[digest(p)] = p
    banks = {}
    for p in sorted(root.glob(".leo/ds7-wave*/**/shortlists.json")):
        if "orbit-comparison" in str(p):
            continue
        doc = json.loads(p.with_name("manifest.json").read_text())
        banks.setdefault(doc["session_id"], (p.parent, doc))
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = {s.digest: s for s in archive.list_snapshots()}
    catalogues = {}
    rows = []
    for capture in manifest["captures"]:
        sid = capture["session_id"]
        folder, bank = banks[sid]
        track_path = tracks[bank["tracks_sha256"]]
        assert bank["manifest_sha256"] == capture["manifest_sha256"]
        pose_path = ds7 / "pose" / (sid + ".json")
        assert digest(pose_path) == capture["pose_file_sha256"]
        pose = json.loads(pose_path.read_text())
        assert pose["manifest_sha256"] == capture["manifest_sha256"]
        key = bank["baseline_snapshot_sha256"]
        if key not in catalogues:
            payload, _ = exclude_labelled_starlink_debris(archive.read(snapshots[key]))
            cat = parse_element_sets(payload)
            catalogues[key] = dict(names=list(cat.names), norad_ids=list(cat.satellite_numbers))
        assert len(catalogues[key]["names"]) == bank["catalogue_size"]
        rows.append(
            dict(
                session_id=sid,
                tracks=str(track_path),
                bank=str(folder),
                pose=str(pose_path),
                catalogue_digest=key,
                manifest_sha256=capture["manifest_sha256"],
                tracks_sha256=bank["tracks_sha256"],
                pose_sha256=capture["pose_file_sha256"],
                bank_sha256=digest(folder / "banks.npz"),
            )
        )
    (out / "inputs.json").write_text(
        json.dumps(
            dict(ds7_sha256=digest(ds7 / "manifest.json"), recordings=rows, catalogues=catalogues)
        )
    )
    print(json.dumps(dict(recordings=len(rows), catalogues=len(catalogues))))


if __name__ == "__main__":
    main()
