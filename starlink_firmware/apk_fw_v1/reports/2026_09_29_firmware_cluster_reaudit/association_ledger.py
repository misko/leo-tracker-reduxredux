"""Coordinate-level ledger; historical public evidence explicitly separated."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = Path(__file__).resolve().parent
REPORTS = (BASE.parents[3] / "reports")


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())


def main():
    region, region_source = read(
        REPORTS / "2026_09_28_sequence_semantics/local/revisit-regions/results.json")
    public, public_source = read(
        REPORTS / "2026_09_28_sequence_semantics/local/header_change_groups.json")
    pairs, pair_source = read(BASE / "local/pair-family.json")
    ledger = []
    for index, row in enumerate(region["results"]):
        ledger.append(dict(
            id=f"region-tree-{index:02}", scope="DS7/DS8/DS9 historical cached subset",
            kind="region phase-profile dendrogram and all pairwise associations",
            evidence=row, source=region_source,
            ranked_interpretations=["Shared waveform/state mixture or observation conditions",
                                    "Channel/beam state", "Satellite-linked state"],
            firmware_constraint="Packed GMH widths do not map to mean phase-profile axes. "
            "SATAddr existence supplies no NORAD or carrier-coordinate equivalence.",
            falsifier="Identity interpretation requires same-ID cross-session separation "
            "beyond different-ID matches after state/channel/rate controls.",
            test_status="Historical discovery/evaluation and frame-count controls retained; "
            "identity_resumption tests challenge identity specificity. No new blind scan."))
    for i, rule in enumerate(pairs["rules"]):
        evaluations = [dict(visit=v["visit"], frames=v["frames"],
                            agreement=v["agreement"][i], cyclic_mean=v["cyclic_mean"][i],
                            family_p=v["cyclic_max_family_p"][i]) for v in pairs["visits"]]
        ledger.append(dict(
            id=f"local-pair-{i + 1}", scope="DS10 three existing paired excerpts",
            kind="frozen two-coordinate sign parity", coordinates=rule["coordinates"],
            parity=rule["parity"], evidence=evaluations, source=pair_source,
            ranked_interpretations=["Visit-specific waveform/bias or selection fluctuation",
                                    "Coded redundancy with unknown mode/scrambling",
                                    "Fixed header copy/complement relation"],
            firmware_constraint="Actual LSB-first software writer constrains packed bytes, "
            "not post-FEC/scrambler/interleaver RF coordinate parity. Signaling mode emits "
            "an 8-bit prefix but gives no RF placement for these pairs.",
            falsifier="A fixed copy relation should transfer to held frames, receiver and "
            "revisits beyond bias-preserving cyclic controls.",
            test_status="All 21 frozen pair/visit tests recomputed; no family p below .05."))
    for kind, key in [("change-trace edge", "edges"), ("change-trace component", "components")]:
        for i, value in enumerate(public[key]):
            ledger.append(dict(
                id=f"historical-public-{key}-{i:03}", scope="Public full-band reference only",
                kind=kind, evidence=value, source=public_source,
                ranked_interpretations=["Known-state mixture or shared waveform",
                                        "Unknown encoded relation"],
                firmware_constraint="No demonstrated CGM/interleaver/carrier map. "
                "A connected change graph is not a software field or codeword boundary.",
                falsifier="A local interpretation needs the same observed coordinates and "
                "held-out transfer beyond known-state effects.",
                test_status="Historical receipt inventoried only; no new public-IQ analysis. "
                "Most reference coordinates lie outside recorded local edge bandwidth."))
    tiles, tile_source = read(BASE / "local/tile-receipt-audit.json")
    for row in tiles["adjacent_tiles"]:
        ledger.append(dict(
            id=f"adjacent-tile-{row['edge']}-{row['width']}", scope="DS7–DS9 selected 10 MS/s",
            kind="adjacent-region partitions", evidence=row, source=tile_source,
            ranked_interpretations=["Region-dependent waveform or noisy fitted alignment",
                                    "Shared encoded field", "Stable satellite signature"],
            firmware_constraint="Device-role settings and threshold masks do not establish "
            "translation or repeated-field equivalence between these regions.",
            falsifier="A stable repeated signature requires adjacent partition transfer.",
            test_status="Saved trees/ARI reproduced; ARI near zero; all Gram matrices PSD. "
            "Only two session/channel/rate/receiver-preserving permutations: abstain."))
    for visit in tiles["paired_tile_evidence"]["visits"]:
        for kind, key in [("paired receiver tile", "tiles"),
                          ("known-state regional comparison", "state_comparison")]:
            for i, row in enumerate(visit[key]):
                ledger.append(dict(
                    id=f"paired-{visit['name']}-{key}-{i}",
                    scope="DS7–DS9 historical paired subset",
                    kind=kind, evidence=row, source=tile_source,
                    ranked_interpretations=["Shared received waveform / known T-state",
                                            "Unmapped message structure"],
                    firmware_constraint="Neither role constants nor 20/60-entry threshold "
                    "tables map these correlations to message fields.",
                    falsifier="Message/identity interpretation requires residual transfer "
                    "beyond known-state and mismatched-receiver controls.",
                    test_status="Historical matched/shift controls preserved, not rerun. "
                    "Known-state equality is not satellite-identity equality."))
    metadata, metadata_source = read(BASE / "local/metadata-receipt-audit.json")
    for row in metadata["associations"]:
        ledger.append(dict(
            id=f"metadata-{row['feature']}", scope="DS7/DS8 historical word-family screen",
            kind="metadata distance association", evidence=row, source=metadata_source,
            ranked_interpretations=["Known waveform/state mixture and observation conditions",
                                    "Unverified metadata-linked message field"],
            firmware_constraint="Software fields, device roles and register masks do not "
            "supply a carrier mapping or SATAddr-to-NORAD equivalence.",
            falsifier="A field interpretation requires supported conditional transfer beyond "
            "known T-code and acquisition effects; absence of labels is not a negative test.",
            test_status=row["assessment"]))
    histograms, histogram_source = read(BASE / "local/phase-histogram-audit.json")
    for row in histograms["hierarchies"]:
        ledger.append(dict(
            id=row["name"], scope="DS7–DS9 phase-histogram hierarchy",
            kind="order-discarding regional phase distribution", evidence=row,
            source=histogram_source,
            ranked_interpretations=["Phase distribution and acquisition quality",
                                    "Known waveform mixture", "Unproven identity association"],
            firmware_constraint="Histogram features erase carrier and symbol order within "
            "regions; software field offsets cannot be read from their dendrogram branches.",
            falsifier="Direct field-position interpretation would require retaining order.",
            test_status="Actual-data reordering changes 99.97% of complex sample positions "
            "with exactly unchanged histogram. Cut compositions and quality association audited."))
    receiver, receiver_source = read(BASE / "local/receiver-family.json")
    for i, row in enumerate(receiver["rows"]):
        ledger.append(dict(
            id=f"receiver-family-{i}", scope="Three existing DS10 excerpts in one session",
            kind="frozen component/symbol cross-receiver correlation", evidence=row,
            source=receiver_source,
            ranked_interpretations=["Shared real received structure or common channel effects",
                                    "Unmapped modulation/message component"],
            firmware_constraint="Firmware role and mask fields do not map to these coordinates.",
            falsifier="Receiver-shared structure must exceed coordinate-preserving cyclic "
            "controls after correction; identity also requires cross-satellite specificity.",
            test_status="34 comparisons, exact joint cycles and coupled-session sensitivity. "
            "Positive I-symbol 3/4/6 results support structure, not decoded fields."))
    words, word_source = read(BASE / "local/word-scope-audit.json")
    for dataset, counts in words["qualified_track_counts"].items():
        ledger.append(dict(
            id=f"known-state-stability-{dataset}", scope=dataset,
            kind="within-frame T-state consistency versus between-frame change",
            evidence=counts, source=word_source,
            ranked_interpretations=["Known frame-dependent waveform state",
                                    "Unproven relationship to header state"],
            firmware_constraint="The 60-entry firmware threshold mask is not this T-code; "
            "no sequence-counter or SATAddr mapping is established.",
            falsifier="A constant raw identity interpretation requires stability across frames.",
            test_status="All 350 source receipts hash-verified and counts recomputed; "
            "qualified scope separated. State changes are not payload changes."))
    for category, counts in words["unmatched_windows_by_dataset_quality_and_distance"].items():
        ledger.append(dict(
            id=f"unmatched-words-{category}", scope=category,
            kind="accepted words outside known vocabulary", evidence=counts, source=word_source,
            ranked_interpretations=["Recovery error or distortion", "Unverified new structure"],
            firmware_constraint="No firmware field maps to these mismatching coordinates.",
            falsifier="New words need independent receiver/revisit reproduction beyond "
            "known-code recovery errors and qualification failures.",
            test_status="Nearest-code Hamming distances independently recomputed; "
            "all qualified unmatched words are distance 1 or 2. No new field claim."))
    identities, identity_source = read(BASE / "local/identity-scope-audit.json")
    for i, row in enumerate(identities["pair_experiments"]):
        ledger.append(dict(
            id=f"identity-pair-scope-{i}", scope="DS7–DS10 conditional candidate labels",
            kind="matched same/different-candidate correlation", evidence=row,
            source=identity_source,
            ranked_interpretations=["Session/trajectory and instrument effects",
                                    "Unverified satellite-linked field"],
            firmware_constraint="SATAddr has no verified NORAD or RF coordinate mapping.",
            falsifier="Identity needs matched cross-visit separation that survives "
            "session/trajectory controls and stronger label support.",
            test_status=row["assessment"]))
    for i, row in enumerate(identities["episode_experiments"]):
        ledger.append(dict(
            id=f"identity-episode-{i}", scope="DS7–DS10 conditional candidate labels",
            kind="episode-weighted retrieval", evidence=row, source=identity_source,
            ranked_interpretations=["Time/trajectory confounding", "Unproven identity retrieval"],
            firmware_constraint="Software identity-field existence does not validate labels.",
            falsifier="A useful identity feature should transfer beyond time-only baselines.",
            test_status="Episode weighting independently reproduced; same-session signs "
            "trail time baseline, cross-session samples sparse."))
    for i, row in enumerate(identities["stable_patterns"]):
        ledger.append(dict(
            id=f"stable-pattern-specificity-{i}", scope="DS10 donor and DS7–DS10 candidates",
            kind="discovery-frozen stable coordinates", evidence=row, source=identity_source,
            ranked_interpretations=["Common waveform/bias", "Unproven address field"],
            firmware_constraint="No demonstrated mapping from stable signs to SATAddr.",
            falsifier="Stable signs must separate other candidates, not merely agree across RX.",
            test_status="Historical frozen comparisons retained with exact coordinates; "
            "different candidates also match strongly and strict controls are sparse."))
    bandwidth, bandwidth_source = read(BASE / "local/bandwidth-receipt-audit.json")
    for i, row in enumerate(bandwidth["bandwidth"]["experiments"]):
        ledger.append(dict(
            id=f"wide-identity-{i}", scope="DS7–DS10 qualified 10 MS/s subset",
            kind="26-carrier versus four-carrier matched identity contrast", evidence=row,
            source=bandwidth_source,
            ranked_interpretations=["Narrow feature/session-specific association",
                                    "Unproven wide identity information"],
            firmware_constraint="No mapped identity field or carrier layout from firmware.",
            falsifier="A wider identity signature should improve held matched separation.",
            test_status="Only 14 within-session matched positives; wide effect weaker. "
            "Trajectory controls fail; other scopes abstain."))
    for row in bandwidth["reliability"]:
        ledger.append(dict(
            id=f"tail-carrier-reliability-{row['original']['edge']}",
            scope="DS7–DS10 selected known-state frames", kind="core versus extra carrier error",
            evidence=row, source=bandwidth_source,
            ranked_interpretations=["Comparable late known-waveform recovery"],
            firmware_constraint="Known T-code disagreement is not decoded message BER.",
            falsifier="A broad additional-carrier quality penalty would raise held errors.",
            test_status="506 held-frame error/count vectors independently aggregated; "
            "small core/extra differences, not evidence about early-header BER."))
    for i, row in enumerate(bandwidth["lower_profile_transfer"]["comparisons"]):
        ledger.append(dict(
            id=f"lower-profile-transfer-{i}", scope="DS9 and three DS10 lower-edge excerpts",
            kind="frozen cross-receiver/time profile transfer", evidence=row,
            source=bandwidth_source,
            ranked_interpretations=["Visit-specific average phase and estimation noise",
                                    "Unproven transferable field"],
            firmware_constraint="No interleaver/carrier map equates profiles with software fields.",
            falsifier="A transferable profile must survive matched cyclic/family controls.",
            test_status="32 saved comparisons and correction arithmetic audited; none passes."))
    counters, counter_source = read(BASE / "local/counter-ties.json")
    for row in counters["visits"]:
        ledger.append(dict(
            id=f"counter-ties-{row['visit']}", scope="DS10 three same-session excerpts",
            kind="frozen periodic-counter model ambiguity", evidence=row, source=counter_source,
            ranked_interpretations=["Selection fluctuation or unconstrained periodic fit",
                                    "Unproven encoded sequence field"],
            firmware_constraint="The audited TX sequence update is a bitmap OR, not an "
            "increment. Patent sequence fields do not map these RF coordinates to counters.",
            falsifier="Discovery-fitted periodic predictions must beat frozen constants and "
            "coordinate-maximum circular controls on later RX1 frames.",
            test_status="Original scores reproduced. Training-tie averaging remains negative; "
            "all six method/visit corrected ranks are 1. One old rank excluded a roundoff tie; "
            "new conservative ranks count numerical ties."))
    amplitudes, amplitude_source = read(BASE / "local/amplitude-audit.json")
    for family in ("models", "neighbors", "raw_axis_rows"):
        for i, row in enumerate(amplitudes[family]):
            public_only = row.get("source") == "public_soft_reference"
            ledger.append(dict(
                id=f"amplitude-{family}-{i}",
                scope="Historical public reference only" if public_only else "DS10 paired excerpts",
                kind=f"Amplitude/neighbor interpretation: {family}", evidence=row,
                source=amplitude_source,
                ranked_interpretations=["Shared received variation with unresolved distribution",
                                        "Discrete modulation distorted by channel/noise",
                                        "Unproven mapped header data"],
                firmware_constraint="MCS tables and patent modulation options do not assign "
                "an alphabet to physical symbols 4/6; no verified interleaver or RF bit map.",
                falsifier="A specified level or leakage model must improve frozen held "
                "prediction beyond its continuous/constant baseline.",
                test_status="12 local paired likelihoods recomputed from hash-verified NPZ. "
                "36 neighbor tests all lose to constants. Raw-axis receipt arithmetic audited; "
                "public rows retained only as historical provenance. No new independent p-value."))
    state_scope, state_source = read(BASE / "local/state-scope.json")
    for visit in state_scope["visits"]:
        for i, assay in enumerate(visit.get("assays", [None])):
            ledger.append(dict(
                id=f"state-scope-{visit['visit']}-{i}", scope="Six existing DS10 paired excerpts",
                kind="known-state residual prediction" if assay else "state-support abstention",
                evidence=dict(visit=visit["visit"], assay=assay,
                              train_frames=visit["train_frames"], test_frames=visit["test_frames"],
                              eligible_states=visit["eligible_states"],
                              training_state_counts=visit["training_state_counts"]),
                source=state_source,
                ranked_interpretations=["Known waveform and limited repeated-state support",
                                        "Unproven additional state-linked information"],
                firmware_constraint="No verified mapping between T-state and a GMH/SATAddr "
                "field; accounting units and conditional prefix forms do not provide one.",
                falsifier="T-state must improve held residual prediction beyond a "
                "state-independent mean, not just shuffled-label templates.",
                test_status="One supported excerpt, five abstentions. All ten residual tests "
                "lose to the global mean; raw assays duplicate across gain models. Eligibility "
                "and score identities audited; historical fits not blindly repeated."))
    combining, combining_source = read(BASE / "local/combining-scope.json")
    for kind in ("parity", "combining"):
        for i, row in enumerate(combining[kind]):
            ledger.append(dict(
                id=f"receiver-combination-{kind}-{i}", scope="Three DS10 paired excerpts",
                kind=f"Receiver combination {kind}", evidence=row, source=combining_source,
                ranked_interpretations=["Improved recovery of known waveform",
                                        "Unproven early redundancy or message information"],
                firmware_constraint="No mapped FEC parity or header-bit reliability model; "
                "resource accounting and prefix widths do not define the frozen RF parity.",
                falsifier="Early parity should survive frozen transfer and bias-preserving "
                "controls, with enough retained frames; tail recovery alone is insufficient.",
                test_status="Ungated parity recomputed from saved signs; six-test minimum "
                "corrected rank 2/3. Median amplitude gates retain only 0–2 frames. "
                "Known-tail error/count arithmetic audited; not message BER."))
    ds9_axes, ds9_source = read(BASE / "local/ds9-axis-audit.json")
    for visit in ds9_axes["visits"]:
        for i, row in enumerate(visit["assays"]):
            ledger.append(dict(
                id=f"ds9-axis-{visit['visit']}-{i}", scope="Two existing DS9 excerpts",
                kind="centered cross-receiver axis correlation", evidence=row, source=ds9_source,
                ranked_interpretations=["Shared waveform/channel/calibration structure",
                                        "Unproven additional quadrature modulation"],
                firmware_constraint="No PHY-to-GMH mapping assigns axis covariance to bits. "
                "Header budgets or device roles do not determine modulation here.",
                falsifier="Extra quadrature interpretation needs transfer after shared-gain "
                "removal and correction over tested regions/axes.",
                test_status="Saved correlations and cyclic extrema reproduced. Middle header "
                "Q=.220, last Q=.017. Two-excerpt correction has minimum possible rank 2/23; "
                "no .05 rejection possible. Preprocessing differs from DS10 residual assay."))
    ds9_leakage, ds9_leakage_source = read(BASE / "local/ds9-leakage-transfer.json")
    for visit in ds9_leakage["visits"]:
        for i, row in enumerate(visit["rows"]):
            ledger.append(dict(
                id=f"ds9-leakage-transfer-{visit['visit']}-{i}", scope="Two existing DS9 excerpts",
                kind="Frozen DS10 preprocessing transferred to DS9", evidence=row,
                source=ds9_leakage_source,
                ranked_interpretations=["Shared waveform or residual channel structure",
                                        "Unproven additional modulation"],
                firmware_constraint="No mapped PHY axis or decoded GMH field. Software "
                "bit order and resource budgets cannot assign these correlations to bits.",
                falsifier="If fitted linear I leakage explains Q, independent reserved-frame "
                "Q should collapse after the frozen correction.",
                test_status="Middle Q survives (.220 to .211), last Q .017 to .003. "
                "Twenty-one-test max control per excerpt, Bonferroni across excerpts; "
                "minimum attainable corrected rank 2/23. No semantic or significance claim."))
    ds9_t, ds9_t_source = read(BASE / "local/ds9-t-quadrature.json")
    for visit in ds9_t["visits"]:
        for i, row in enumerate(visit["rows"]):
            ledger.append(dict(
                id=f"ds9-t-quadrature-{visit['visit']}-{i}", scope="Two existing DS9 excerpts",
                kind="Known T-code coupling to early quadrature", evidence=row, source=ds9_t_source,
                ranked_interpretations=["Simple linear T-sign coupling unsupported",
                                        "Other shared waveform or channel variation unresolved"],
                firmware_constraint="Known T generator is a waveform constraint, not an "
                "established GMH field or satellite address. No nonlinear state mapping proved.",
                falsifier="A discovery-fitted coordinate slope from fixed T signs should "
                "predict reserved-frame Q better than the discovery-mean baseline.",
                test_status="Aggregate Q errors increase 4–7%; no support for this mapping. "
                "Known late real-axis controls improve 37–47%. Categorical state lookup "
                "has insufficient recurring-state support. Frozen 28-test cyclic family "
                "per excerpt with two-excerpt correction; no new state or lag search."))
    phase_scope, phase_source = read(BASE / "local/ds9-phase-scope.json")
    for visit in phase_scope["visits"]:
        for i, row in enumerate(visit["rows"]):
            ledger.append(dict(
                id=f"ds9-phase-scope-{visit['visit']}-{i}", scope="Two existing DS9 excerpts",
                kind="Frozen tail-phase correction transferred to early quadrature",
                evidence=row, source=phase_source,
                ranked_interpretations=["Shared variation survives this phase estimator",
                                        "Fast phase error or modulation remains unresolved"],
                firmware_constraint="No verified symbol-phase control or RF bit mapping; "
                "surviving receiver covariance is not a software field.",
                falsifier="A valid constant per-frame/carrier rotation estimate should "
                "remove early Q if that rotation explains it, and improve known-tail recovery.",
                test_status="Middle Q .220 to .212; last .017 to .019. Historical known-tail "
                "errors reproduced and slightly worsen after correction, limiting exclusion. "
                "Fourteen-assay joint cyclic control per excerpt, Bonferroni over two. "
                "Separate pilot probe is last-excerpt pilot coherence only, not early Q."))
    carrier_scope, carrier_source = read(BASE / "local/ds9-carrier-scope.json")
    for visit in carrier_scope["visits"]:
        for i, row in enumerate(visit["rows"]):
            ledger.append(dict(
                id=f"ds9-carrier-scope-{visit['visit']}-{i}", scope="Two existing DS9 excerpts",
                kind="Early Q covariance attribution to fixed carrier groups", evidence=row,
                source=carrier_source,
                ranked_interpretations=["Middle shared Q spans both recorded carrier groups",
                                        "Modulation versus shared channel error unresolved"],
                firmware_constraint="Carrier groups bracket known lower pilots; no mapping "
                "to separate software fields, devices, or satellite identities established.",
                falsifier="An effect limited to one group or one frame should disappear in "
                "the other fixed group or after removing the responsible frame.",
                test_status="Middle corrected Q .198/.222 across groups, remains positive "
                "under every single-frame omission. Last groups weak and opposite-signed. "
                "Four-assay cyclic maximum per excerpt, two-excerpt correction; minimum "
                "attainable rank 2/23. Influence ranges are not confidence intervals."))
    initialization, initialization_source = read(BASE / "local/initialization-execution.json")
    _, parser_source = read(BASE / "local/parser-gate.json")
    _, budget_source = read(BASE / "local/format-budget.json")
    _, entry_source = read(BASE / "local/entry-caller.json")
    _, sysinfo_source = read(BASE / "local/sysinfo-format.json")
    _, downlink_source = read(BASE / "local/downlink-accounting.json")
    _, address_source = read(BASE / "local/sysinfo-address-decode.json")
    _, dispatch_source = read(BASE / "local/sysinfo-dispatch-decode.json")
    _, timing_source = read(BASE / "local/sysinfo-timing-layout.json")
    _, ephemeris_source = read(BASE / "local/sysinfo-ephemeris-layout.json")
    _, consumer_source = read(BASE / "local/sysinfo-consumer.json")
    _, variance_source = read(BASE / "local/pnt-variance-format.json")
    _, pnt_context_source = read(BASE / "local/pnt-context-identity.json")
    _, utgw_source = read(BASE / "local/utgw-identity-gate.json")
    _, utgw_mode_source = read(BASE / "local/utgw-mode-route.json")
    _, integrity_source = read(BASE / "local/descriptor-integrity.json")
    _, meh_source = read(BASE / "local/meh-length-crc.json")
    _, meh_tx_source = read(BASE / "local/meh-transmit-trailer.json")
    _, descriptor_lengths_source = read(BASE / "local/transmit-descriptor-lengths.json")
    _, descriptor_config_source = read(BASE / "local/transmit-configuration-descriptor.json")
    _, grant_origin_source = read(BASE / "local/grant-configuration-origin.json")
    _, grant_timing_source = read(BASE / "local/grant-timing-gate.json")
    _, grant_queue_source = read(BASE / "local/grant-queue-origin.json")
    _, ulmap_fields_source = read(BASE / "local/ulmap-grant-fields.json")
    _, grant_identity_source = read(BASE / "local/grant-identity-context.json")
    result = dict(associations=ledger,
                  shared_grant_identity_constraint=dict(source=grant_identity_source,
                      consequence="288 full-validator executions with other gates permissive. "
                      "Satellite mismatch compares stored context+0x41538 to expected+0x4164c; "
                      "either zero bypasses comparison. Grant fill and context-valid byte "
                      "do not alter this gate. Diagnostic IDs are context, not proof of an "
                      "address repeated in every RF grant or a NORAD mapping."),
                  shared_ulmap_fields_constraint=dict(source=ulmap_fields_source,
                      consequence="174 actual ULMAP diagnostic cases name seven-byte grant: "
                      "SID16,index5,symbolOffset8,symbolCount8,rbOffset5,rbCount5,unreported1,"
                      "MCS8. Refines two NumOfdm values to count/offset; descriptor omits MCS "
                      "from that packed word. No recovered RF field or satellite ID follows."),
                  shared_grant_queue_constraint=dict(source=grant_queue_source,
                      consequence="Internal callback type4 populates queued session, RF "
                      "number and7-byte grant;366 composed RX-sender/TX-consumer cases "
                      "across3 entry indices preserve the actual generated packet fields. "
                      "Handler consumes queued grant at+0x20, then stores its5-byte suffix "
                      "as descriptor configuration. Internal type4 is not an RF type ID. "
                      "RX header/entry packing verified; transport and upstream decoded-grant "
                      "storage remain unexecuted."),
                  shared_grant_timing_constraint=dict(source=grant_timing_source,
                      consequence="6000 actual queued-grant gate cases: session mismatch "
                      "rejects; matching session signed32 difference normalized modulo750 "
                      "handles residue0, defers1..63, rejects64..749. Tested uint32 wrap. "
                      "No proven equivalence to SYSINFO RFNum, seconds or RF sign period."),
                  shared_grant_origin_constraint=dict(source=grant_origin_source,
                      consequence="Configuration word traces to five bytes of grant record. "
                      "Executed diagnostic maps source bits5..12 and13..20 to two NumOfdmSymb "
                      "values,26..30 to NumRb; NumDataSymb=(63*NumRb-16)*(firstOfdm-1). "
                      "Allocation interpretation strengthened; RF direction/placement and "
                      "two OFDM meanings not established. No satellite identity inference."),
                  shared_transmit_configuration_constraint=dict(source=descriptor_config_source,
                      consequence="942 actual composed metadata/descriptor packing cases. "
                      "Five config fields of5/8/8/5/5 bits transfer; second uses zero-absent "
                      "or presence plus value-minus-one representation. Grant-origin audit "
                      "names three fields; remaining semantics require separate evidence. "
                      "This is a configuration source, not evidence for a satellite address, "
                      "message field or directly transmitted RF word."),
                  shared_transmit_descriptor_constraint=dict(source=descriptor_lengths_source,
                      consequence="72 executed length-write cases. Ordinary first buffer "
                      "excludes1 byte; second excludes2/3 by form, matching reserved trailers. "
                      "Mode1 separately excludes0/1. Supports later insertion hypothesis, "
                      "but hardware CRC generation and RF mapping remain unverified."),
                  shared_meh_transmit_constraint=dict(source=meh_tx_source,
                      consequence="576 actual transmit-helper cases append alignment ones "
                      "then16/24 zero trailer bits from verified form table. No data-dependent "
                      "checksum is computed here or by tested flush/join helpers, which "
                      "preserve the trailer. Later insertion unverified; zeros "
                      "cannot be imposed as RF constraints."),
                  shared_meh_framing_constraint=dict(source=meh_source,
                      consequence="Executed MEH helper accounts2 checksum bytes normally, "
                      "3 with extended flag. Both read16-bit length; normal rejects >255. "
                      "Requires length>=2+CRCbytes and <=buffer bytes; special bit1 path "
                      "uses fixed7 bytes instead. Checksum polynomial and RF mapping unknown."),
                  shared_integrity_constraint=dict(source=integrity_source,
                      consequence="Executed descriptor handling confirms CRC-failure metadata, "
                      "gated by descriptor byte5 bit1. MEH failure is recorded but its error "
                      "bit is suppressed for local state2. No checksum polynomial, covered "
                      "bytes, or RF checksum extraction established."),
                  shared_utgw_mode_constraint=dict(source=utgw_mode_source,
                      consequence="Composed post-decode routing reaches type15 context-ID "
                      "assignment with configuration enum4 and two clear context flags; "
                      "enum1 invalidates and other tested enums route elsewhere. This enum "
                      "has no verified equivalence to PHY roles or DS7–DS10 operating modes."),
                  shared_utgw_identity_constraint=dict(source=utgw_source,
                      consequence="Type15 UTGW SYSINFO, distinct from type0 SYSINFO, has a "
                      "verified context-ID assignment gate: equal IDs or either zero accepted; "
                      "unequal nonzero IDs invalidate context. Received zero is stored as "
                      "valid. Feature-mode reachability and NORAD relationship unverified."),
                  shared_pnt_identity_constraint=dict(source=pnt_context_source,
                      consequence="272 executed construction cases show PNT telemetry "
                      "satellite_id comes from device context, not the decoded PNT body. "
                      "Flags and variance come from message storage; context validity gates "
                      "assembly. PNT telemetry schema does not justify an RF identity-bit scan."),
                  shared_pnt_variance_constraint=dict(source=variance_source,
                      consequence="Exhaustive actual converter execution establishes unsigned "
                      "6-bit exponent/10-bit fraction, bias25; zero and FFFF special zero/NaN. "
                      "Not IEEE binary16. Physical units and RF positions unverified; no "
                      "identity or phase-cluster interpretation follows from numeric format."),
                  shared_sysinfo_consumer_constraint=dict(source=consumer_source,
                      consequence="Executed consumer adapter preserves position, widens "
                      "velocity precision and zero-extends first timestamp word without "
                      "unit scaling. Initial change gate reacts to version, address or "
                      "channels; it is not a satellite-change-only indicator. No RF mapping."),
                  shared_sysinfo_ephemeris_constraint=dict(source=ephemeris_source,
                      consequence="708 actual codec round trips verify a 352-bit ephemeris "
                      "block: position3x64, velocity3x32, timestamp2x32. Presence shifts "
                      "timing offsets by352 and yields52/62-byte messages under tested "
                      "optional choices. Codec accepts nonphysical bit patterns; parsing "
                      "does not validate orbit, epoch, identity, or RF coordinate mapping."),
                  shared_sysinfo_timing_constraint=dict(source=timing_source,
                      consequence="Actual writer/body-reader round trips establish conditional "
                      "SYSINFO group fields 4+4 bits, RFNum32 and ULTxTimeOffset32. With "
                      "ephemeris absent and later optionals empty the message is 18 bytes. "
                      "Cadence, units and RF-coded positions remain unknown; no cluster "
                      "cardinality or observed sign period can yet be assigned to these fields."),
                  shared_control_dispatch_constraint=dict(source=dispatch_source,
                      consequence="Executed outer decoder accepts minimal SYSINFO at four "
                      "byte alignments, rejects seven-byte truncation, and accepts zero or "
                      "nonzero trailing padding values. Caller statically gates success on "
                      "status zero. Format acceptance is not a checksum or RF identity proof."),
                  shared_sysinfo_address_constraint=dict(source=address_source,
                      consequence="Executed minimal SYSINFO body decoder preserves all 32 "
                      "SATAddr bits in 52 synthetic cases. It can write the address before "
                      "returning error 27 on insufficient remaining bit count. Output memory "
                      "alone is not a valid decode; no RF position or NORAD mapping proved."),
                  sources=[region_source, public_source, pair_source, tile_source,
                           metadata_source, histogram_source],
                  receiver_family_source=receiver_source,
                  word_scope_source=word_source,
                  identity_scope_source=identity_source,
                  bandwidth_source=bandwidth_source,
                  counter_source=counter_source,
                  amplitude_source=amplitude_source,
                  shared_transmit_constraint=dict(source=entry_source,
                      consequence="Selected parent wrapper and pointer paths connect prefix "
                      "form and entry width to common storage at object+0x70c1. Initialization "
                      "and intervening changes remain unverified; no RF coordinate map."),
                  shared_sysinfo_constraint=dict(source=sysinfo_source,
                      consequence="Executed conditional LONG/SHORT diagnostic decision; "
                      "compared-byte meaning and connection to +0x70c1 remain unknown."),
                  shared_downlink_accounting_constraint=dict(source=downlink_source,
                      consequence="RX-LMAC accounts complete 32-bit units as 114 symbols. "
                      "Audited caller replenishes unused GMH resources and has a saturating "
                      "bookkeeping counter. Not a transmitted sequence field or header boundary."),
                  shared_parser_constraint=dict(source=parser_source,
                      consequence="72 actual RX prefix branch cases verify feature value exactly "
                      "1 plus nonzero two-bit state enables table parsing with positive count. "
                      "Short accounting uses 16 bits, table reader requests 20; runtime-valid "
                      "short/table combinations unproven. No four-cluster/field equivalence."),
                  shared_format_budget_constraint=dict(source=budget_source,
                      consequence="Uplink-associated SYSINFO format byte selects budget tables "
                      "114/228 before codeword conversion and 16/24 afterward. These are "
                      "distinct from entry width 16/20 and prefix width 8/16. No RF placement "
                      "or evidence of 114/228 switching in our Ku downlink captures."),
                  shared_firmware_constraint=dict(
                      source=initialization_source,
                      role_labels=[dict(value=c["mode"], label=c["role_label"])
                                   for c in initialization["cases"]],
                      consequence="Canonical object+0x10 controls device roles, not an "
                      "established per-frame field. Mode 3 is SAT-RX; do not map cluster "
                      "counts to its CGM table split. Applies to all associations above."),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Expanded coordinate/group ledger, not yet the complete "
                  "195-artifact semantic inventory. Historical tests not new confirmation. "
                  "Rankings are evidential judgments, not posterior probabilities.")
    (BASE / "local/association-ledger.json").write_text(json.dumps(result, indent=2) + "\n")
    excess = np.array([np.array(v["agreement"]) - v["cyclic_mean"] for v in pairs["visits"]])
    fig, ax = plt.subplots(figsize=(10, 3.8), layout="constrained")
    im = ax.imshow(excess, vmin=-.35, vmax=.35, cmap="RdBu_r", aspect="auto")
    ax.set_xticks(range(len(pairs["rules"])), [f"P{i + 1}" for i in range(len(pairs["rules"]))])
    ax.set_yticks(range(len(pairs["visits"])), [v["visit"] for v in pairs["visits"]])
    for y, v in enumerate(pairs["visits"]):
        for x, p in enumerate(v["cyclic_max_family_p"]):
            ax.text(x, y, f"{excess[y, x]:+.2f}\np={p:.2f}", ha="center", va="center", fontsize=9)
    ax.set_title("Frozen pair transfer: RX1 held frames\n"
                 "Excess agreement over cyclic mean; family-controlled p")
    fig.colorbar(im, ax=ax, label="Agreement excess")
    fig.savefig(BASE / "local/pair-transfer.png", dpi=160)
    plt.close(fig)
    print("Ledger entries", len(ledger), "region pairs",
          sum(len(r["pairs"]) for r in region["results"]))


if __name__ == "__main__":
    main()
