# Can the full solver refit ambiguous satellite groups independently?

All 111 curved tracks in the original dense DS30-0008 cold search belong to **one connected group** as soon as the four receiver/band offsets are free. The same holds for the 112 tracks in the winning dense short-receiver branch. This occurs with calibration fixed at zero before adding the fitted RF coefficient. It rules out exactly updating only the small group whose satellite label changed while leaving all other fitted receiver parameters and tracks untouched. [Protocol](assignment-components-protocol.md) · [Measured component counts](measurements/assignment-components.json)

At a fixed position, tracks assigned the same satellite can share an orbit phase. The original likelihood also estimates an offset for each receiver and band. One satellite observed across two bands or two receivers can connect otherwise separate groups through those offsets. The census follows these connections transitively. It includes only these links, with the optional RF coefficient in a third comparison. The shared drift, smooth terms and the two position coordinates can couple tracks further. [Original likelihood design](../../../src/leo/analysis/localization_v3/marginal.py)

| Saved assignment set | Tracks | Groups if receiver parameters are held fixed | Largest group | Groups with ordinary receiver/band offsets free |
|---|---:|---:|---:|---:|
| Seven original v3 branches together | 111 | 19 | 24 | 1 |
| Original v3 cold winner alone | 111 | 39 | 12 | 1 |
| Full-short winner alone | 112 | 42 | 11 | 1 |

Across the seven original branches, 43 tracks changed owner or integer alias. Connecting all observed alternatives put 86 tracks in the affected satellite groups, even with all receiver parameters held fixed. On that favorable conditional problem, evaluating every distinct group pattern once would need 44 group evaluations instead of 133. Weighting each by track count gives 452 instead of 777 track evaluations. The ratio ignores row counts, priors, joint posterior work and convergence. It supplies no measured speedup or saved seconds. The actual cold-stage comparison of the three leading dense short assignments found that every common final posterior coefficient and track weight differed. [Measured equality of fit inputs and outputs](dense-assignment-reuse.md)

Conditional sufficient statistics can still be shared while the solver recomputes the common receiver parameters. Independent finished fits for local groups cannot reproduce this objective in general. The receiver fit and position therefore remain global in the next prototype. This archive-only check used one physical location and two detector packets. It scored no positions, touched no raw I/Q and took no Gauss benchmark slot. [Reproduction](assignment_components.py) · [Component tests](../../../tests/pipeline_eval/test_assignment_components.py)
