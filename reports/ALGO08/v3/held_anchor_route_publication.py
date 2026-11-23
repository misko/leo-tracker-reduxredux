"""Bind the held-anchor route to one authentic mixed-aperture receiver packet."""

from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
SELECTOR_SOURCES = {
    "anchor_cycle_route.py": "fd6cd122b01fd6865cde965c6f6f8d72d97bb804642e835398de168ce333ab13",
    "anchor_holds.py": "b0607a337c832b8a766b8e07e1f23417456e4046491a5acd26c8f7930cfbb7f5",
    "anchor_exposure.py": "aec435ae4bcd86892566bfa6a21ec5fedb3c3b6174fe4f9b4640c986bd6cf8cd",
}
HISTORY_SOURCES = {
    "north_factor_swap.py": "2e974f0869f6edee312cd415fd61c16ee0a0caea2f9363f56ad43a84b8a65978",
    "causal_short_receiver.py": "61520e72ed4d1937319ae21f57e4e3f4bb566d14862a08a81f215dbfe0a5e0fe",
}
SETTINGS = dict(period_admitted_visits=8, nonanchor_donors=7, prior_positive=0.5, prior_negative=0.5,
                eager_mask_of_all_original_anchors=True, incomplete_cycles="skip", radios=[0, 1],
                history_gate="strictly greater sum of held log scores on both radios",
                sparse_fallback="unfiltered", tie_fallback="unfiltered", disagreement_fallback="unfiltered")


def prepare(original, recipe, session, inventory, receipt_file):
    """Select from an already verified 20/12 ms acquisition and seal before solving."""
    import empty_bootstrap as staged
    from leo.contracts.digests import canonical_digest

    began = process_time(), perf_counter()
    for name, digest in SELECTOR_SOURCES.items():
        staged.checked(HERE / name, digest)
    from anchor_cycle_route import select_route

    original_pin = canonical_digest(recipe)
    from full_short_run import RECIPE_SHA

    if original_pin != "sha256:"+RECIPE_SHA:
        raise ValueError("The held-anchor rule requires the authenticated unfiltered 20/12 ms receiver")
    staged.bind_native(original, session, inventory, RECIPE_SHA)
    original_digest = canonical_digest(original)
    before = process_time(), perf_counter()
    assessment = select_route(original)
    selector = dict(cpu_s=process_time()-before[0], elapsed_s=perf_counter()-before[1])
    choice = assessment["route"]
    now = process_time(), perf_counter()
    if choice == "history":
        for name, digest in HISTORY_SOURCES.items():
            staged.checked(HERE / name, digest)
        from causal_short_receiver import identity
        from north_factor_swap import continued

        packet = continued(original)
        selected_recipe, detector = identity(RECIPE_SHA)
    elif choice == "unfiltered":
        packet, selected_recipe, detector = original, recipe, RECIPE_SHA
    else:
        raise ValueError("The frozen route returned an unsupported selection")
    replay = dict(cpu_s=process_time()-now[0], elapsed_s=perf_counter()-now[1]) if choice == "history" else None
    selected_digest = original_digest
    if choice == "history":
        from anchor_exposure import bind

        bind(original, packet)
        if any(after["candidates"] and after["candidates"] != before["candidates"]
               for before, after in zip(original["source"]["probes"], packet["source"]["probes"], strict=True)):
            raise ValueError("History selection must retain original factors exactly")
        staged.bind_native(packet, session, inventory, detector)
        if canonical_digest(selected_recipe) != "sha256:"+detector:
            raise ValueError("The selected packet needs the original receiver history recipe")
        selected_digest = canonical_digest(packet)
    before_seal = process_time(), perf_counter()
    result = dict(schema_version=1, choice=assessment, settings=SETTINGS, selector_sources=SELECTOR_SOURCES,
                  history_sources=HISTORY_SOURCES if choice == "history" else None,
                  adapter_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  raw_recording_authority=original["source"]["raw_recording_authority_digest"],
                  input_inventory=inventory, session=session, original_native_sha256=original_digest,
                  original_recipe_sha256=original_pin, original_recipe=recipe,
                  selected_native_sha256=selected_digest, selected_recipe_sha256="sha256:"+detector,
                  selected_recipe=selected_recipe, selector=selector, original_history_replay=replay,
                  before_seal=dict(cpu_s=before_seal[0]-began[0], elapsed_s=before_seal[1]-began[1]))
    with Path(receipt_file).open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return packet, selected_recipe, detector, result
