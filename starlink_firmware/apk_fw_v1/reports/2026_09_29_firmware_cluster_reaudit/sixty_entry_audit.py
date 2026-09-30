"""Discriminate the adjacent 60-entry configuration table from known T-code."""

import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from prefix_execution import CONTEXT, STOP, machine
from raw_audit import FIRMWARE, inspect_binary
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X30

BASE = Path(__file__).resolve().parent
SEED = "010010100010010010001000000000001000100000101000001010100010"


def transitions(bits):
    return int(np.count_nonzero(np.asarray(bits) != np.roll(bits, 1)))


def execute(binary, threshold, kind):
    uc = machine(binary)
    uc.mem_write(CONTEXT + 8, struct.pack("<I", kind))
    uc.mem_write(CONTEXT + 0xFC, struct.pack("<I", threshold))
    uc.mem_write(CONTEXT + 0x1C0, b"\xa5" * 240)
    uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
    uc.reg_write(UC_ARM64_REG_X30, STOP)
    uc.emu_start(0x6B6D0, STOP, count=2000)
    assert uc.reg_read(UC_ARM64_REG_PC) == STOP
    assert uc.reg_read(UC_ARM64_REG_X0) == 0
    observed = list(struct.unpack("<60I", uc.mem_read(CONTEXT + 0x1C0, 240)))
    expected = [0 if i < threshold else (6 if kind == 1 else 8) for i in range(60)]
    assert observed == expected
    return dict(threshold=threshold, kind=kind, table=observed)


def compare():
    seed = np.array(list(map(int, SEED)), dtype=np.uint8)
    words = np.array([1 ^ seed ^ np.roll(seed, -k) for k in range(60)])
    # All circular offsets, reversals and complements of threshold masks are
    # covered by all possible contiguous cyclic runs of ones, including constants.
    masks = np.unique(np.array([np.roll(np.arange(60) >= t, k)
                                for t in range(61) for k in range(60)]), axis=0)
    distances = np.count_nonzero(words[:, None, :] != masks[None, :, :], axis=2).min(axis=1)
    return dict(unique_masks=len(masks), seed=SEED,
                states=[dict(state=k, cyclic_transitions=transitions(w),
                             nearest_mask_hamming=int(distances[k]))
                        for k, w in enumerate(words)],
                exact_matching_states=np.flatnonzero(distances == 0).tolist())


def main():
    evidence = inspect_binary("catson-bin--phyfw", [
        ("sixty_entry_builder", 0x6B6D0, 0x6B738),
        ("transmit_builder_call", 0x64D08, 0x64D18)])
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    assert evidence["sha256"] == (
        "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326")
    cases = [execute(binary, threshold, kind) for threshold in (*range(61), 61, 0xFFFFFFFF)
             for kind in (0, 1, 2)]
    comparison = compare()
    result = dict(evidence=evidence, cases=cases, comparison=comparison,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Existing explicit T-code model, no new IQ or word search. "
                  "Excludes direct threshold-to-sign identity under rotation/reversal/"
                  "complement; does not exclude undocumented downstream encoding or "
                  "a shared hardware role. Constant-state match has no specificity.")
    (BASE / "local/sixty-entry-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    states = comparison["states"][1:]
    print("Executed cases", len(cases), "exact states", comparison["exact_matching_states"],
          "nonconstant minimum transitions", min(s["cyclic_transitions"] for s in states),
          "nonconstant minimum Hamming", min(s["nearest_mask_hamming"] for s in states))


if __name__ == "__main__":
    main()
