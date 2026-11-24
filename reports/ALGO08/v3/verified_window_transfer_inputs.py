"""Adapt the two signed partial-window detector ledgers without opening IQ."""

from pathlib import Path

from prefix_transfer_0419 import RADIOS, metadata, observation_id
from verified_window_transfer_0163 import parse


ATTESTED = Path("/tmp/leo-ds30-partial-window-attestation01")
ATTEST_PINS = {
    "DS30-0163": "f97a78dc990d406237a1c896c1c26d7ce04ce8162722a61b2d01c98ca8c5dd6e",
    "DS30-0419": "7c50973d2ccc1b16dd59c0019aafb90306b406a94f3f4144e306e339e71fb19c",
}
DETECTOR = "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"


def producer(path, ledger_pin, driver_pin, request, inventory, signed):
    from leo.contracts.digests import canonical_digest

    book = parse(path, ledger_pin)
    case = request["case"]
    expected = ATTEST_PINS[case]
    custody = parse(ATTESTED/case/"visits.json", expected)
    original = book["original"]
    scope = book["scope"]
    named, mixed = (book["detector"][part] for part in ("named", "mixed"))
    recipe = mixed["pre_selector_recipe"]
    prior = signed["visits"][0]["clock_anchor"]
    if (book["schema"] != "leo.research.attested-original-visit-detectors.v1" or book["case"] != case
            or book["driver_sha256"] != "sha256:"+driver_pin.removeprefix("sha256:")
            or book["original_waveform_bytes_read"] != 0 or not book["detector"]["named_archive_exact"]
            or original != dict(session_id=request["session"], inventory_sha256=request["inventory"],
                                raw_authority=request["raw_authority"], native_sha256="sha256:"+request["native_sha256"],
                                first_segment=inventory["segments"][0], first_member=signed["member"], clock_anchor=prior)
            or scope["attestation_sha256"] != "sha256:"+expected or scope["verified_file"] != custody["verified_file"]
            or scope["original_raw_reads"] != 0 or scope["original_recording_qualified"]
            or scope["complete_original_member_encoded_sha_verified"]
            or scope["complete_original_member_decoded_sha_verified"]
            or named["detector_sha256"] != DETECTOR or named["selector"] != "installed chronological continuation"
            or mixed["selector"] != "complete mixed chronological schedule, before held selector"
            or recipe["aperture_samples"] != [200_000, 80_000] or recipe["rule"] != ["full"]+["short_primary"]*7
            or canonical_digest(recipe) != mixed["pre_selector_recipe_sha256"]):
        raise ValueError("The sealed producer differs from original content, authority or measured receiver stage")
    length = len(custody["windows"])
    stop = custody["stop"]
    if (not 0 < length < signed["member"]["window_count"] or len(book["visits"]) != length
            or stop["sequence"] != length or stop["reason"] != "incomplete_decoded_visit"
            or stop["emitted_bytes"] != custody["trailing_decoded_bytes"] or not 0 <= stop["emitted_bytes"] < stop["expected_bytes"]
            or custody["original_backing_payload_reads"] != 0 or custody["original_issued"] != signed["member"]["window_count"]
            or custody["receiver_ids"] != list(RADIOS) or custody["normal_acquisition_contract"] is not False):
        raise ValueError("The detached evidence is not the maximum complete original prefix")
    visits, ordered = [], dict(installed=[], mixed=[])
    for source, measured in zip(custody["windows"], book["visits"], strict=True):
        target, acquire = source["target"], source["signed_row"]["acquisition"]
        visit = len(visits)
        expected_visit = signed["visits"][visit]
        if (source["sequence"] != visit or measured["visit_index"] != visit or source["receiver_ids"] != list(RADIOS)
                or measured["target"] != target or measured["acquisition"] != acquire
                or measured["iq_sha256"] != source["sha256"] or source["sha256"] != expected_visit["iq_sha256"]
                or measured["samples"]*8 != source["decoded_bytes"]
                or measured["target_id"] != source["signed_row"]["target_id"]
                or type(measured["admitted"]) is not bool):
            raise ValueError("Detector evidence does not reproduce the attested visit")
        visits.append(dict(sequence=visit, sample_start=measured["start_counter"], sample_end=measured["end_counter"],
                     iq_sha256=measured["iq_sha256"], clock=measured["delivery_clock"], admitted=measured["admitted"],
                     channel=target["channel"], actual_rf_hz=target["rf_center_hz"], edge=target["edge"]))
        expected_radios = list(RADIOS) if measured["admitted"] else []
        if [row["receiver_id"] for row in measured["lanes"]] != expected_radios:
            raise ValueError("Detector output dropped a native stereo lane or invented an excluded lane")
        for lane in measured["lanes"]:
            original_row, mixed_row = lane["named_20ms"], lane["mixed_20_8"]
            if (lane["observation_id"] != observation_id(request["session"], original_row)
                    or metadata(original_row) != lane["original_probe_metadata"] or metadata(mixed_row) != metadata(original_row)
                    or original_row["receiver_id"] != lane["receiver_id"] or original_row["visit_index"] != visit):
                raise ValueError("The original paired receiver lane lost its absolute observation identity")
            ordered["installed"].append(original_row)
            ordered["mixed"].append(mixed_row)
    if sum(row["decoded_bytes"] for row in custody["windows"]) != custody["verified_file"]["bytes"]:
        raise ValueError("The original emitted visits do not match the detached verified extent")
    return dict(visits=visits, native=ordered, binding=dict(
        source_sha256=book["driver_sha256"], ledger_sha256=ledger_pin, attest_sha256=scope["attestation_sha256"],
        named_detector_sha256=named["detector_sha256"], mixed_recipe=recipe, mixed_recipe_sha256=mixed["pre_selector_recipe_sha256"],
        prefix_bytes=custody["verified_file"]["bytes"], last_excluded_partial=stop, first_segment=original["first_segment"],
        actual_detector_timing=book["summed_callback_timing"], original_read_bytes=0))
