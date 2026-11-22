"""Generate opaque single-edge IQ recordings. Inference reads only public/."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
from unittest.mock import patch

import numpy as np

from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools.pipeline_eval.qualification import clock_transfer_inputs, waveform_site_model as model
from tools.pipeline_eval.qualification.portable_v5_transfer import authentic_history
from tools.pipeline_eval.qualification.waveform_site_trial import revised


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def generate(work, seed=None, fresh=False):
    public = work / "public"
    if fresh and public.exists() and any(public.iterdir()):
        raise ValueError("Fresh confirmation requires an unused public directory")
    private = work / "scorer/answers.json"
    private.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if fresh and private.parent.stat().st_mode & 0o077:
        raise ValueError("Fresh confirmation requires a private scorer directory")
    if fresh and private.exists():
        raise FileExistsError(private)
    archive = public / "tle/archive/space-track"
    archive.mkdir(parents=True, exist_ok=True)
    received, nominal, history, objects = authentic_history()
    for item in history:
        digest = item["sha256"]
        name = f"{item['collected_utc_ns']}-{digest}.tle"
        (archive / name).write_bytes(objects[digest].read_bytes())
    updated, later, _ = revised(received, hashlib.sha256(nominal).hexdigest())
    causal = model.orbit._constellation(nominal, received)
    frames = model.pulse_bank()
    seed = secrets.token_bytes(32) if seed is None else bytes.fromhex(seed)
    if len(seed) != 32:
        raise ValueError("Expected a 32-byte seed")
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    answers, jobs = {}, []
    inputs = {"offers": {}, "recordings": {}}
    layout = [((48., 15.), "lower"), ((-33., 20.), "upper")]
    if fresh:
        from tools.pipeline_eval.qualification.holdout_geography import fresh_layout, fresh_offers
        layout = fresh_layout(rng)
    for index, (box, edge) in enumerate(layout):
        anchor = received + (3740 + 360 * index) * 10**9
        bank = clock_transfer_inputs._true_bank(nominal, updated, anchor, later)
        schedule = model.schedule()
        for row in schedule:
            offset = model.EDGE_HZ if edge == "upper" else -model.EDGE_HZ
            row.update(edge=edge, rf_hz=int(model.orbit.CHANNELS[row["channel"] - 1] + offset))
        with patch.object(model, "SITE_BOX", box), patch.object(model, "schedule", lambda: schedule):
            scan, scene = model.make_scene(bank, causal, anchor, rng)
        recording = rng.bytes(12).hex()
        width = 25.
        if fresh:
            width, offers = fresh_offers(rng, scene["coordinate"])
        else:
            offers = dict(scene["offers"], far=model.regional_offer(scene["coordinate"], 0, 1, 65.))
        for condition, center in offers.items():
            key = rng.bytes(12).hex()
            save(public / (key + ".json"), dict(center=center, width_km=width))
            if fresh:
                inputs["offers"][key] = hashlib.sha256((public / (key + ".json")).read_bytes()).hexdigest()
            answers[key] = dict(recording=recording, truth=scene["coordinate"], condition=condition)
            jobs.append(dict(recording=recording, offer=key))
        targets = [dict(target_id=str(r["channel"]), channel=r["channel"], edge=edge,
                        rf_center_hz=r["rf_hz"], lnb_lo_hz=9750000000,
                        rf_mapping_authority="simulation") for r in scan[:8]]
        writer = ShortWindowWriter(public, recording, configuration=dict(targets=targets,
            sample_rate_hz=model.RATE, window_ms=20), radio=dict(serial="simulated"), receiver_ids=(0, 1),
            schema_version=2)
        def clock(ns):
            return dict(realtime_ns=anchor + ns, monotonic_ns=10**10 + ns)
        for r in scan:
            start = scene["counter"] + r["relative_counter"]
            receipt = dict(host_delivery_clock=clock((r["relative_counter"] + model.SAMPLES)
                                                     * 10**9 // model.RATE))
            if r["visit"] == 0:
                receipt["utc_clock_bracket"] = dict(sample_counter=start, before=clock(-5000000),
                                                   after=clock(5000000))
            writer.append(sequence=r["visit"], target_id=str(r["channel"]),
                acquisition=dict(global_visit=r["visit"], generation=1, sample_start=start,
                    sample_end=start + model.SAMPLES, actual_if_center_hz=r["rf_hz"]-9750000000,
                    complete=True, validity_authority="provider_attested", validity_includes_guard=True,
                    quality_flags=[], retune_receipt=json.dumps(receipt)),
                samples=model.iq(r, scene, frames[edge]), powers=({}, {}))
        sealed = writer.finish(stop_reason="simulation schedule completed")
        if fresh:
            inputs["recordings"][recording] = ShortWindowReader(sealed).manifest_sha256
    rng.shuffle(jobs)
    save(private, dict(seed=seed.hex(), answers=answers))
    panel = dict(jobs=jobs, commitment=hashlib.sha256(private.read_bytes()).hexdigest())
    if fresh:
        # The archive names bind collection timestamps and the object digests.
        inputs["tle_objects"] = sorted(p.relative_to(public / "tle").as_posix() for p in archive.glob("*.tle"))
        panel["inputs"] = inputs
    save(public / "panel.json", panel)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--replay-seed", help="Recreate the sampled waveforms after unblinding")
    parser.add_argument("--fresh-sites", action="store_true", help="Sample new geographic areas for confirmation")
    args = parser.parse_args()
    generate(args.workspace, args.replay_seed, args.fresh_sites)
