from pathlib import Path
import shutil
import subprocess
import sys


def test_exact_research_imports_preserve_installed_tools_namespace(tmp_path):
    root = Path(__file__).resolve().parents[2]
    checkout, payload = tmp_path/"checkout", tmp_path/"payload"
    research = checkout/"reports/ALGO08/v3"
    research.mkdir(parents=True)
    for name in ("exact_named_route.py", "held_adaptive_0160.py"):
        shutil.copyfile(root/"reports/ALGO08/v3"/name, research/name)
    for location in (checkout, payload):
        tools = location/"tools"
        tools.mkdir(parents=True)
        for name in ("algo08_position.py", "algo08_scan.py"):
            (tools/name).write_text(f"source = {location.name!r}\n")

    # Acquisition imports the tools namespace before the late research imports.
    probe = """
import sys

payload, research = sys.argv[1:]
sys.path[:0] = [payload, research]
import tools
import exact_named_route
from tools import algo08_scan, algo08_position

assert (algo08_scan.source, algo08_position.source) == ("payload", "payload")
"""
    result = subprocess.run([sys.executable, "-IB", "-c", probe, str(payload), str(research)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
