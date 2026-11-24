# Standard-format visit frames on the complete physical DS30-0107 recording

The standard writer sealed the complete DS30-0107 recording with one optional authenticated seek table. The unmodified installed reader verified all **29 visits** against the original ordered IQ hashes, including one cancelled 136,857-sample visit and one zero-sample capacity skip. The seek reader independently reproduced all 29 prefixes, including the empty prefix. The original index and whole decoded member hashes agree. The segment retains the original configuration, radio, `incomplete` status, `fault` stop and failure text. The detached authority records the original lifecycle timestamps beside the new writer timestamps. [Frozen protocol](visit-frame-recording-0107-protocol.md) · [Run receipt](measurements/visit-frame-recording-0107.json)

| Measured phase | Wall (ms) | CPU (ms) |
| --- | ---: | ---: |
| Pinned source admission and passive residency | 3.236 | 1.794 |
| Authenticate the original member and hydrate owned windows | 86.276 | 74.870 |
| Ordinary constructor, append and segment seal | 72.321 | 72.305 |
| Write and sync the seek table | 0.183 | 0.183 |
| Seal and sync the detached authority | 0.126 | 0.126 |
| **Writer, table and authority** | **72.629** | **72.614** |
| Independent installed full readback including reference prefix hashes | 97.567 | 97.565 |
| Independent full-authenticated seek readback | 56.136 | 56.135 |
| **Conversion and both independent readbacks** | **312.609** | **301.183** |

The conversion subtotal combines hydration, writing, and both readbacks. The worker clock through sealing was **356.616 ms wall and 343.191 ms CPU**, including its other in-process work. The timed process took **1.36 s wall, 1.18 s user CPU and 0.16 s system CPU**, including startup and excluding the lock wait. There were **zero charged input blocks and zero major faults**. The input manifest, index and payload had all **8,205 pages** resident. The run charged tmpfs file and directory sync. The whole process created one archive and kept all receiver and solver work outside the writer trial. [Measured stage clocks](measurements/visit-frame-recording-0107.json)

The new payload occupied **33,519,348 bytes**, 635 fewer than the signed original payload. With the manifest, index and seek table the output held **33,607,284 bytes**, 5,150 more than the original. The one-member memory and retained output bound reached **90,589,712 bytes**. The seek pass authenticated all 33,519,348 compressed bytes, fed 13,560,526 bytes through the decoder and recovered 17,920,000 prefix bytes. The external authority pins the side table and the full compressed digest under the freshly sealed manifest. [Member pins and lifecycle](measurements/visit-frame-recording-0107-authority.json)

| Ordinary SHA-256 identity | Original | Visit-frame archive |
| --- | --- | --- |
| Segment manifest | `c64d0bb3bcefb4e42eb0a7816bee9d14f47574a7d200129bb10c95a6ac4be49c` | `72d578d505d4eb1293416bdc3b9fc59d5a8ecae857d704c9a7e44fc7a9fc06dd` |
| Recording inventory | `4c05fc0cbe26fcae1c42a85417b4ba20be683f1c8ea0b3fce0eb7a5c273f473d` | `eee87aea7f015ed0f66a73dd559f76b64ff3219986dc23dd34d4a04d73f9c691` |
| Raw authority | `fb9fcc8e0670737cbe1fc5f794a99b6790dc2840d9d652b8587208ab536ebcf7` | `d077f3df44d708906fb5b8a5b88dfa9d700a22126f5d7b8c51b544bc546c4ef1` |

The staged archive at `/dev/shm/leo-v3-frame-visit-0107-recording01/recording-ef0311b07dae436cae968281ad486619` has session `fast-eee87aea7f015ed0f66a73dd559f76b6`. The sibling detached authority has SHA-256 `007f71e30f97fd6b43e5b7e1e3c6cd76f25616ab6abd07926226ea0249397fb7`. The table is `visit-frames-000000.json` with SHA-256 `5ff9bb3ee27c02ff10fa28cd1d2df3d179a123ffef1ae783e26e52220a271196`. The recording is suitable for a separate matched analysis through the same optional seek port as DS30-0016. [Authority and table binding](measurements/visit-frame-recording-0107-authority.json)

Code and protocol were frozen at `572b17ae`. The supplied pinned recording configuration selects the stage, source manifest, expected extents and retained byte limit. The visit-frame codec and selective reader are the same as DS30-0016, and the input fixture for this trial is the existing DS30-0107 recording. The physical job used one historical lock slot. Twenty focused writer, format and integrity tests passed. [Writer](visit_frame_recording_0016.py) · [Frozen DS30-0107 input](visit-frame-recording-0107-input.json) · [Shared format](frame_visit_0016.py)
