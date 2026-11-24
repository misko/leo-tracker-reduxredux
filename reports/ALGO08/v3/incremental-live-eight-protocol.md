# Actual compressed demand with the signed 20/8 ms receiver

The previous incremental-ingress work used the same staged physical first
member, a 20/12 ms receiver and replayed chunk arrival deadlines. This
comparison uses the actual original 20/8 ms schedule and operating-system
delivery on the existing resident DS30-0169 tmpfs source. The released
whole read performs one ordinary descriptor traversal. The reviewed
incremental feed reads only when the normal Zstandard reader asks, in
objects of at most 1 MiB. No pacing, injected ready times, arrival trace,
copy, cold read, original backing volume or extra worker.

Use the one pinned manifest, index and compressed member, exact 64
issued visits and 51 admitted stereo visits, 16 full and 86 short native
calls, installed paired SHA-256, and existing original 20/8 ms output.
Verify every original compressed, index, window and decoded member
digest with framing, EOF, complete stable descriptor and chronology
checks. The provisional detector and its state are private to a call.
Only a final successful return permits a signed seal. Component tests
exercise a short or late-failing source, wrong authenticated decoded
authorities and two unaffected returned window lifetimes. No input writes.

Run four fresh processes, whole then incremental, incremental then
whole, under one shared Gauss CPU2 low-priority lock. Record acquisition,
member-to-seal and external launch-to-exit clocks, actual read bytes,
calls, CPU, first decoded window/first finished callback, process input
blocks and peak RSS. Check complete manifest/index/payload residency
before and after each. Require exact matches for native tuples, detector
packet, original signed clocks, and all 64 original IQ hashes.

Consider one already resident independent dense DS30-0008 validation
only if both orders show at least 10 ms actual CPU benefit through the
signed acquisition/seal with no sign reversal at acquisition elapsed.
Report external clocks separately. An earlier first stereo result does
not provide an authoritative publication before all compressed and
decoded checks finish. No new stage or full-rerun authorization is
implied by a successful member.
