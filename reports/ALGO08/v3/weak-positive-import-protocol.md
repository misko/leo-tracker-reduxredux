# Legacy detector import isolation on the weak positive all-visit route

Use the same signed DS30-0016 8 ms saved selection, resident archived
request, full publication flags and original causal region as the sealed
weak profile at `80296c1c3`. Earlier source and trace separate the
legacy receiver and experimental tooling imported by the scanner from
the position module's actual preparation, inference and plotting imports.
The earlier traced 20/12 ms saved route loaded the historical receiver
subtree in 176.7 ms CPU. The current weak profile charged 221.3 ms to
the entire scanner subtree. Its solve policy was stock, with no
history/corner retry. On the older trace those two position fallback
imports cost only 12.5 ms combined; leave their modules alone.

Run only one fresh candidate using the existing independently reviewed
`--lazy-scanner-detector` switch. It defers just the legacy detector
entry in the ordinary scanner loader until actual use, after validating
both source pins. Use no module stubs, feature shims or solver/figure
changes. Record the real loader audit and whether the legacy detector,
differential pilot, SciPy signal, SciPy stats and Matplotlib loaded at
any time before exit. Record inclusive scanner and position first imports
with a narrow observer, and charge the rest of the fresh launch to exit.

Compare to the pinned current weak overhead profile and its uninstrumented
signed publication. Keep original numerical and publication paths, accepted
named survivor fit, both ordered arms, original regional proof and 179
grid nodes and eight decoded PNGs. No original input reads. Use the single
Gauss CPU2 low-priority lock, one numerical thread and fresh tmpfs output.
Individual clock differences have page and process variation. An import
that appears later in the same complete candidate is not a removed cost.
