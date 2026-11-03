# Server-authority compatibility profile proposal

This is a proposed follow-up, not a production change. The portable native
fractional-support path remains the default and the pipeline-v1 persisted
contract remains unchanged.

Add one explicit profile named
`server-x86_64-glibc-2.43-fma-python-repr-v1`. Bind the profile name and a
source-manifest digest to session authority before observations enter online
tracking. A session must contain one profile. Historical metadata continues to
carry supplied authority strings; it does not silently recompute or relabel
them. Publish the new binding only through an additive diagnostic or a new
authority schema version, because existing published majors are immutable.

Implement the profile as a normal, named library call. Compile the pinned glibc
pow core with its existing symbol renamed, expose a narrow
`leo_server_pow3_fma(double)` entry point, and call it only for the third-power
term inside the compatibility support calculation. Do not export `pow`, use
`LD_PRELOAD`, interpose on process math, or alter the portable implementation.
The second moment retains its already exact operation sequence. Build the
LGPL-derived code as a separately replaceable shared library, ship the retained
notices and `COPYING.LIB`, and preserve the corresponding source and relinking
information.

Return the numeric support and its four authority lexemes from one profile API.
Projection ingestion and `online::derive_support_authority` must call that same
API so arithmetic and spelling cannot diverge. Reject mixed profile names,
manifest digests, non-C numeric conventions, non-nearest rounding, or a missing
compatibility library before accepting evidence.

Keep the measured one-entry thread-local geometry cache. Its key includes every
support input, fractional-offset bits, rounding mode, and profile identity; it
caches only successful results and remains bounded. The 11,747-row DS9 sequence
has 2,237 adjacent hits and 9,510 distinct keys. No broader or unbounded cache
is justified by current evidence.

Promotion gates are the existing 24,681-row binary64 proof, 23,494 exact DS9
lexemes, the 116,364-value host and ARM adversarial formatter test, and the
direct 58-track digest/partition comparison. Add mixed-profile and manifest
rejection tests plus a test proving the portable default is byte-identical.
Measure the explicitly linked profile on physical ARM before enabling it: the
research pinned-pow harness remains slow even with its one-entry cache, and the
current results are compatibility evidence rather than a real-time
qualification. The six duplicate-rank C4 candidate identities remain outside
this profile and must not be hidden by authority serialization.
