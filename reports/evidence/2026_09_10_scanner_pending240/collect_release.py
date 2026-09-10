"""Retain staged-host checks and the failed/corrected release gates, without IQ."""

from pathlib import Path

LOOPBACK = Path("/tmp/leo-staged-glrt-network.oQCyDX")
WEB = Path("/tmp/leo-report-assets-isolated.o4ZCRF")
RELEASE = Path("/tmp/leo-release-a37f5e92.lafvfb")
INTEGRATION = Path("/tmp/leo-main-integration.W66xm6")


def collect(archive):
    originals = []
    for name in (
        "build_fixture.py",
        "run_staged.py",
        "fair-receipt.json",
        "fair-configure.log",
        "fair-build.log",
        "fair-test_scanner_glrt_provider.log",
        "fair-test_spf_hop_adaptive_native.log",
        "fair-test_spf_hop_adaptive_policy.log",
        "sdk.so.build.json",
        "worker.build.json",
        "staged-definition.json",
        "staged-result.json",
        "staged-network.xml",
        "replay-diagnostics.xml",
        "report-assets-tests.xml",
    ):
        originals.append(archive(LOOPBACK / name, "staged-host/" + name))
    for name in ("verify_web.py", "receipt.json", "web.log"):
        originals.append(archive(WEB / name, "release-web-isolation/" + name))
    # These are copied, allowlisted evidence files, not mutable production data
    # or a recursive copy of a release, recording store or browser profile.
    for variant in ("failed", "corrected"):
        assert (RELEASE / variant / "receipt.json").is_file()
        for path in sorted((RELEASE / variant).rglob("*")):
            if path.is_file():
                name = str(path.relative_to(RELEASE))
                originals.append(archive(path, "release-qualification/" + name))
    originals.append(archive(RELEASE / "checkpoint.json", "release-qualification/checkpoint.json"))
    originals.append(
        archive(RELEASE / "snapshot_release.py", "release-qualification/snapshot_release.py")
    )
    assert (INTEGRATION / "receipt.json").is_file()
    for path in sorted(INTEGRATION.rglob("*")):
        if path.is_file():
            originals.append(
                archive(path, "main-integration/" + str(path.relative_to(INTEGRATION)))
            )
    return originals
