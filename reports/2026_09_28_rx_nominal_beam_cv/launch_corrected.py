"""Preserve the original prefit failure and bind the corrected fold driver."""

from pathlib import Path

HERE = Path(__file__).resolve().parent
original = (HERE / "launch.py").read_text()
corrected = original.replace(
    'prefix = f"fold-{fold}"', 'prefix = f"corrected-fold-{fold}"'
).replace(
    'str(HERE / f"{prefix}.json")', 'str(HERE / f"fold-{fold}.json")'
).replace(
    'bound = [Path(__file__),', 'bound = [HERE / "launch.py", Path(__file__),'
)
# Execute unchanged resource limits and evidence binding with this launcher bound.
exec(compile(corrected, str(HERE / "launch.py"), "exec"))
