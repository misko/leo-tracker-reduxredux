import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
binding = runpy.run_path(str(ROOT / "deploy/scripts/scanner-runtime-binding.py"))[
    "scanner_binary_path"
]
TARGET = "a" * 40
PIN = "b" * 40
BUNDLE = f"/opt/leo-tracker/releases/{PIN}/runtime/scanner-glrt/bundle.json"
ENVIRONMENT = (
    f"LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH={BUNDLE}\n"
    f"LEO_SCANNER_GLRT_ALGORITHM_SHA256={'c' * 64}\n"
    f"LEO_SCANNER_GLRT_CONFIGURATION_SHA256={'d' * 64}\n"
)


def test_plain_scanner_follows_application_release() -> None:
    assert binding("# no GLRT bundle\n", TARGET) == (
        f"/opt/leo-tracker/releases/{TARGET}/runtime/scanner-iiod/iiod"
    )


def test_glrt_runtime_stays_with_explicit_bundle_pin() -> None:
    assert binding(ENVIRONMENT, TARGET) == str(Path(BUNDLE).with_name("iiod"))


@pytest.mark.parametrize(
    "manifest",
    [
        "",
        "/tmp/bundle.json",
        BUNDLE.replace(PIN, "current"),
        BUNDLE.replace("runtime/", "../runtime/"),
    ],
)
def test_noncanonical_bundle_is_rejected(manifest: str) -> None:
    with pytest.raises(ValueError, match="canonical"):
        binding(ENVIRONMENT.replace(BUNDLE, manifest), TARGET)


@pytest.mark.parametrize("key", ["ALGORITHM", "CONFIGURATION"])
def test_missing_or_duplicate_digest_is_rejected(key: str) -> None:
    name = f"LEO_SCANNER_GLRT_{key}_SHA256"
    lines = ENVIRONMENT.splitlines(keepends=True)
    selected = next(line for line in lines if line.startswith(name))
    with pytest.raises(ValueError, match="exact digest"):
        binding(ENVIRONMENT.replace(selected, ""), TARGET)
    with pytest.raises(ValueError, match="duplicate"):
        binding(ENVIRONMENT + selected, TARGET)


def test_duplicate_manifest_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        binding(ENVIRONMENT + ENVIRONMENT.splitlines()[0] + "\n", TARGET)
