"""Keep the public receiver catalog in step with the executable registry."""

from pathlib import Path

from tools.pipeline_eval.__main__ import VARIANTS
from tools.pipeline_eval.cavity_runtime import PROFILES
from tools.pipeline_eval.scoring import ROLES


def test_catalog_covers_the_registered_receivers_and_active_selectors():
    guide = (Path(__file__).resolve().parents[2] / "algorithms.md").read_text()
    table = guide.split("<!-- receiver-variant-rows -->")[1].split(
        "<!-- end-receiver-variant-rows -->"
    )[0]
    assert table.strip().splitlines() == [
        f"| `{name}` | {description} |" for name, description in VARIANTS.items()
    ]
    for role in ROLES:
        assert f"`replay --role {role}`" in guide
    assert "`run --variant v5_secant_fit`" in guide
    for profile in PROFILES:
        assert f"`{profile}`" in guide
