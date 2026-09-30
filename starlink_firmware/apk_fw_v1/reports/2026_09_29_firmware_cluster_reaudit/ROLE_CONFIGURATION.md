# Reciprocal transmit/receive configuration

Following the newly identified device roles finds a concrete configuration
setter and two callers. Bounded execution confirms that `SAT-TX` and the receive
branch of `UT-TRX` share several parameter values. Conversely, the transmit
branch of `UT-TRX` matches `SAT-RX`. This narrows which firmware branches are
plausibly relevant to our satellite-downlink recordings, without assigning
undocumented parameter names or RF positions.

## Direct code evidence

The canonical PHY binary is the same SHA256-verified input used in
[the initialization audit](INITIALIZATION_ROLES.md). The function at **0x6b440**
writes argument `w1` into `object+0x10` and returns zero. It does not validate the
role or itself access hardware. Two direct calls found in the executable text
are **0x52f4c** and **0x64be0**. This direct-call search is navigation evidence,
not proof that indirect calls or other writes are absent.

The first function starts at **0x52f30** and selects branches for role values
1 (`SAG-RX`), 3 (`SAT-RX`) and 4 (`UT-TRX`). The second starts at **0x64bc0** and
selects 0 (`SAG-TX`), 2 (`SAT-TX`) and 4 (`UT-TRX`). Those role sets support the
receive/transmit interpretation independently of a name guessed from an address.

`role_configuration.py` executes the actual setter call and the following
configuration branches, stopping at **0x52fc4** or **0x64c38**, before subsequent
helpers or virtual calls. Forty-eight cases cover all six accepted role/direction
combinations, two secondary-mode values, two low-word adjustments and two
high-word flags. Object and stack are synthetic RAM; no hardware is touched.

## Observed parameter correspondence

These are **object offsets and unsigned stored values**, not decoded header
fields. The table uses zero adjustment and zero flag.

| Branch | +0xf0 | +0xf4 | +0xfc | +0x100 | +0x104 | +0x48 |
|---|---:|---:|---:|---:|---:|---:|
| SAT-TX | 3 | 4 | 20 | 0 | 51 | 18 |
| UT-TRX receive | 3 | 4 | 20 | 0 | 51 | 16 |
| UT-TRX transmit | 3 | 16 | 16 | 0 | 63 | 27 |
| SAT-RX | 3 | 16 | 16 | 0 | 63 | 24 |

The paired roles agree at five offsets but **do not agree at +0x48**. The packed
caller argument's low 32 bits are subtracted from the +0xfc value; bits 32–39
are stored as a byte at +0x100. This is software argument packing, not evidence
of transmitted byte order. The regression test changes both parts and checks
the distinct stored effects.

The differences 18−16=2 and 27−24=3 are real numerical observations. They are
not sufficient to name synchronization symbols, pilot counts, interleaver depths
or message lengths. Likewise, values 4 and 16 do not establish QPSK/16-QAM:
we have not traced those fields to a mapper or RF coordinate definition.

## What this changes for the recordings

The ordinary CGM table and the SAT-TX/UT-receive configuration are the better
supported firmware starting points for the recorded downlink. The SAT-RX/UT-TX
branch appears directionally different. This strengthens the exclusion against
interpreting the SAT-RX-only CGM alternative as a changing downlink header type.

The setter shows that role is mutable through software configuration; it does
**not** show whether such changes occur during active reception, at startup,
or on reconfiguration. That timing remains unresolved. There is no observed
path here from received message bytes to this setter.

Accordingly, none of the hierarchy's 2/4/8-way partitions, the seven frozen
symbol-pair relations, or repeated T states acquires a semantic label from
these constants. Matching a cluster count to 4, 16 or 20 would be another
unconstrained numerical coincidence. No new RF search was run on that basis.

The next connected helper at **0x6b590** reads +0xfc and +0x100 and builds a
small vectorized configuration table. Its operations are a specific next
code-tracing target; its meaning and consumers have not yet been established.

## Reproduction

```sh
uv run --no-project --with capstone --with pyelftools --with unicorn python reports/2026_09_29_firmware_cluster_reaudit/role_configuration.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib --with capstone --with pyelftools --with unicorn --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit
```

Ignored `local/role-configuration.json` contains all 48 cases, raw disassembly,
input/method hashes and explicit limits. All 13 research-component tests pass.
Full caller reachability, runtime settings, parameter units, helper consumers
and RF placement remain open. No message or satellite identity is decoded.
