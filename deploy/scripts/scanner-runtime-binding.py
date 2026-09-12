"""Deployment-owned scanner binding policy; no runtime or hardware imports."""

import json
import re
from pathlib import Path

SCANNER_ONLY_BINDINGS = {
    "LEO_SCANNER_RADIO_ID": "radio_pluto_19f2",
    "LEO_RADIOS_JSON": json.dumps(
        [
            {
                "radio_id": "radio_pluto_19f2",
                "serial": "10400056f695001322002d0010ad1719f2",
                "host": "192.168.1.21",
                "receiver_count": 2,
            }
        ],
        separators=(",", ":"),
    ),
}


def scanner_radio_bindings(environment: dict[str, str]) -> dict[str, str]:
    """Keep the explicitly selected single-profile radio through cutover."""
    if environment.get("LEO_SCANNER_PROFILE") != "single-rx-random-10m-300s-v1":
        return dict(SCANNER_ONLY_BINDINGS)
    selected = environment.get("LEO_SCANNER_RADIO_ID")
    raw = environment.get("LEO_RADIOS_JSON", "")
    try:
        radios = json.loads(raw)
    except ValueError as error:
        raise ValueError("single-RX profile requires one explicit radio binding") from error
    if (
        not selected
        or not isinstance(radios, list)
        or len(radios) != 1
        or not isinstance(radios[0], dict)
        or radios[0].get("radio_id") != selected
        or not radios[0].get("serial")
        or not radios[0].get("host")
    ):
        raise ValueError("single-RX profile requires one explicit matching radio binding")
    return {"LEO_SCANNER_RADIO_ID": selected, "LEO_RADIOS_JSON": raw}


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
        *SCANNER_ONLY_BINDINGS,
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
