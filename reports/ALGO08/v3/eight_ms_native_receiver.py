"""Bind the checked live 20/8 ms receiver to the frozen saved history recipe."""

from pathlib import Path


SAVED_SELECTOR = "7c6a0ee22f66144ec8f65fde0fc2e019ad5eb91149a5b0fb611a7e3e68768a49"


def prepare(original, recipe, session, inventory, receipt_file):
    from empty_bootstrap import bind_native, checked
    from full_short_run import EIGHT_MS_RECIPE_SHA
    from leo.contracts.digests import canonical_digest

    checked(Path(__file__).with_name("eight_ms_held_fit.py"), SAVED_SELECTOR)
    if canonical_digest(recipe) != "sha256:"+EIGHT_MS_RECIPE_SHA:
        raise ValueError("Native history requires the original signed 20/8 ms recipe")
    bind_native(original, session, inventory, EIGHT_MS_RECIPE_SHA)
    from eight_ms_held_fit import select
    from preloaded_saved_worker import write

    packet, witness = select(original, recipe)
    detector = witness["detector_recipe_sha256"].removeprefix("sha256:")
    bind_native(packet, session, inventory, detector, expected=witness["native_sha256"])
    if witness["refinement_calls"] or "fixed_epoch_cfo_refinement" in witness["receiver_recipe"]:
        raise ValueError("Native history cannot purchase a subsequent CFO measurement")
    write(receipt_file, witness)
    return packet, witness["receiver_recipe"], detector, witness
