# Alternating the fifth timing search between antennas

On each hardware-valid two-antenna visit, process four timing regions on both antennas and an additional fifth region on exactly one antenna. Start with physical antenna 0 separately for each integer RF centre. Alternate the chosen antenna on subsequent valid visits to the same RF. Hardware-invalid visits keep their place in the recording and do not advance any counter. The choice uses only the RF and prior valid-visit count. It does not use a position, tile centre, detector score, recording ID, later packet or survey.

The earlier twenty recordings have complete, verified four- and five-region detector streams. Select the corresponding antenna records on those streams and run the actual position solver on the resulting input. This reconstruction measures position after acquisition. It supplies no measurement of the time needed to acquire the mixed stream. The two fresh recordings, DS26-0144 and DS29-0491, test the real mixed detector from saved samples through position. Both use the lower pilot edge and come from the same surveyed roof as the earlier twenty. Score the groups separately before reporting their union.

| Frozen input | SHA-256 |
| --- | --- |
| Original twenty-recording figure receipt | `2bc3768d2c146adc402992f5bbb5714119c2be77ec1959fa6c16329bdebef73a` |
| New lower-edge recording and control schedule | `3c242cadc057614759a17a66959ee2dd4cedd739392d65756c68d2df63ea3f18` |

Validate stock, fifth and staggered results against identical capture-era native input, request, causal catalogue and offered region. The primary denominator includes every scheduled case. Retain missing, timed-out or withheld positions with a blank geographic error, and record any valid diagnostic endpoint separately. Compare zero and fitted RF calibration on the same schedule. Report the geographic median and P95 among published fixes, fraction of all scheduled recordings within 5% and 10% of original no-repair v5, and the original four v5 options. Retain frequency fit statistics as distinct columns.

For each tolerance also count the recordings where both fixed policies, four only, five only, or neither meet the allowance. Their union is the maximum number a selector of the two complete fixed outcomes could attain even with access to survey truth. It is a diagnostic upper bound on that class of selector. Count which recordings the mixed stream recovers beyond that union and which it loses. The previously known twenty define a small difficult subset where both fixed arms exceed the 10% geographic allowance under both calibration settings. This subset is descriptive. Hold it fixed for the new receiver.
