"""Narrow metadata eligibility proposal; never authorizes cache reuse on its own."""
# ruff: noqa: E501

OLD = {
    "analysis/regional_position_fit.py": "sha256:c5aba169beafad93c11f707bf57ee2b72b7c343660be2f5d6943a22baead2ab8",
    "application/hard60_runner.py": "sha256:81ffd3839bf71d17ef2eb3425c0a16b876480850709a7306656e6f6361d5b5e9",
}
PRESENTATION = "application/regional_position_report.py"


def eligibility(old_sources, current_sources, old_configuration, current_configuration):
    """Return metadata conditions only; runtime model/state verification is mandatory.

    current_sources is the complete frozen required numerical dependency closure,
    expressed using the same public source keys as old_sources.
    """
    reasons = []
    for name, digest in current_sources.items():
        if name == PRESENTATION:
            continue
        expected = OLD.get(name, digest)
        if old_sources.get(name) != expected:
            reasons.append("unverified-source:" + name)
    if not set(OLD).issubset(current_sources):
        reasons.append("missing-required-known-source-closure")
    for name in old_sources.keys() - current_sources.keys():
        if name != PRESENTATION:
            reasons.append("unreviewed-source:" + name)
    expected = dict(current_configuration)
    policy = expected.pop("recovery_policy", None)
    if policy != "failed-coarse-box-v1":
        reasons.append("unexpected-current-recovery-policy")
    if old_configuration != expected:
        reasons.append("configuration-diff-not-only-added-recovery-policy")
    return dict(
        metadata_eligible=not reasons,
        reasons=sorted(reasons),
        reuse_authorized=False,
        scope="bootstrap/coarse fixed-point only",
        required_runtime_checks=[
            "input/analysis/evidence/snapshot/prior/score/bank",
            "bootstrap/coarse payload binding and fixed position",
            "finite feasible state and saved objective agreement",
        ],
        forbidden_aliases=["calibration", "association", "final", "recovery", "region"],
    )
