"""Deployment-owned scanner binding policy; no runtime or hardware imports."""

import re
from pathlib import Path


def scanner_binary_path(
    environment: str,
    revision: str,
    release_root: Path = Path("/opt/leo-tracker/releases"),
) -> str:
    """Preserve an explicitly pinned GLRT bundle across application releases.

    Bundle integrity is checked by the sealed-release and PPU lifecycle gates.
    This policy prevents deployment from mixing that bundle with the plain iiOD.
    Changing the detector bundle/algorithm/configuration remains explicit.
    """
    values: dict[str, str] = {}
    keys = {
        "LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH",
        "LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH",
        "LEO_SCANNER_GLRT_ALGORITHM_SHA256",
        "LEO_SCANNER_GLRT_CONFIGURATION_SHA256",
    }
    for line in environment.splitlines():
        if line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if separator and key in keys:
            if key in values:
                raise ValueError(f"duplicate scanner runtime binding: {key}")
            values[key] = value.strip().strip("'\"")
    manifest = values.get("LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH")
    if manifest is None:
        return str(release_root / revision / "runtime/scanner-iiod/iiod")
    pattern = re.escape(str(release_root)) + r"/[0-9a-f]{40}/runtime/scanner-glrt/bundle\.json"
    if re.fullmatch(pattern, manifest) is None:
        raise ValueError("scanner bundle must bind an exact canonical release-local GLRT manifest")
    for key in ("LEO_SCANNER_GLRT_ALGORITHM_SHA256", "LEO_SCANNER_GLRT_CONFIGURATION_SHA256"):
        if re.fullmatch(r"[0-9a-f]{64}", values.get(key, "")) is None:
            raise ValueError(f"scanner bundle requires an exact digest: {key}")
    return str(Path(manifest).with_name("iiod"))
