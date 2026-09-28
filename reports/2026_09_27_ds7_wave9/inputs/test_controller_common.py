import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).with_name("controller_common.py")
    spec = importlib.util.spec_from_file_location("wave9_controller_common", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failure_before_first_freeze_has_no_final_path(tmp_path) -> None:
    controller = _module()

    assert controller.last_validated_path(tmp_path, 73, []) is None


def test_failure_after_prepare_retains_last_validated_snapshot(tmp_path) -> None:
    controller = _module()
    previous = tmp_path / "inputs-through-single-073-ready-v1.json"
    previous.write_text("validated\n")
    validated = ["session-073"]
    prepared = ["session-073", "session-074"]

    final = controller.last_validated_path(tmp_path, 73, validated)

    assert len(prepared) > len(validated)
    assert final == previous
    assert controller.digest(final) == (
        "sha256:cb424b9cab55c18f6faa61082e3f71d6efa7e5dd398c6160f4e99e8777d21895"
    )
