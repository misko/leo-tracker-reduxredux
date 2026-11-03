# Receiver-convention correction before any aggregate

Version1 component tests passed, but its actual saved-state alignment guard rejected the first b1000 NPZ: the model persists receiver0/1 whereas the original context metadata numbers receiver1/2. No summary, model objective, score or fit was produced. Its source and plan.json remain unchanged; v1_failure.json records the failure.

Version2 makes this convention explicit: persisted receiver equals metadata receiver minus one. Exact observation IDs, channels and times remain unchanged and exact; no tolerance or scientific threshold is loosened. Two added component tests qualify both receiver lanes and reject a wrong conversion/observation ID. All original counting/denominator/adjacency semantics remain identical. The frozen authority is plan_v2.json, including this correction and both test files.
