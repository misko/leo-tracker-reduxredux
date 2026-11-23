"""Capture the verified owner oracle and price the centre step before evidence."""

import argparse
import gzip
import json
from pathlib import Path
from time import process_time_ns
from types import SimpleNamespace

from aperture_trial import archive_identity, write
from arc_doppler_start_trial import source
from dense_full_short_crossover import TRACK_ASSET_PIN, file_sha
from dense_geographic_trial import host


HERE = Path(__file__).resolve().parent
CASES = ("physical", "north")
ALIAS_ARCHIVE = HERE / "measurements/fixed-causal-estimation.json.gz"
ALIAS_SHA = "1fbfdf76f378dbcc05830b941fd19eb77afd863cb736b7c6ebcf518c847ea016"
REQUESTS = {
    "physical": ("/dev/shm/leo-fixed-causal-physical-b/request.json",
                 "8f7276f7c86ea263e660e670e06d8875dfe5cefb6a806b98b11ef42b7ca39e4d"),
    "north": ("/dev/shm/leo-fixed-causal-north-a/request.json",
              "c1189daf2d73562dd9396643858fd0efbf855c1f59758dd0ab81fcd082756bf4"),
}


class CaptureComplete(Exception):
    pass


class OwnerOracle:
    def __init__(self, case, inputs):
        self.case, self.inputs = case, inputs
        self.result = None
        self.native = None
        if file_sha(ALIAS_ARCHIVE) != ALIAS_SHA:
            raise ValueError("The original signed alias archive changed")
        prior = json.loads(gzip.decompress(ALIAS_ARCHIVE.read_bytes()))["cases"]
        section = prior["DS30-0016" if case == "physical" else "northern"]["attempts"]
        if section["source"] != inputs["pin"]:
            raise ValueError("The signed alias witness used different detector factors")
        self.alias = section["trial"]
        self.started = process_time_ns()

    def bind(self, native, assets):
        from leo.contracts.digests import canonical_digest

        if (self.native is not None or canonical_digest(native) != self.inputs["pin"]
                or file_sha(assets / "tracks.json") != TRACK_ASSET_PIN):
            raise ValueError("The captured oracle changed its input or Graph")
        start = process_time_ns()
        _, self.binding, self.archived, self.terminal = source(
            "weak" if self.case == "physical" else self.case)
        if (self.inputs["archive"] != self.binding["archive"]
                or self.inputs["offer"] != self.binding["offer"]
                or self.inputs["pin"] != self.binding["native_sha256"]):
            raise ValueError("The saved source differs from the verified original publication")
        self.started += process_time_ns() - start
        self.native = native

    def prepare(self, original, native, *args, **kwargs):
        if native is not self.native:
            raise ValueError("The oracle received different receiver rows")
        return original(native, *args, **kwargs)

    def repair(self, _prepared, signed, _measured):
        from centre_oracle_step import ARMS, arm_step
        from fixed_causal_estimation import flatten
        from local_future_repair import memberships

        oracle_ns = process_time_ns() - self.started
        rows = {arm: flatten(memberships(signed, arm)) for arm in ARMS}
        readouts = {arm: dict(latlon=list(signed["arms"][arm]["endpoint_latlon"]),
                              rf_rms_hz=signed["arms"][arm]["RMS_hz"]) for arm in ARMS}
        aliases = dict(conditional_aliases=list(signed["node"]["aliases"]),
                       predictive_aliases={row["component"]: row["alias"] for row in signed["entries"]})
        if (rows["c0"] != rows["fitted_c"]
                or any(rows[arm] != sorted(map(tuple, self.archived["selected_rows"][arm]))
                       for arm in ARMS)
                or readouts != self.terminal["arms"]
                or any(aliases[key] != self.alias[key] for key in aliases)):
            raise ValueError("Original selected memberships, signed aliases or arm readouts changed")
        start = process_time_ns()
        # Pass only the oracle rows and the causal priors, never the oracle endpoint or posterior.
        args = tuple(signed[key] for key in ("scan", "node", "keep", "entries", "means", "model"))
        trials = {arm: arm_step(*args, arm) for arm in ARMS}
        self.result = dict(oracle_rows=rows["c0"], oracle_aliases=aliases,
                           oracle_arms=readouts, oracle_cpu_ns=oracle_ns,
                           trials=trials, paired_candidate_cpu_ns=process_time_ns()-start,
                           prior_model=signed["model"], causal_means_s=signed["means"])
        raise CaptureComplete()


def run(case, output):
    settings = host()
    from full_short_raw import RECIPE_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, geographic_projection
    from joint_publication import run as publish

    path, pin = REQUESTS[case]
    request_path = Path(path)
    if file_sha(request_path) != pin:
        raise ValueError("The original oracle request changed")
    inputs = json.loads(request_path.read_bytes())
    if (file_sha(Path(inputs["geographic"])) != GEOGRAPHIC_SHA
            or file_sha(Path(inputs["regional"])) != TRACK_SCORES_SHA):
        raise ValueError("Expected the original native geographic and regional scorers")
    policy = OwnerOracle(case, inputs)
    args = SimpleNamespace(
        saved=Path(inputs["saved"]), saved_digest=inputs["pin"],
        output=output.parent / f"{case}-scratch",
        recording=Path(inputs["recording"]), archive=Path(inputs["archive"]["root"]),
        region=Path(inputs["region"]), verify_images=False, optimized_full_catalogue=True,
    )
    try:
        publish(args, early_regional=True, keep_selected_rows=True, saved_receiver=RECIPE_SHA,
                geographic_projector=lambda: geographic_projection(
                    Path(inputs["geographic"]), Path(inputs["regional"])),
                reuse_cold_rows=True, reuse_grid_phase_states=True, local_future_policy=policy)
    except CaptureComplete:
        pass
    if policy.result is None or archive_identity(args.archive) != policy.binding["archive"]:
        raise ValueError("Expected the original complete saved selection on the causal archive")
    pins = {name: file_sha(HERE / name) for name in (
        "centre-oracle-step-protocol.md", "centre_oracle_step.py",
        "centre_oracle_step_trial.py", "measurements/fixed-causal-estimation.json.gz")}
    write(output, dict(case=case, binding=policy.binding, host=settings, sources=pins,
                       request_sha256=pin, **policy.result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
