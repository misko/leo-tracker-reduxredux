"""Exercise checkpoint replay and integrity failures against the existing corpus."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

import replay
import rerun_cold


def main(args):
    results = []
    for fold, variant in [("early_to_late", "cold"), ("late_to_early", "cold"),
                          ("early_to_late", "band_bias"), ("early_to_late", "no_bias_from_band")]:
        record = replay.replay(SimpleNamespace(input=args.input, tle_root=args.tle_root,
                                              fold=fold, variant=variant))
        results.append(dict(check="checkpoint", variant=variant, **record))
    with tempfile.TemporaryDirectory(prefix="three-track-replay-validation-") as tmp:
        root = Path(tmp)
        changed_input = root / "changed-input.json"
        changed_input.write_text('{"changed":true}\n')
        try:
            replay.replay(SimpleNamespace(input=changed_input, tle_root=args.tle_root,
                                          fold="early_to_late", variant="cold"))
        except ValueError as error:
            if "Digest mismatch" not in str(error):
                raise
            results.append(dict(check="changed_recording_rejected", reason=str(error)))
        else:
            raise AssertionError("Changed recording was accepted")
        original = replay.HERE
        try:
            shutil.copytree(original, root / "capsule")
            replay.HERE = root / "capsule"
            checkpoint = replay.HERE / "checkpoints/early_to_late/band_bias.json"
            checkpoint.write_bytes(checkpoint.read_bytes() + b"\n")
            try:
                replay.replay(SimpleNamespace(input=args.input, tle_root=args.tle_root,
                                              fold="early_to_late", variant="band_bias"))
            except ValueError as error:
                if "Capsule digest mismatch" not in str(error):
                    raise
                results.append(dict(check="changed_checkpoint_rejected", reason=str(error)))
            else:
                raise AssertionError("Changed checkpoint was accepted")
        finally:
            replay.HERE = original
        # Exercise fresh-rerun orchestration without repeating a scientific fit.
        # The stub checks the reader override and preserves the real input/TLE checks.
        original_run = rerun_cold.pipeline.run
        original_reader = rerun_cold.pipeline.TleArchiveReader
        original_discovery = rerun_cold.application.discover_channel_groups
        calls = []
        def checked_runner(input_path, output, *, maximum_seconds, tle_root):
            selected = rerun_cold.pipeline.TleArchiveReader(tle_root).select_latest_before(2**63-1)
            assert selected.digest == "sha256:c1341ed302fe6301e1dd4515e5bcee227d4c0c7aa975bdf572f8f3cbfd702072"
            try:
                rerun_cold.pipeline.TleArchiveReader(tle_root).select_latest_before(selected.collected_utc_ns)
            except ValueError:
                pass
            else:
                raise AssertionError("Noncausal pinned snapshot was accepted")
            assert maximum_seconds == 480 and input_path.exists() and not output.exists()
            calls.append(dict(input_sha256=replay.digest(input_path.read_bytes()), maximum_seconds=maximum_seconds))
            return dict(state="stubbed_validation_only")
        try:
            rerun_cold.pipeline.run = checked_runner
            for fold in ["early_to_late", "late_to_early"]:
                rerun_cold.main(SimpleNamespace(input=args.input, tle_root=args.tle_root,
                    fold=fold, output=root / ("fresh-" + fold), run=True))
                assert rerun_cold.pipeline.TleArchiveReader is original_reader
                assert rerun_cold.application.discover_channel_groups is original_discovery
                declaration = replay.verified_json(replay.HERE / "checkpoints" / fold / "derivation.json")
                assert calls[-1]["input_sha256"] == declaration["derived_input_sha256"]
            results.append(dict(check="fresh_rerun_orchestration", scope="Stub runner; no optimizer executed", calls=calls))
        finally:
            rerun_cold.pipeline.run = original_run
            assert rerun_cold.pipeline.TleArchiveReader is original_reader
            assert rerun_cold.application.discover_channel_groups is original_discovery
    payload = json.dumps(dict(passed=True, checks=results), indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    print(payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    main(parser.parse_args())
