import ast

import pytest

from tools.pipeline_eval.qualification import direct_lifetime_bundle as build
from tools.pipeline_eval.qualification.direct_lifetime_results import whole_cpu
from tools.pipeline_eval.variants import v5_direct_lifetime as lifetime


def test_projection_scope_is_restored_after_nested_failure():
    assert not lifetime.columns_active.get()
    with lifetime.projection_columns():
        with pytest.raises(ValueError), lifetime.projection_columns():
            raise ValueError("ranking error")
        assert lifetime.columns_active.get()
    assert not lifetime.columns_active.get()


def test_generated_kernel_excludes_original_qualification_workers():
    donor = build.ROOT / build.direct.VARIANTS
    source = build.kernel_source(
        {name: (donor / f"{name}.py").read_text() for name in build.DONORS}
    )
    compile(source, "bounded_kernels.py", "exec")
    names = build.module_nodes(source)
    assert {"decode_native", "bounded_states", "TrackField", "salvage", "nominate"} <= names.keys()
    assert {"worker", "run", "measured_worker"}.isdisjoint(names)
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom)) and "pipeline_eval" in ast.unparse(node)
        for node in ast.walk(ast.parse(source))
    )


def test_source_binding_rejects_absent_and_ambiguous_anchors():
    assert build.replace("xyz", "y", "a") == "xaz"
    for text in ("xz", "xyyz"):
        with pytest.raises(ValueError, match="specialization anchor"):
            build.replace(text, "y", "a")


def test_unstaged_entry_refuses_to_use_different_numerical_core():
    with pytest.raises(RuntimeError, match="source-bound direct lifetime release"):
        lifetime.main()


def test_cpu_sample_preserves_full_service_scope():
    assert whole_cpu("CPU time consumed: 1min 49.197s\n") == 109.197
    assert whole_cpu("CPU time consumed: 230ms\n") == pytest.approx(0.23)
    assert whole_cpu("Unobserved") is None
