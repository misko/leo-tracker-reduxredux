# One idle-only window for the original DS30-0163 first member

Keep the original first-member enrollment and its earlier zero-residency
result. The only authorized encoded payload is sequence-zero of
DS30-0163's first original signed segment, **78,720,466 bytes** across
**64 visits**. Its signed compressed SHA-256 is
`1ec1091d4b9237b0c367d4cbe5866e96ee594c2632c9a1635ef0ae9add9cb7d2`.
Bind the original inventory, manifest, index, and recorded inode before
opening its data. DS30-0173 stays outside this window.
[Point-in-time admission](ds30-combined-first-member-admission.md)

Use the unchanged quiet-interval I/O gate on dm-5, CPU 2, nice 15 and
idle I/O priority. Release the Gauss lease between single sequential
requests of at most 1 MiB, with random file advice and at most 2 MiB/s.
Allow one staging opportunity of at most **300 s** and one member plus
its signed sidecars. Retain a verified local checkpoint if it expires.
No retry, other member or recording.

Only a complete original compressed, decoded and per-visit verification
permits a resident receiver pair. Use the original scanner acquisition,
named installed-v3 20 ms first or second by the original parity rule
(candidate first for DS30-0163), and the exact current adaptive 20/8 ms
verify-once candidate. Stop at signed detections. Charge physical staging
separately from the resident through-exit clocks. Compare original visit
order, exclusions, lane occupancy and shared selected CFOs. No new RF,
full scan, position solve or speed inference for the full recording.
