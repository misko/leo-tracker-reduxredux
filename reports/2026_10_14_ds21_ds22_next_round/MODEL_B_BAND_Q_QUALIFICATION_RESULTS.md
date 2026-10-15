# Actual shared/band q qualification preserves B's free group calibration

Both frozen case slices passed3474objectives/0fits: B0811992 in118.162s, B1151482 in123.522s, within declared180s completion/external195s TERM/200s KILL. No reference/original held/locked read. The [qualification protocol](MODEL_B_BAND_Q_QUALIFICATION_PROTOCOL.md) and [12-fit model protocol](MODEL_B_BAND_DETECTABILITY_PROTOCOL.md) remain unchanged. Component source`c83a19117`, actual qualifier`82cdc9d2c`; bulk `model-b-band-q-qualification-v1` under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/`.

All3sources/case are training-selected complete states: current full uniform winner plus original own-low/high winners. Every clock and absolute satellite timing term is retained; half functions rebase exactly into the original full B frame through the existing functional transport. Their own original25km disks are preserved. Both original receiver/band offsets remain FREE with original bounds/scales/precision, not frozen into an A shift. Underlying existing SmoothVisibilityModel/BandDetectabilityModel are used directly; PathModel is excluded.

The entire probe inventory was derived from source metadata and persisted before the first objective. Actual counts exactly match those inventories. All feasible physical/clock/freegroup/q coordinates were tested at deterministic nonzero q/contrast. No coordinate was blocked, so no active-face tangent fallback was needed. Stable source-cell steps range down to6.25e−7 in optimizer scales; no failed direction or threshold weakening occurred.

|Case|Complete source|Shared dimensions|Shared max scaled FD error|Band dimensions|Band max scaled FD error|
|---|---|---:|---:|---:|---:|
|B081|Full|136|.000027549|190|.000024147|
|B081|Low|136|.000083918|190|.000079185|
|B081|High|136|.000007142|190|.000008011|
|B115|Full|102|.000050773|139|.000050360|
|B115|Low|102|.000046014|139|.000047335|
|B115|High|102|.000075365|139|.000069712|

Every error is below the absolute3e−4 gate, without needing its relative2e−5 allowance. Zero-q and deterministic nonzero tied-band objective/NLL/physical/base/q-gradient/posterior nesting passed. Original full legacy GroupCalibrationObjective versus its unchanged legacy wrapper reproduces all physical/base-nuisance gradients. At nonzero q, direct group_design-transpose likelihood gradient plus unchanged group prior matches both free original group derivatives (maximum discrepancy2.41e−16). This rules out an accidental conversion of free offsets into fixed calibration.

At all6 source states, zero-q smooth versus hard conditional objective difference is exactly0, with zero horizon-transition pairs. Maximum physical gradient difference1.82e−13 and base nuisance difference5.55e−17. During later fitting, smooth visibility may enter its declared transition; no claim that hard/soft objectives remain identical there. Synthetic component tests additionally cover nonzero contrast at a smooth horizon.

Terminal SHA256: B081`eddd389a040f6a890f061357e1c529cc4228da6fd6f47120109fbec8c02cc37f`, B115`9996b7d534619b7bb44d3c7e0a5c04a0ebec26e5678827f42781357a70aac68c`. Both cases' preparations, terminals and source seals are mandatory inputs to a new frozen fit namespace. Five component tests and4qualifier tests passed with Ruff. This establishes numerical/source compatibility, not stationarity after adding q or localization improvement. The approved12full-view fits remain a separate experiment; source KKT cannot be copied to the expanded models.
