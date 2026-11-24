"""Bind the checked live 20/8 ms receiver to the frozen saved history recipe."""

from pathlib import Path


SAVED_SELECTOR = "7c6a0ee22f66144ec8f65fde0fc2e019ad5eb91149a5b0fb611a7e3e68768a49"


def prepare(original, recipe, session, inventory, receipt_file):
    from empty_bootstrap import bind_native, checked
    from full_short_run import EIGHT_MS_RECIPES, SPARSE_EIGHT_MS_SHA
    from leo.contracts.digests import canonical_digest
    from primary_anchor_8ms import RECIPE_FIELD, anchor_witness, single_anchor_options

    checked(Path(__file__).with_name("eight_ms_held_fit.py"), SAVED_SELECTOR)
    guarded = "guarded_full_anchor" in recipe
    base = single_anchor_options(recipe)
    if guarded:
        from guarded_full_anchor import unguarded

        base = unguarded(base)
    short_pin = base.get("shortened_sha256")
    if short_pin not in EIGHT_MS_RECIPES or canonical_digest(base) != "sha256:"+EIGHT_MS_RECIPES[short_pin]:
        raise ValueError("Native history requires the original signed 20/8 ms recipe")
    if short_pin == SPARSE_EIGHT_MS_SHA and RECIPE_FIELD in recipe:
        raise ValueError("Sparse native 8 ms uses the original two-scan full anchors")
    if guarded and short_pin != SPARSE_EIGHT_MS_SHA:
        raise ValueError("Guarded full anchors keep the registered sparse 8 ms primary")
    bind_native(original, session, inventory, canonical_digest(recipe)[7:])
    from eight_ms_held_fit import select
    from preloaded_saved_worker import write

    packet, witness = select(original, recipe)
    detector = witness["detector_recipe_sha256"].removeprefix("sha256:")
    if short_pin == SPARSE_EIGHT_MS_SHA and not guarded and detector != "ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a":
        raise ValueError("The sparse 8 ms held selector changed")
    bind_native(packet, session, inventory, detector, expected=witness["native_sha256"])
    if witness["refinement_calls"] or "fixed_epoch_cfo_refinement" in witness["receiver_recipe"]:
        raise ValueError("Native history cannot purchase a subsequent CFO measurement")
    if RECIPE_FIELD in recipe:
        witness["full_anchor_measurements"] = anchor_witness(original)
    write(receipt_file, witness)
    return packet, witness["receiver_recipe"], detector, witness
