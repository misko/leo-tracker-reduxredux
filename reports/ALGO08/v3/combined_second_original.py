"""Enroll and audit DS30-0339 without opening waveform bytes."""

import argparse
import json
import os
import stat
import subprocess
from hashlib import sha256
from pathlib import Path

from combined_small_panel import FROZEN, check, paired

HERE = Path(__file__).resolve().parent
CAMPAIGN = FROZEN.parent
NVME = Path("/srv/postgres-nvme")
BULK = Path("/srv/bulk")
CASE = "DS30-0339"
PLAN_PIN = "9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
CASE_PINS = {
    "pair.json": "222d9f45247fc1fb222fb16f6ffcd1b17bb5998c9c425142c32453bba70e7798",
    "input.json": "4cf442bae03e64b00c3784e98025eec6feb34720e1c9f00dec8f1ea41b68a33a",
    "authority.json": "0acb07a9dc39bad22abac086a4b6c8fe66f52e8d5d5b39e8528ade73d3bcea5a",
}
DONOR = Path("/dev/shm/leo-v3-saved-0316-pair-01/tle/archive/space-track")
MAX_NEW = 2_550_000_000
RATE = 4 * 1024**2


def select_rows(rows):
    return sorted(
        (r for r in rows if 1024 <= r["window_count"] <= 4096),
        key=lambda r: (abs(r["window_count"] - 1800), r["case"]),
    )


def checked_doc(path, pin):
    return json.loads(check(path, pin))


def extent(path, size=None):
    observed = path.lstat()
    if (
        path.resolve(strict=True) != path
        or not stat.S_ISREG(observed.st_mode)
        or (size is not None and observed.st_size != size)
    ):
        raise ValueError(f"Signed extent changed: {path}")
    return observed.st_size


def recording_roster(inventory, original):
    files, segments = [], []
    for row in inventory["segments"]:
        segment = Path(row["path"])
        if segment.parent != original:
            raise ValueError("Signed manifest leaves DS30-0339")
        path = segment / "manifest.json"
        document = checked_doc(path, row["manifest_digest"])
        segments.append(
            dict(
                name=segment.name, windows=document["window_count"], members=len(document["chunks"])
            )
        )
        files.append(
            dict(
                path=str(path),
                relative=str(path.relative_to(original)),
                kind="manifest",
                size=extent(path),
                sha256=row["manifest_digest"],
            )
        )
        for chunk in document["chunks"]:
            for kind, length, pin in (
                ("index", "index_bytes", "index_sha256"),
                ("payload", "compressed_bytes", "compressed_sha256"),
            ):
                name = Path(chunk[f"{kind}_relative_path"])
                if name.name != str(name):
                    raise ValueError("Signed member leaves its sealed segment")
                path = segment / name
                files.append(
                    dict(
                        path=str(path),
                        relative=str(path.relative_to(original)),
                        kind=kind,
                        size=extent(path, chunk[length]),
                        sha256=chunk[pin],
                    )
                )
    return files, segments


def controls(case_root, pair, authority):
    history = {}
    for role in ("installed", "successor"):
        attempt = case_root / role / f"attempt-{pair['generation']:06d}"
        pin = pair["attempt_result_sha256"][role]
        result = checked_doc(attempt / "result.json", pin)
        if (
            result["raw_identity"] != authority
            or result["process"]["exit_code"]
            or result["timing_scope"] != paired.TIMING_SCOPE
        ):
            raise ValueError("Historical control differs in source or timing scope")
        history[role] = {
            k: result[k]
            for k in (
                "process",
                "validation",
                "elapsed_s",
                "cpu_s",
                "native_sha256",
                "timing_scope",
            )
        } | dict(path=str(attempt), pin=pin)
    return history


