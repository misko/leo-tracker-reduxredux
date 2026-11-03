"""Isolated adapter: same source factors, an equivalent exact summation engine."""
import importlib.util
from pathlib import Path
import source_partition_fast

_path = Path(__file__).resolve().parent / 'whole_source_position.py'
_spec = importlib.util.spec_from_file_location('whole_source_exact_accelerated', _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
_module.partition = source_partition_fast.partition
WholeSourcePosition = _module.WholeSourcePosition
