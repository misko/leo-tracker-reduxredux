# Wave 6 merged input integrity

The merged contract has all 88 distinct plan sessions in plan order, with 48 ready and 40 unavailable. Its 144 ready artifacts match their frozen SHA-256 digests. The original 32 ready rows exactly match the Wave 5 final contract.

The Group 04 and Group 05 additions are disjoint and preserve exporter eligibility. For each new bank, the eligible track set exactly equals its manifest and bank track set, and the timing grid contains 41 points. Capture 038 has 57 observation tracks but 56 eligible/banked tracks; its one excluded observation track fails the frozen held-out eligibility rule, so this is expected rather than a binding loss.

All 259 Wave 5 closeout bindings match at their recorded roots. The merged index and frozen digest are recorded in `INPUT-INTEGRITY.json`.
