"""Explicit-path additional-panel wrapper for frozen source_alpha050."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ADAPTER_PATH = HERE.parent / "source_balance" / "additional_adapter.py"
TEMPER_PATH = HERE / "model.py"
ADAPTER_SHA256 = "0a867565ac6a754ff958aa5f5f854baab2a09f61568c0327731dc9e471e59d92"
TEMPER_SHA256 = "7d0fd6d06cc3b3bf076badb11db8da061042a69e426e6b77d843ba0677580fe7"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if digest(ADAPTER_PATH) != ADAPTER_SHA256 or digest(TEMPER_PATH) != TEMPER_SHA256:
    raise RuntimeError("sealed additional adapter or source-temper model changed")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load("ds11_source_balance_additional_for_temper", ADAPTER_PATH)
temper = load("ds11_source_temper_sealed_for_additional", TEMPER_PATH)


def build_additional_model(
    documents, config, *, index, plan_path, runs_dir, identity_sidecar_path
):
    """Build alpha050 by tempering the explicit-path frozen alpha-one weights."""
    base = adapter.build_additional_model(
        documents,
        config,
        index=index,
        plan_path=plan_path,
        runs_dir=runs_dir,
        identity_sidecar_path=identity_sidecar_path,
        variant="source_receiver_equal",
    )
    alpha = temper.VARIANTS["source_alpha050"]
    weights = np.asarray(base.weights) ** alpha
    for row, weight in zip(base.assignments, weights, strict=True):
        if not row["unambiguous"] and weight != 1.0:
            raise AssertionError("ambiguous singleton weight changed")
    model = adapter.frozen.SourceBalancedIID(
        documents, config, weights, base.assignments
    )
    model.metadata = {
        **base.metadata,
        "variant": "source_alpha050",
        "alpha": alpha,
        "weight_rule": "explicit-path source_receiver_equal weight raised to 0.5",
        "wrapper_sha256": digest(Path(__file__)),
        "additional_adapter_sha256": ADAPTER_SHA256,
        "screen_frozen_source_temper_sha256": TEMPER_SHA256,
        "normalized_posterior": False,
        "additional_panel_status": "exposed exploratory follow-through",
    }
    return model
