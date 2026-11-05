import subprocess
import sys


def test_standalone_localization_import_does_not_load_concrete_adapters():
    # Run in a fresh interpreter: prior pytest imports must not mask an eager
    # dependency on storage, acquisition, database, web or an older worker.
    code = """
import sys
def guard(event, args):
    if event == "import" and args[0].startswith((
        "leo.storage", "leo.operations", "leo.acquisition", "psycopg", "fastapi", "algo0"
    )):
        raise RuntimeError("Unrelated adapter loaded: " + args[0])
sys.addaudithook(guard)
from leo.application.localization_v3 import recover_numerical_checkpoint, recover_gap_tracks
assert callable(recover_numerical_checkpoint) and callable(recover_gap_tracks)
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_existing_application_exports_keep_their_identity_and_discoverability():
    code = """
import importlib
import leo.application as application
assert set(application.__all__) == set(application._MODULE_BY_NAME)
assert set(application.__all__) <= set(dir(application))
for name in application.__all__:
    module = importlib.import_module("leo.application." + application._MODULE_BY_NAME[name])
    assert getattr(application, name) is getattr(module, name)
    assert getattr(application, name) is application.__dict__[name]
try:
    application.not_an_application_export
except AttributeError:
    pass
else:
    raise AssertionError("Unknown attribute must raise AttributeError")
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
