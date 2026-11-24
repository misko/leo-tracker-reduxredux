"""Optional first-arm veto for the original charted matched-support repair."""

from hashlib import sha256
from inspect import getsource, getsourcefile
from pathlib import Path


REPAIR_SHA256 = "f89e80dd65606b065e4c8097d0d3204362993e070dc7dd3f2c2590dc2c32b2a0"
POLICY_SHA256 = "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1"
ORIGINAL = '    measured["repair_fit_clocks"] = elapsed(cpu, wall)\n'
VETO = '''\
        if arm == "c0" and _completed_curved_veto(repaired[arm]):
            measured["repair_fit_clocks"] = elapsed(cpu, wall)
            details.update(attempted_refits=1, status="rejected",
                           reason="repair_original_joint_pair_gate",
                           finish={arm: readout(repaired[arm])},
                           fitted_arms=[arm], skipped_fit_arms=["fitted_c"])
            return None, details["reason"]
'''


def completed_curved_veto(record):
    """Decide only from explicit incompatibility in ordinary curved gates."""
    return any(row["compatible"] is False for row in record["gates"]["tracks"])


def with_first_arm_veto(repair_once, *, enabled=False):
    if not enabled:
        return repair_once

    namespace = repair_once.__globals__
    policy = namespace.get("pair_passes")
    if namespace.get("ARMS") != ("c0", "fitted_c") or policy is None:
        raise ValueError("Expected the original two-arm repair and paired policy")
    source_paths = [getsourcefile(obj) for obj in (repair_once, policy)]
    for path, expected in zip(source_paths, (REPAIR_SHA256, POLICY_SHA256), strict=True):
        if path is None or sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError("First-arm veto requires the original charted repair and policy sources")

    source = getsource(repair_once)
    if repair_once.__name__ != "repair_once" or source.count(ORIGINAL) != 1:
        raise ValueError("Expected the original repair refit boundary")
    source = source.replace(ORIGINAL, VETO + ORIGINAL, 1)
    research = dict(namespace, _completed_curved_veto=completed_curved_veto)
    exec(compile(source, source_paths[0], "exec"), research)
    return research["repair_once"]
