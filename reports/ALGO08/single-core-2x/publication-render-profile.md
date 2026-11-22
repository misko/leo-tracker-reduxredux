# Empty residual series in the publication renderer

Repeated empty scatter calls accounted for about 0.11 CPU seconds per southern simulated publication and 0.26 seconds on DS30-0374. Each figure axis retains its first empty residual series because it initializes automatic axis limits. Every nonempty series keeps its original order and styling.

| Saved recording | Selected observations | Duplicate empty series omitted | Median render CPU, original → simplified |
|---|---:|---:|---:|
| Southern simulation | 456 | 82 | 1.756 → 1.647 s |
| Physical DS30-0374 | 4,157 | 228 | 2.424 → 2.164 s |

Each test started from the frozen candidate's saved detector packet, reconstructed the solver and eight plots, and compared those bytes with the archived publication. An instrumented render preceded four renderings in original, simplified, simplified, original order. All eight PNGs matched byte for byte in every comparison. On DS30-0374 the original publication store spent 6.7 ms writing the manifest and artifacts and 5.8 ms checking the artifacts. This is a rendering experiment outside the frozen 100-recording candidate.

Run the `publication_render_profile` module with the existing pair path, frozen bundle, `candidate` and pair SHA-256 in the release environment. [Southern profile](measurements/publication-render-profile-south.json.gz) · [Physical profile](measurements/publication-render-profile-0374.json.gz) · [Runner](publication_render_profile.py)