def causal_roster(archive, authority):
    bodies = []
    for path in sorted((archive / "archive/space-track").glob("*.tle")):
        epoch, pin = path.stem.split("-", 1)
        if int(epoch) >= authority["causal_cutoff_utc_ns"]:
            raise ValueError("The archived view contains a later catalogue body")
        size = extent(path)
        donor = DONOR / path.name
        local = str(donor) if donor.is_file() and extent(donor) == size else None
        bodies.append(
            dict(path=str(path), name=path.name, size=size, sha256="sha256:" + pin, donor=local)
        )
    encoded = json.dumps(
        {r["name"]: r["sha256"][7:] for r in bodies}, sort_keys=True, separators=(",", ":")
    ).encode()
    if len(bodies) != 46 or "sha256:" + sha256(encoded).hexdigest() != authority["archive_sha256"]:
        raise ValueError("Archived causal roster fails its detached authority")
    return bodies


def enrollment():
    rows = select_rows(checked_doc(CAMPAIGN / "plan.json", PLAN_PIN)["cases"])
    if len(rows) != 18 or rows[0]["case"] != CASE:
        raise ValueError("Reserved middle recording changed")
    original = Path(rows[0]["recording"])
    scope = CAMPAIGN / "cases" / CASE
    pair, request, authority = (checked_doc(scope / name, pin) for name, pin in CASE_PINS.items())
    if (
        request["authority"] != authority
        or str(original) != authority["recording"]
        or any(authority[key] != value for key, value in request["expected"].items())
        or pair["authority_sha256"] != "sha256:" + CASE_PINS["authority.json"]
        or not pair["verified_pair"]
        or request["expected_admitted"] != 1276
    ):
        raise ValueError("The enrolled original authority changed")
    history = controls(scope, pair, authority)
    inventory = (
        Path(history["installed"]["path"])
        / "publication/fast-scan-inputs"
        / (authority["session_id"] + ".json")
    )
    files, segments = recording_roster(
        checked_doc(inventory, authority["inventory_sha256"]), original
    )
    roles = {
        k: sum(row["size"] for row in files if row["kind"] == k)
        for k in ("manifest", "index", "payload")
    }
    causal = causal_roster(Path(request["archive"]), authority)
    new_bytes = sum(roles.values()) + sum(body["size"] for body in causal if not body["donor"])
    if (
        roles != dict(manifest=27527, index=5495969, payload=2509593165)
        or sum(s["windows"] for s in segments) != authority["window_count"]
        or new_bytes != 2_525_845_744
        or new_bytes > MAX_NEW
    ):
        raise ValueError("Signed source exceeds frozen physical staging budget")
    check(CAMPAIGN / "offer.json", authority["region_sha256"])
    placements = [NVME / "fast-scan-recordings" / Path(r["recording"]).name for r in rows]
    return dict(
        case=CASE,
        plan_sha256=PLAN_PIN,
        candidates=[(r["case"], r["window_count"]) for r in rows],
        nvme_links=sum(p.is_symlink() for p in placements),
        authority=authority,
        segments=segments,
        files=files,
        causal=causal,
        counts=roles,
        new_backing_bytes=new_bytes,
        cap_bytes=MAX_NEW,
        rate_limit=RATE,
        minimum_copy_seconds=new_bytes / RATE,
        archived_controls=history,
        archived_order=pair["actual_order"],
        archived_same_lease=pair["same_lease"],
        expected_admitted=1276,
        offered_region=request["offered_region"],
        dataset_manifest_raw_authority_sha256=rows[0]["manifest_raw_authority_sha256"],
    )


def cache(paths):
    result = subprocess.run(
        ["/usr/bin/fincore", "--bytes", "--json", "-o", "RES,SIZE,FILE", *map(str, paths)],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stderr.strip():
        raise ValueError(f"Cache metadata was not authoritative: {result.stderr.strip()}")
    rows = json.loads(result.stdout)["fincore"]
    if len(rows) != len(paths) or {r["file"] for r in rows} != set(map(str, paths)):
        raise ValueError("Cache receipt is incomplete")
    return rows


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--privileged-cache", action="store_true")
    args = cli.parse_args()
    book = enrollment()
    if args.privileged_cache:
        if os.geteuid():
            raise ValueError("Use authoritative root credentials for this cache-only census")
        paths = [row["path"] for row in book["files"] if row["kind"] == "payload"]
        book["source_cache"] = cache(paths)
    print(json.dumps(book, sort_keys=True, indent=2, allow_nan=False))
