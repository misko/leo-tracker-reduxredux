# Semantic decoding checkpoint

Current resumed-run blocker audit 3: re-read the saved family-test and firmware
alignment/variant results and current firmware report. They still establish no
verified encoder/scrambler/serialization mapping or symbol-to-header example.
No pending analysis handle or new external evidence is available in this run.
The same substantive blocker has now persisted across three consecutive goal
continuations. Mark the goal blocked, not complete. Resumption needs a concrete
new discriminating source or hypothesis with independent validation; more
peripheral telemetry labels or arbitrary sweeps are not a decoder. Preserve
DS7+DS8+DS9 and all existing ignored numerical/firmware artifacts. This is a
limit of the present investigation, not proof that decoding is impossible.

Current resumed-run blocker audit 2 (supersedes historical audit counts below):
the previous continuation did not establish widened CGM setup indices or a
public ISA description. This continuation re-read the state-conditioned coding
results, scrambler search, moving-code search, and independent-validation limits.
No new discriminating coding hypothesis or verified header reference emerged.
Repeating these searches with arbitrary additional layouts would not identify
semantics or supply independent evidence. Core blockage is still the unknown
encoder/scrambler/serialization mapping and lack of a validated symbol-to-header
test vector. No process from this work is pending. Do not request private data
or new RF: user scope remains public sources and existing DS7+DS8+DS9. Goal is
incomplete and remains active until the resumed three-turn audit threshold.

Follow-up did NOT confirm wider setup indices in v4. Inspected initialization
5e2e8..5e3c0 and helper5e010..5e06c: no analogous immediate setup-byte stores
established. Immediate member2550 access search is bounded, not alias-complete;
cannot infer that setup is absent or hardwired. Public searches for Starlink
CGM/init_cgm_table/header decoder yielded no relevant register/ISA definition.
No decoder progress from this pass; do not count more peripheral register names
as recovered bits. Core gap remains code/mapping between observed signs and GMH.

CGM variant audit: v4 loader5f2d0 tablesb1d10/b2510, catapult loader64ad0
tablesb7980/b8180, both512words*16 versus canonical256*16. Corresponding tables
differ277(mode3)/291(ordinary) words; no canonical table byte-copy in variants.
Do not transfer indices or coding assumptions. firmware_cgm_variants.py checks
hashes/loader instructions, ignored JSON preserves tablehashes/disassembly;
Ruff pass. Table instruction semantics and header coding still unknown.

CGM table alignment supports setup-byte INDEX hypothesis: ordinary tableaf7a0
A[9:93]==mode3tableaf3a0 B[10:94]. All10 ordinary setup bytes i select identical
words A[i]==B[i+1], exactly tracking mode3+1 values. Runs13–90 overlap (not
independent evidence). Also A[:9]==B[:9], A[93:242]==B[107:256]; padding ambiguous.
Extra mode3byte97 unexplained. New firmware_cgm_alignment.py checks canonical
hash/slices/pairs; ignored JSON+Ruff pass. No instruction semantics, FEC matrix,
or header decode. See firmware-header-analysis.md latest section.

TX metadata counter producer found consistent with adjacent field layout:
6ac10..6ac1c computes uint32(reg(member5f0+64)-savedword664)->output18.
Payload nextdoor reg60-saved660->output14. Baseline routine6ade0 adjusts object
by8000 then6ae08..6ae14 stores both counters. Counter delta, not packet header
length. Complete serialization chain and hardware accounting remain unverified.
Static exact-operand audit/Ruff pass; firmware report updated. No decoded fields.

GMH metadata telemetry lead classified: mpp_pdu_gmh_meta_bytes belongs to TX
beam telemetry uint32, ELF entry10e0a0 name d1ae0 offset18. Adjacent fields
PDUcount/payloadbytes/dropcount offsets10/14/1c. Audit asserts all metadata links.
Producer not traced; callback485d0 returns1, not byte retrieval. No wire-length
inference justified. Firmware report updated; audit/Ruff pass. Header remains
undecoded; metadata-name search alone supplies no coding/placement information.

PHY header status mapping: ELF metadata10bdc0/10bde0 names header_decoder_error_cnt
and mcs_decoder_error_cnt at output offsets16/18 hex. Routine62208..6221c reads
cb0+168 twice, upper16->header error, lower16->MCS error. Static audit verifies
relocations, metadata offsets and exact instructions; Ruff pass. Hardware read/
write semantics unknown; no claim header==GMH or LDPC. Register status is not
on-air bits. Detailed firmware report updated; no newRF or firmware execution.

PHY cb0 block follow-up ties it to named receive LDPC counters. Routines
61dc0/61e90/61f60 identify get_rfp_ldpc_codewords/syn_failed/corrected via
assertion diagnostics. They read block+4*(3c/2c/1c + low8user + 4*objectword2c),
require low8user<=3, maskbit31 and accumulate. This is counter behavior, not
header FEC identification; setup words remain unknown. Extended static audit
and Ruff pass; docs updated. Offset search is not exhaustive alias analysis.

PHY firmware upstream setup audit: object+0xcb0 points to constructor base+0x4000.
Three register words at offsets4/8/12: ordinary 351c155b/38220e3d/00004345,
mode3 361d165c/39230f3e/00614446. First10 little-endian bytes each increase1;
next changes0->97. Exact instruction/hash assertions pass; semantics UNKNOWN,
not generator evidence. firmware_phy_register_audit.py/ignored JSON, Ruff pass;
firmware-header-analysis.md updated including stale receive-leaf target. Next
trace other register-block accesses/diagnostics; do not invent FEC parameters.

Separate early-phase hypothesis tested with disjoint sequence slots: fit phase
and polarity per frame on slots 0–29, evaluate 30–59 over symbols 2–7. Middle
443/916 errors (48.36%), last 489/900 (54.33%); 20 fixed shuffled-codebook controls
average 48.17%/46.90%. Tail symbols 272–277 positive controls give 3/884 (0.34%)
and 5/869 (0.58%), shuffled 45.88%/47.89%. Thus changing phase/polarity does not
rescue this physical -16-step header layout. Other serialization/masks remain
untested by this probe. Synthetic test verifies held slots cannot influence fit;
Ruff passes. ds9_header_family_test.py/ignored JSON. No semantic fields decoded.

Frozen tail-phase prediction does not explain header symbols 2–7: on the
middle-trained amplitude gate, middle 1,645 decisions disagree 45.90% versus
46.51% shifted-phase mean; last 1,623 disagree 48.86% versus 48.32%. Late
positive controls at symbols 272/301 disagree 0–0.38%. No header phase or polarity
was fitted. Middle symbol 13 shows partial agreement, not reproduced in last;
do not label it a boundary. ds9_header_tail_prediction.py and ignored JSON retain
per-symbol counts, shift controls, and hashes; Ruff passes. This rejects direct
continuation under the tested physical indexing, not other scrambling/layouts.

Header/tail distribution audit corrects the interpretation of sparse parity
support: the middle-trained amplitude gate retains 49.67%/49.00% of individual
header observations in middle/last, versus 49.94%/49.23% of tail observations.
The three-bit conjunction, not wholesale header rejection, leaves few triples.
After per-coordinate centering, real RX correlation header/tail is .584/.624
middle and .367/.437 last; imaginary correlation is .220/.227 and .017/.037.
There is no header-specific quadrature excess in this comparison. This does not
identify modulation or exclude additional bits. ds9_header_quadrature.py and
ignored JSON preserve per-symbol results/hashes; synthetic offset-control test
and Ruff pass. Continue coding/layout work with soft observations; do not infer
header BER from the sequence or claim imaginary correlation is a second stream.

Amplitude reliability check: thresholds learned from DS9-middle discovery tail
transfer to DS9-last. Keeping observations above the discovery median absolute
combined real amplitude retains 8,270/16,560 middle decisions with 34 disagreements
(0.41%) and 8,152/16,560 last decisions with 47 (0.58%). These are disagreements
with the inferred known repeating sequence, not measured header BER. The same
fixed threshold leaves only three complete header parity triples per visit;
agreement equals the marginal baseline and supplies no new constraint evidence.
Higher thresholds leave still less header support. Three targeted tests and Ruff
pass. See DS9_LAST_VALIDATION.md and ds9_combined_reliability.py; numerical results
remain ignored under local/. Continue using existing DS7+DS8+DS9; no new RF.

Native-symbolphaseprobe DS9last8frames(1,14,28,43,51,64,76,88)*2RX*2alternate
pilotcarriersplits=32. Re-demodexistingIQ usingstoredsampleclock/slopes; incremental
phase9symbolboxcar fitonehalf evaluateother. Meanheldpilotcoherence.58437->.57638,
ZERO32improve;headerpilotcoherence.56240->.55778. RejectadditionalCPEsmoother,
nativeunchanged. Baselinecalibrationusedallpilots,incrementaltestonlydisjoint;
coherence notBER. ds9_symbol_phase_probe.py/ignoredJSON;syntheticslowphase test
andlintpass; report DS9_LAST_VALIDATION.md. No newRF/download. Thisnoise-tracking
possibility doesnot establishphysicalcause or ruleoutotherdemodimprovements.

Combinedheader frozen3bitparitycheck(s3,524)^(s3,537)^(s5,524)=1 onlater23frames:
DS9middle13/23=56.52% vsmarginal60.38%,shiftmean62.85%;last17/23=73.91% vs78.19%,
shift77.08%. All3constituentsvary overall. Confidence>.9allbits leaves1/3frames,
allpassBUTbaseline100%andnonevary;noevidence. Combiningtailbenefit doesnotrescue
localparity. combined_header_parity.py/ignoredJSON triples/masks/hashes;
reused2baseline tests+lintpass; report DS9_LAST_VALIDATION.md. No correction imposed,
nativeunchanged,no newdata. Need codinglayout/independentconstraints still.

DS9 receivercombining POSITIVE onheldtail:trainfirst22frames242..271,eval23frames
272..301,phasefrompairedwindows<242. Equalreal sum errors/16560 middle1102(6.65%)
vsRX01946/RX12010;last1393(8.41%)vs2761/2543. Fitted5coeff/carrier leastsquares
middlemodel1380/1820;lastmodel1058/1330 acrossmiddle/last. Equalno-fit robust,
not productionadoption orheaderBERproof. Savedseparateignored DS9-middle/last-
combined-header.npz soft(z0+z1)/2/signbits/bins/symbols/sourcehash/evalframes;
UNVERIFIEDheaderestimates,nativeunchanged. ds9_receiver_combining.py/JSON hashes,
coefficients,counts;syntheticindependentnoiseheldtest+lintpass. Report
DS9_LAST_VALIDATION.md. Nextusecombinedestimates for paritydiagnostic withknown
baseline, do notvalidateagainstreceiversusedincombinationasindependenttruth.

DS9 tailcarrierphase experiment:phasefrompairedacceptedwindowsending<242;
eachRX/frame/carrier gainfit242..271, rotatephaseonly,eval272..301 andheader2..7.
Later23frames/visit. Medianrotation6.6..7.9deg. Tail errors/16560 middleRX0
1946->1996,RX12010->2102,last2761->2819/2543->2564. Headeroriginalfrozenmask
middle86.35->85.71%,last77.48->77.29%;RX0onlyunchanged,RX1onlysameasboth.
Rejectthiscorrection;retainnativecalibration. NotBER/whollyindependentwordphase.
ds9_tail_phase_transfer.py/ignoredJSON;syntheticgain/amplitudetest+lintpass;
DS9_LAST_VALIDATION.md appended. No newdata/nativecachechanges.

Lower-edgeparityprobe directlyinDS9bins516..527/536..547symbols2..7:
first39ref108eligiblevaryingpositions132weight2/3equations;only1exactall39eval:
(s3,b524) XOR(s3,b537) XOR(s5,b524)=1. Local45heldframes/RX:
DS9middle60.0/48.89% vsbaselines57.40/55.24;DS9last66.67/64.44 vs68.25/64.88.
Allconstituentsvary; no consistentexcess,NOTvalidlocalcheck/correctionrule.
lower_edge_parity.py/ignoredJSONallcandidates/hashes;syntheticcopy/XOR/constant
exclusiontest+lintpass. Report DS9_LAST_VALIDATION.md appended. No newdata.

AdditionalDS9 last10Msessionindex52 existingvisit exported readonlycontracts:
scan-fw-c64b5da401800b53 visit1295lower,pairedmaxweakerpilot margins.83861/.83464,
120ms1.2Mcomplex/RX,noRF. Native89frames24bins both45heldpilotqualified;tailQ
.399/.385. Fixedwordassay331/405accepted,45framesmultiple/noconflicts,28words,
ALL331known60generator. Changingheader audit96coords1079helddecisions77.48%RX
agreement vsframe-shift57.69%(55.70..59.96),marginal60.10%;notFEC/semantics.
Ignored ds9-last-10m,DS9-last-soft.npz,ds9_last_quality/word_audit/header_audit JSON.
ds9_word_audit.py now--tag(defaultmiddle preservesoldoutput). Report
DS9_LAST_VALIDATION.md. Additionalrecordingconfirmsstructure,headerstillnoisy.

Firmware reset/audit:canonicaltx_lmac SHAa921819... staticGMHscheduler strings
1128f8/1129c0/112a20 plus92d1c..92d38 arithmeticceil(bits/bpcw)*spcw.
Helpere04c0tablechecks+16bytecopy e051c/e0524, notencoder. Boundedpath yields
NOpolynomial/interleaver/scrambler/onairmapping. Explicitly notproofhardwareonly
orabsenceelsewhere. firmware_tx_gmh_audit.py verifieshash/exactoperands, ignored
JSONdisassembly, lintpass. Firmware-header-analysis.md updated. No execution,
download, orRF. 32/114remainsaccountingfact; convolutioninterpretationhypothesis.

State-conditioned convolutiontest:trainstatecounts23/11/3/2 too small toidentify
separate32inputencoders. Instead same-stateXOR tofirstdiscoveryanchor cancels
state-specificfixedmask;35traindiffs/31evaldiffs (8unknownstatesabstain).
Same153rectangles7344layouts/pairs,1120trainwindows/config:ZERO exact7tapmixed
checks. Fixedstate-mask doesnotrescue testedcommonshortconvmodel. Othercoding/
state-specificencoders/framevaryingmasks/errorsnotexcluded. Existing
rectangle_convolution_probe.py --state-conditioned, separateignoredJSON;
2tests inclstatemask/unknownabstention+lintpass; report HEADER_BLOCK_RANK.md.
No newdata. State semantics andactualencoderstillunknown.

State-conditioned templates first39train later39eval, ONLYsymbols5..7 excluded
from statedefinition2..4. Discoveryvariablecoords20–80%,>=3qualifiedstateexamples.
31evalframesknownstate;8unknownabstain47,67,68,71,73,75,76,77. Conditionalerrors
symbols5/6/7 44.70/40.12/46.46% vsglobaltemplate47.11/44.98/48.08%;counts28235/
28028/29511. Modest broadassociation, notbitdecoder. State definitionsfitall78
so notfullyindependentvalidation. state_conditioned_header.py/ignoredJSON;
syntheticstate/qualitytraining test+lintpass, report HEADER_BLOCK_RANK.md.
No newdata. Need structure strongerthanconditionalmajority before fieldclaims.

Sharedstate structureprobe:78frames32runs longest8;adjacentequal59.74% vsuniform
labelpermutation expectation26.61% (descriptive,notp). First13measuredframes states
0..3 have widelyvaryingtailboundarywithinstate;state1 earlyhardends7/24/7,state2
7/10/7/9/9/9. LOOstate-median tailMAE38293 vsall-other41126positions;earlyend3.00
vs3.04symbols. No lengthdecoder or semantics. Earlyhardaxisnottrueheaderlength.
shared_state_structure.py/ignoredJSON runs/table/hashes;2run/LOOtests+lintpass.
Report HEADER_BLOCK_RANK.md appended. Labelsfitall78;sameacquisition limitation.
Next inspectpersistentstate changes vsheaderbitlayout/conditionaltemplates, not
assignID/time/orbit from categoricallabels. No newdata.

Sharedcoordinates from37pairing-dependentrectangles:70distinctnormalizedtraces,
unionrank8 but ONLY9jointstates across78ref, sortedcounts1,1,1,2,2,3,14,26,28.
Rank8=max9states-1; NOT8independentinformationbits. All70raw equalitychecks pass
but ZEROsharedcoordinatesvary amongqualifiedrawframes. Priorvaryingconstituents
doesnotmeanvaryingXOR; novelcompletewordscanchangeunsharedcomponents. Thisweakens
encoderinference, identifies9observedconditionalstates (semanticsunknown).
shared_header_coordinates.py/ignoredJSON contains70explicitcrosssymbolXORs,
ref/rawtraces,masks,stateindices/counts/hashes. Syntheticsharedinversiontest/lint
pass; report HEADER_BLOCK_RANK.md. Next correlate9state familywith headerregion
structure/boundaries using existingframes, avoid sourcebit/IDclaims.

Rectangle framepairingcontrol:153windows,77nonzero circularshifts second-symbol
frames, preserves eachsymbolworddistribution/cyclicorder.139observedrankstrictly
belowallshifted.105windowsALLshiftedranks<=32 ->boundweakthere.37windowsALLshifted
ranks>32 vsobserved<=32;11mixed.69.26%shiftedtests<=32. Narrow37candidates:
symbols2/3 starts723..725;symbols2/4 starts872..884 and891..911 (width57).
Sharedpairedvariation, notproofFEC/commonstatespossible. rectangle_rank_control.py/
ignoredJSONallshiftranks/hashes;syntheticmatched/shuffledrank+offsettest/lintpass.
Report HEADER_BLOCK_RANK.md. Next inspect37paired-dependent windows for common
informationbits/conditionalstates;avoid treating all153asencoderconfirmations.

Known60sequence explanation tested on1532symbolrectangles:phase/polarityfitfirst28
positions/frame, predictother86 withestablishedcompactslotmapping.321/11934 exact
rectangleframes ALLconstant-sign;0nonconstantexact. Discoveryfirst39 selectvariable
coords, evaluationlast39 375258dependentdecisions:generatorerrors46.78% vsconstant
fitbaseline47.84%,better77/153windows. Notadequateheaderdecoder underknownalignment;
othermasks/alignmentsnotexcluded. rectangle_sequence_test.py/ignoredJSON/hash;
syntheticphase/held-positionisolationtest/lintpass. Report HEADER_BLOCK_RANK.md.
Tailresultunchanged,no newdata. Lowrankheaderstructure stillunexplained.

Rectangle convolutionprobe:153surviving2symbolrectangles,2symbolorders*2carrier
orders*2serialization(symbol/carriermajor)*2streamlayouts(interleaved/blocks)*
3pairs=7344configs. Blindmixed7tap14columncheck,all32windows x38frameXORs=1216
discoveryrows/config,constantcolumns excluded. ZERO exactdiscoverychecks.
No testedshortconvolutionalrule despite lowrank; otherinterleavers/memories/
codes/state/errors remain. rectangle_convolution_probe.py/ignoredJSON/hash;
synthetictwogenerator+injectederror test andlintpass; report HEADER_BLOCK_RANK.md.
No newdata/nativechanges. Next revisit source of lowrank/template structure,
not assuming firmware32/114 implies this convolutionalencoder.

Two-symbol rectangle rawtransfer:fit all78ref,153rank<=32survivors,2847unique
mixedsymbol equations,all>=4qualifiedrawframes/zeroerrors.60equations have varying
constituents in bothsymbols,weights6..11. Wholeblock rawquality2..6frames;rank
increase0/153. Novelrawwords:81windows0,31one,30two,6five,5six =>72windows
genuinelynewwords stillinrefaffinesubspace. Sameacquisition,notencoderidentification.
Example symbol2 bins600/603 +symbol3 bins600/601/612/627 XOR0,7raw/4varyingbits.
header_rectangle_transfer.py/ignoredJSON(allconstraints/support/hashes),testmixed
classification+existingpredictortests/lintpass. Report HEADER_BLOCK_RANK.md.
Next seek minimalnonoverlappingrectangle boundaries/affinesubspace dimension and
check templatefamilyexplanation before mappingbits to32input/codeword.

Rectangle114bit rank test across symbols2..7 subsets, contiguousnativebins no
pilots/gutters. 2x57:12900starts12105active504trainlow411evalqual153combinedlow;
3x38:17960starts17814active79trainlow57evalqual0combinedlow (22unqualified);
6x19:950starts936qualactive0trainlow. Surviving2symbol:96symbols2/3,57symbols2/4,
ranks16..32; neitherindividualconstant, sharedrankdimensions1..6. Notencoderproof.
57carriers span13.125MHz centers, beyond10MS/s;38/19span8.672/4.219MHz nofully
qualifiedcandidates. Restrictednegative, errors/state/interleavers notexcluded.
header_rectangle_rank.py/ignoredJSON testcoordinate/rankpermutation+lintpass.
Report HEADER_BLOCK_RANK.md appended. No newdata; candidate2symbolsharedvariation
is next structural lead, or revisit rank under conditionalstates.

Joint local parity prediction: enumerate frozenrefconstraints,4bits8words S01/02,
14bits64words S13/22/23 (11equationsdependent), maximize sum directionalsoftscores
usingoneRX, evaluateotherRX. S13direct70%->69.3/67.9%;S22 73.7->71.0/70.5;
S23 78.9->82.3/85.7 but majoritybaseline85.7/83.3. Target-omitted predictions
usuallyworse; S23 78.2/80.3. S01nochange/S02oneRXworse. Notconsistentcorrection,
keep empiricalrelations as hypotheses, notdecoderconstraints. local_parity_prediction
.py/ignoredJSON;2synthetic weakerror/target-exclusion/unconstrainedtie tests+lintpass.
Fulltable appended LOCAL_REFERENCE_PARITY.md. No raw/nativechanges/newdata.

Reference parity localtransfer:11equations fit cached upper-edgecarriers,allOFDM2;
S01/S02 one each22/21heldframes,S13/S22/S23 eleven10/16/21frames. DS9caches no
equationcoverage. Frozenrefequations, nolocalparityfit. Pooled4bit484/486/487/496
XOR0 n90/RX63.3%both vsbaseline55.8/54.3%. 3bit499/505/506 XOR1 n47 RX74.5/70.2
vs62.7/53.1%. All11 tables report LOCAL_REFERENCE_PARITY.md; dependentcomparisons,
variablevisitresults,no verifiedcode. Strictallconstituentaxis>.9 gate yields
<10observations for EVERYvisit/equation/RX. local_reference_parity.py/ignoredJSON
includesallcounts/pools/hashes;2syntheticbaseline tests+lintpass. No newdata.
Next jointlytest equations for held-outbitprediction before any correctionclaim.

Fixed affine predictor near9bitcandidates: OFDM2 bins901..937 rank16discovery->22
combined,7/21exactlater rules;880..993 width114 rank24->39,11/90exact;
888..1001 width114 rank26->41,11/88exact. All39+39reference qualitypasses.
These2widewindows violate fixed32input encoder bound. Raw7frames pass ALLrules
(21/90/88), despite referencefailures: insufficientrawstate diversity, do not
overinterpret rawtransfer. Smallwindow survivors3copies+4higher; wide7constant
+4higher. Source header_block_predictor.py/ignoredJSON(allrules/errors/hashes).
Synthetic affine+held-error test/lintpass; report HEADER_BLOCK_RANK.md appended.
No native decoderchange/newRF/download. Need differentmapping or independent
structure, not interpreting empiricalbasis as MACinputbits.

Nine-bit parity translation test:1849allowed nativebin shifts,437 fullyqualified
and all9 discoveryvariable, exactly2 constant across78frames=originals delta0.
No demonstrated slidingfrequency code; block/conditionalmapping remains. Both
original9bitblocks affine rank8,27distinctpatterns,10novelevalpatterns. Exactly
one affine constraint within each9coords; no proper-subset parity there. All11
cached DS7/8/9 paireddecodes lack originalcarriercoords (cachecoverageonly).
header_parity_translation.py/ignoredJSON includeshashes/allshifts/coverage;
syntheticheld-error/quality test+lintpass, report HEADER_BLOCK_RANK.md appended.
No new data. Next inspect fixed-block structure around901..937 or find relations
inside alreadycaptured localcarriers; do not assume slidingcode or bitsemantics.

Header rank relation followup:2644discovery-selected/evalquality windows,123166
weight>=3 basisrelations,6101 exacteval,1497unique coordinateequations. None1970
combinedlowrank survivors explained solely constants/copies. Transfer to7existing
pilot rawframes:1494exact of1497(all>=4qualified); BUT1417passing have zero
changing constituents; only2 have every constituentvary, bothweight9. Example
OFDM2 bins901,903,905,906,916,917,918,920,932 XOR1 across78ref+7rawframes.
Not identified encoder/check; sameacquisition, limiteddiversity risk. Source
header_rank_relations.py, ignoredJSON(allrelations+transfers), report appended
HEADER_BLOCK_RANK.md. Syntheticcopy/parity/held-error test+lintpass. Nextinspect
two variable9bitrelations vs conditional templates/localcoverage before semantics.

Reference candidate check: existing78 hardframes allqualified symbol2 bins498/503;
17disagreements/78, agreement78.21% vs marginal78.73%, corr-.058. Reject universal
copy rule; local conditional effect unresolved. reference_header_candidate.py/JSON.
Completed pending header_block_rank.py on same existing78 cache:23644starts,
20926quality,18854active>=64,2940discoveryrank<=32,2644evalquality,
1970combinedrank<=32 (starts symbols3/4, ranks7..32). 822survivors rank equals
distinctwords-1 (limitedpatterncount), none nonmodalframes<=32. Example FFT+
start2821 rank3->7,87activecolumns,8distinctwords/78frames,50nonmodal.
No encoder identified. Next examine remaining windows for bit-copy/template
structure vs nontrivial parity before inferring32-to114 encoding.
Report HEADER_BLOCK_RANK.md; ignored JSON updated, rank test/lint pass.

Header candidate common-phase diagnostic: symbol2 bins498/503 excluded from
reference selection and phase estimate. Other carriers selected discovery mean
unit-phasor magnitude>=.5; held-out targets corrected by reference common phase.
S13 RX0/RX1 corr .139/.879 ->.361/.725; S22 .395/.813 ->.495/.712;
S23 .026/-.111 ->-.161/-.188. This estimated phase does not fully explain
candidate but references are not known bits, other calibration effects remain.
Relative-phase coherence RX1 S13 .466/S22 .509, not near-perfect equality.
No validated copy relation. header_common_phase.py and ignored JSON; synthetic
target-exclusion/injected-phase test and lint pass. Report appended to
LOCAL_HEADER_RELATIONS.md. No new recording/download or native decoder change.

Local soft header pair search: single maximum absolute centered correlation
among RX0 discovery-variable coordinates per visit, fixed polarity, later frames
both RX and cross-RX evaluation. Most fail. S22 symbol2 nativebins498/503:
discovery .938, held RX0 .395 RX1 .813 (14/16 signs agree vs53.1% baseline),
cross .425/.542. Same pair transfers S13 RX1 .879 but RX0 .139 (10frames);
S23 RX0 .026 RX1 -.111 (21frames). Inconsistent, not a duplicate-bit rule.
DS9 best discovery .736 becomes RX0 -.328 RX1 .006. All14 available transfers
saved local/local_header_relations.json; report LOCAL_HEADER_RELATIONS.md.
Two synthetic tests and lint pass. No new data. Next diagnose S22/S13 candidate
against shared calibration/neighbor leakage before trying to combine its signs.

Local header recovery audit: existing nine DS7/DS8 caches plus two DS9 caches;
six have >=12 paired evaluation frames with both held-pilot coherences >.5.
RX0 discovery selects variable coordinates (20–80% positive) and median axis
confidence; held-out RX0 selects samples without RX1 agreement. Symbols2–7
matched agreement S01/S02/S13/S22/S23/DS9-middle =80.17/76.77/69.47/76.80/
78.71/86.35%, shifted-frame means55.06/51.90/54.27/51.15/55.27/52.49%.
DS9-middle1099 decisions. Evidence of shared changing signs, not verified bits,
plaintext or fields. Raw receiver strings, masks, agreement-only erasures,
hashes and splits saved ignored local/local_header_recovery.json. Source and
tests local_header_recovery.py/test_local_header_recovery.py; report
LOCAL_HEADER_RECOVERY.md. Tests/lint pass. No new recordings/downloads.

Headerrepetitiongridprobe: frameXOR, adjacentchanges, R2..32 bothphysical/FFT
orders6symbols; offsetselected3rawpairs, eval6softreferencepairs. Symbols2/4
R2/4/8/16 changefractions50.94/25.12/13.23/6.86% and50.75/26.52/12.21/6.13%,
nearcoverage1/R, nofixedrepetitionconcentration. 1429/2006changes. Nojustification
collapsecarriergroups. 372configs savedlocal/header_repetition_grid.json;
script+syntheticrepetitiontest/lintpass. Variable/pilotadvancinggridsnotcovered.

Noise-tolerant time-codeprobe: fullsymbolpairs pooled7tap Walsh masksweight4..10,
activecols10–90%;60configs918960maskconfigs. Rawbest .514discovery waswithin-
streamparitybias baseline.555 (eval.189/baseline.175). Final selection maximizes
excess over productstream-paritymeans. Selectedsymbols3,4 physical+,mask15878:
trainexcess.18363/2568windows, evalexcess.01253/5862, evalcorr-.01433~chance.
No usefulcoderelation. Shortembeddedcodescoulddilute; notallFECexcluded.
noisy_time_code_probe.py/localJSON; noisyinjectedrelationtest/lintpass.

Time-separatedcodeprobe: pairsamongOFDM2..7 asencoderoutputs,38carrierblocks,
7tapmixedGF2relations,physical/FFT±orders. Raw3framepairsdiscovery,softreference
6pairsavailableeval.58020configs57320support,0exactdiscovery; noevalcandidate.
Differentmappingfrompriorwithin-symbol114bitassays, stillrestrictedexact
noisetolerantnotdone/generalinterleavernotexcluded. time_separated_code_probe.py
localJSON; indexing/qualitytestlintpass. Headerencoderstillunresolved.

Tail-to-header bin511phase transfer: fitlinearphase firsthalftail knownsigns;
remainingtail0/1486signerrors. Extrapolateheader2..7 (notinfit): meanQfraction
.41777→.08962,11/13framesimprove. Only6headerdecisions/frameatonecarrier;
axisalignmentnotvalidatedbits/headerdecode. Originaldataunchanged. Script
tail_header_phase_transfer.py/localJSON; knownlinearphase test/lintpass.

Bin511 EXPLAINED forsignrecovery bycomplexgain: first30tailsymbols/framefit
mean(z*boundarypredicted_sign), evaluateallremaining. Bin5111880/2576 original
errors ->0/2576 corrected. Neighbors5100/2576,5120/2563 before/after. 511angles
~ -174..169deg vsneighbors~-1..11. Samegenerator aftercalibration, noextrabits
evidence. Physicalcauseunknown; notboundary-onlyunfittedprediction orproofgain
transfersheader. Rawtail2errorsboth511frame251(twoedges), only9carriersymbols/
edge across4frames, insufficient30split. tail_carrier_phase.py/localJSON;
syntheticgain/evalisolationtestlintpass.

Tailerrorlocalization:2180/2186referenceerrors nativeFFTbin511; other6 at513(2),
514(2),515(1),518(1). Discovery0..5 selects errorfraction>.1 =>511only. Discovery
bin5111227/1461errors, others1/1462598. Eval6..12 bin511953/1505, others5/1505677.
Exceptionhighamplitudetypical, notjustweaknoise; nosemanticclassification. Keep
overallresultsincluding511. tail_error_localization.py/localJSON; evalisolation
test/lintpass. Nextinspect511rawspectrum/adjacentcarriers ratherthanclaimnewbits.

Boundary-only fulltailprediction verified: phase=-b%60, fixedpolarity+1,
slot=(absolutecompactn-32)%60, noword/phasefit. Reference13tails2971241decisions,
2186errors (~.074%); first240/frame3120total only1error, preboundary1516/3120
errors~chance. Raw4frames*2edge tails16122decisions2errors; first1920zero;
pre990/1920. Boundary+1control~50%errors. Strongdeterministicsequenceonset
evidence; sameacquisition reused, periodicdecisionsnotindependentbits, rawedges
shareIQ, b+60indistinguishable. Noheader/paddingsemanticclaim. Script
boundary_tail_prediction.py/localJSON; indexing/moduloambiguity test/lintpass.

Direct boundaryheaderfieldprobe: fullsoftUT13frames symbols2..7; discovery0..5,
eval6..12; binaryboundary18bits, symboloffset8, carrieroffset10, remainingcount19;
LSB/MSB +physical/FFT±orders, allcontiguousstartsinclcrossings, fixedXORmask fit
discoveryonly, |real|/abs>.9 qualification.183188supportedconfigs,0exactdiscovery.
Bestdiscovery8/48errors ->eval33/55errors; no copiedfield. Restrictednegative,
notabsencecoded/interleaved/variablescrambledheader. header_boundary_fields.py
ignoredlocalJSON; injectedfield/evalisolationtest andlintpass.

DS9 quadraturestructure: 22discovery/23evalframes, last60symbols. Qsign RXpair
agreement57.41%/33120; RX0absQ gatesfixeddiscovery50/75/90percentiles give
61.92/66.45/70.92%, n16230/7842/3091, baseline~50%. Different-frame49.38%;
symbol-lags1,2,5,15,30 ~49.48–50.16%; nativebinlags1,2,4 ~49.51–50.38%.
Real sign unshift81.01%, lag15/30 78.35/79.09%. Qdoesnotshowknown60word
repetition; weaksharedcomponent notdecodedbits. ds9_quadrature_structure.py,
ignoredJSON;2tests/lintpass. Need coding/otherreproduciblestructure or diagnose
sharedinterference rather than confidencegate alone toclaimpayload.

DS9 nearestcarrier leakageprobe: knowncyclicsigns*relativepublishedtemplate,
complexlinear perRX/carrier, intercept; radii0/1/2/4. Phase fromacceptedwindows
ending<272, regression272..301, first22framesfit/last23eval;16commonnonpilot
neighborhoodtargetbins. Evalimagcrossraw.18864, residual .19083/.17824/.17673/
.17712 => -1.16/5.51/6.31/6.11% reduction. SingleRXimagpower reduction<1.3%.
Simple same-symbolneighborleakage notmainexplanation; notpayloadproof. Script
ds9_leakage_probe.py localJSON; linear/evalisolationtestpass. Next inspect paired
quadraturedecisionreproducibility/timefrequencystructure; other-symbol/pilot
leakage/interference/calibrationremainpossible.

DS9 crosspower diagnostic: paired45evalframes last30symbols272..301. Matched
realcross1.31842, imagcross.20414 =>Qfraction.13407. Different-frameimagmean
.00668 sd.04321; residualQ shared, notonly independentnoise. Fit perRXaxis
on242..271 thenevaluate272..301 givesQfraction.13531 (noimprovement).
No newquadraturebitsclaim. ds9_cross_power.py ignoredlocal/ds9_cross_power.json;
syntheticshared/noise testpass. Next: predict sharedQ using knownneighborcarrier
patterns and linearleakage model fit/evaluatedonseparateframes; avoidpayloadclaim.

DS9 paired recovery SUCCESS: second visit selected maxweakerRXmargin in middle
10Msession index26/53 scan-fw-fad62f2672600b46 visit50 lower; margins.87094/.86146.
120ms existingIQ. BothRX89frames24bins;45evalframesallheldpilot>.5. TailQ .367/.364.
ds9_word_audit.py fixedwindows14,46,..270 (32symbols):405attempted,368accepted,
45framesmultiplematches/nointernalwordconflicts;28words20families;ALL368exact
known60stategenerator. Phase meaning via localboundaryNOTyetindependenttested.
Ignored DS9-middle-soft.npz,ds9-middle-10m,ds9_middle_quality.json,ds9_word_audit.json.
Next attempt sign-independent boundary inside captured DS9 bins; do not infer
missingboundaryfromphase and call it validation. Exportnow--session-index/--tag/
--paired; decoder--tag. Pairedselector test passes.

DS9 timing/alias probe: frame0 trainpilot-selected sweep alias±2/TS andtiming
±2native samples/0.5step separately. Bothoriginalaliasbest; timings+1.5RX0/+1RX1.
Frame1heldpilot baseline→selected .33186→.32269 RX0, .48457→.48495 RX1; nofix.
No cache/acquisitionmutation. ds9_calibration_probe.py/localsamebase.json;
next sampleanother existingpaired DS9 loweredgevisit, not assume correction.

DS9 first actual demodulation: selected first10MS/s session
scan-fw-2ab18976d4eb3bf8 strongest either-edge startzero pilot, visit1536 lower
channel3, RX margins .62939/.78602, 120ms existingIQread via read-onlycontract.
Source manifest verified; ignored local/ds9-first-10m excerpts/inventory.
decode_ds9_visit.py produced local/DS9-first-soft.npz,89frames24bins/RX.
Heldpilot>.5 evaluation RX0=0, RX1=25, paired=0; RX1tailQ=.44294.
No boundary/signature validation yet. First/middle/last10M sessions initially
upperfilterzero; firstsession has4438lowerprobes. Need loweredge-aware selection.
Next diagnoseRX0 calibration or sampleanother existingpaired loweredgevisit.
Export script requires sudo productionvenv for readpermissions; noQNAPwrites.

Local transfer feasibility: nine existing S*-soft pairedvisitcaches; both-RX
evaluationframes + heldpilotcoherence>.5 yields179framepairs acrossS01(44),
S02(41),S13(20),S22(32),S23(42); fourothercacheszeroeligible. 11/24carriers per
symbol. Final10symbolQfractions .369–.436 averagedbyvisit/RX; none358 individual
RX/frame tailsbelow.1. Cannot transplant clean fullband boundarydetector or
concatenatemissingcarrier gaps. No local phase-boundaryvalidation yet; not
DS9/exhaustiveaudit. Script local_boundary_feasibility.py, ignored JSONsamebase.
Next: examine DS9 existingrecordingavailability/quality or improve local
calibration/averaging, preserving independent boundary/phase selection.

Restricted firmware budget probe: b=114*h+L*n, h1..16, npositive,132nonzero MCS
records, nooffset/mixedMCS. Seven referenceframes0,2,3,6,8,9,10 nofit; remaining
frames1,4,5,7,11,12 have33,1,1,1,2,9 MCS-labelled matches (7,1,1,1,2,4distinct
budgets). No header length/MCS decode; limitedmodelassumptions and firmwareage
mismatch. Script boundary_codeword_budget.py, ignored result samebasename.json;
shared-length ambiguity test/lintpass. Phase-boundary relation remains valid.

Raw-IQ cross-check: raw_tail_boundary.py uses existing pilot_polarity.npz,
last6symbols, same502flank powerboundary. Eligible beforeQfrac>.3/after<.1:
raw250,251,254,255; boundaries299288,300517,298469,298465; phases52,23,31,35.
Both edge references identical; all residues0. Fit lowerhalf lastsymbol
postboundary angularqualifiedcarriers; evaluateupperhalf: all0errors, support
477–502 peredge/frame. Raw252/253/256 lackaxis tails and ineligible, notfailures.
17distinct eligibleframes total now, samepublicacquisition/differentprocessing,
not DS789 evidence. Data local/raw_tail_boundary.json; testgate/lintpass.

MAJOR UPDATE: full soft frames0..12 now cached ignored full-soft-reference-0-12.npz.
Sign-independent change point on Q²/(I²+Q²), first/last502carrier flank means,
search coarse-4..coarse+1, predicts ALL13 phases: (boundary+phase)%60=0. Flanks
251/1004 give identical boundaries. Soft boundaries [63353,10696,122564,46855,
21574,78099,117649,31814,100627,57095,38777,106066,149190]. Frame9 phase=25.
All prior exceptions disappear using soft rather than forced hard coordinates.
Supports phase as start-offset modulo60 in these frames, not independent ID.
No decoded header length/payload or universal rule; same recording/template.
Next: validate fixed soft-boundary rule on other available frames/acquisitions
and relate boundary to candidate header lengths. soft_tail_boundary.py and
local/soft_tail_boundary.json; amplitude/sign invariance test and lint pass.

IMPORTANT CORRECTION: public yDataDec is nearest-constellation hard slicing;
modEst is per OFDM symbol. Downloaded bounded yDataSoft bins400..463 frames0..12
(3,889,047bytes, ETag checked, ignored soft-transition-0-12.npz). In six suspect
transition windows soft median|Q|=.055–.090 vs hard .171/.236; soft Q/I power
1.21–2.45%. Earlier controls median|Q|=.248–.527; later real-axis controls
.069–.112. Strong evidence apparent extra QAM imaginary signs are slicing
artifacts, not payload bits. Withdraw that interpretation for tested windows.
Real-sign continuation remains; hard-coordinate onset estimates provisional.
Next: soft amplitude-independent onset and wider soft validation, not searching
these forced imaginary signs for headers. fetch_soft_transition.py and
soft_transition_audit.py; result local/soft_transition_audit.json; report updated.

Imaginary-sign probe completed: six QAM windows, Q sign and I*Q sign; fit first
120/evaluate last120 carriers. Search3600 cyclic words/rotations and32767 PN
shifts, both polarities. None of24 tests exact evaluation. PN errors46–71/120;
cyclic23–63/120. Strongest frame10 Q97/120 scarcely exceeds predicting Q=I
(96/120); I*Q cyclic candidate is constant,80% agreement equals marginal
baseline. No new sequence/semantic decode. qam_imaginary_probe.py plus ignored
local/qam_imaginary_probe.json; evaluation-isolation test/lint pass. Next:
characterize QAM labels/magnitude classes rather than assume imaginary signs
are a clean second cyclic word or the existing PN scrambler.

Backward QAM trace: frames 4/10 show 239/240 tail-sign agreement already at end
of penultimate QAM symbol and ~99.9% across last full QAM symbol. Earlier
sampled symbols approximately chance. Imaginary sign lag60 agreement is only
48–63% in last-symbol windows; not the same exact repetition. Magnitude-only
240-carrier onset windows (two outliers, tolerance .01) give residues59,57,59,58
for frames1,4,10,11; frames5/9 have no qualifying window. Zero-outlier boundaries
unstable (6,0,40,13); no validated reset. Script/result tail_transition_audit
extended with four-symbol traces and magnitude diagnostics. Next test varying
imaginary signs against rotations/scrambler with separate discovery/evaluation.

Tail exceptions investigated: all five outlying axis boundaries are within six
carriers of symbol start; seven residue-zero transitions are inside symbols.
Projecting the later tail phase/polarity backward WITHOUT refitting into the
last 240 carriers of the preceding QAM symbol matches 239/240 in frames 1,4,10;
231/240 in 5; 185/240 in 9; near-zero frame 11 matches 240/240. Marginal
agreement baselines are 50–61%, so high agreement is not just sign imbalance.
Axis transition is not necessarily sequence onset. No universal reset or
semantic field established. Script tail_transition_audit.py; ignored result
local/tail_transition_audit.json; detailed table FULL_FRAME_REGIONS.md. Next:
trace QAM sign pattern backward and examine other constellation decision bits.

Phase-independent tail boundary: `tail_axis_boundary.py` uses only +/-1 axis
membership, then joins phase afterward. Zero-error 240-carrier windows yield
residues 0,50,0,0,18,33,0,0,0,13,9,59,0: seven exact zero, one at 59,
five exceptions. Supports investigating a reset relation without the previous
direct sequence-selection circularity; same recording/template, exploratory,
no semantic decode. Error allowances 1/2 also saved with source hashes in
local/tail_axis_boundary.json. Two focused tests pass. Next: inspect exceptions
and evaluate the fixed rule on other frames; DS7+DS8+DS9 authorized for existing
recording analysis, no new RF collection.

Exploratory tailonset/phase: first240carrier window with>=238matches around
coarseonset, phase fitted5symbols later. (boundary+phase)%60 residues
58,47,58,56,16,31,58,57,58,11,3,57,58. 8/13in56..58,5not.
Boundary depends on phase; groupingposthoc, partlycircular, no validatedreset
or semanticdecode. Need independentboundary. local/tail_boundary_phase.json,
method FULL_FRAME_REGIONS.md. All existingdata, noRFcollection.

60state algebra result: currentdictionaryall60states; differencesBk^B0 rank59,
seedrotationsrank60, gcd(seedpoly,x60+1)=1. Onlyindependentlinearconstraint
is evenparity. Not59informationbits (only60words). Rulesout fixedaffine6input
encoding or fixedprojection of32variableinput linearcodeword; changingmasks,
positions, encoderstate, multiplewords/nonlinearphase selection notexcluded.
phase_rank.py/local/phase_rank.json;2tests/lintpass. NoRFsemanticdecode.

Publicencoder-source refresh: officialRaineri thesisrecord38704confidential,
no fulltext; excluded as actionable publicimplementation. Quarkslab publication
explicitly says lowlevelPHY/LMAC processes cannot run in hardware-incomplete
emulator. OriginalJuly2026communityquestion asks sameunknownpolynomials/mapping,
not verifieddecoder. Catalogued withlinks in firmware-leads.md. No newRFdecode
or independentencoderdefinition obtained; avoid interpreting genericemulation
or community LTE guesses as a recovered RFchain.

Region-matched symbols8–9probe: discoverypairs(0,2),(3,6); reserved evaluation
(8,9),(10,11);12unused. All21384configs perlayout support-qualified;0exact
discovery in interleaved or separateblocks. NoRFdecode. extended_header_probe.py
and local/extended_header_probe.json;1focusedtest/lint pass. Later10–24lack
eighteligibleframes for this same split. Differentmapping/scrambling/noise remain.

Early-extension vocabulary audit:46early symbols beyond7,0exact matches to
known60state model; medianheld-frequency disagreement49.70%. Common2..7:
78symbols0exact,49.25%held disagreement. Tailcontrols2perframe:14/26exactboth,
median0%. Phase/polarity selected only lowerfrequencyhalf. Extraearly region
is distinct from this known model and remains meaningful nextdecodingtarget;
not provenGMH. region_phase_audit.py/local/region_phase_audit.json;1test/lintpass.

Full-frame reference map:13frames x300data symbols. >95%template-relative
+/-1membership gives early intervals ending7..24 and late intervals starting
13..151, all ending301. Details FULL_FRAME_REGIONS.md/local/frame_binary_map.json.
Prior parity assays onlycommon2..7; fixed-symbol frame comparisons can mix
region types beyondthat. Additionalearly regions require variable-boundary
alignment and separation from known cyclic tails. Onefocusedtest/lint pass.

Literal60-bit seed firmware search completed:10extracted executables,
35450176bytes,240rotation/reversal/complement patterns; packedMSB/LSB at all
bitoffsets plus uint8/uint32LE/uint32BE0/1 arrays. Zero matches. Twofocusedtests
and lint pass. firmware_seed_search.py / local/firmware_seed_search.json.
Does not exclude generated/instructionencoded/hardware or otherrepresentation
sequences; no phase-state meaning recovered.

114-bit symbol-boundary check completed: boundaries2–3through6–7,113starts
each,2orders/2directions. 6541interleaved/6099block qualified configurations;
interleaved275exactdiscovery,0exacteval;block0discovery. NoRFdecode.
Sixfocusedtests/lint pass. Results blind_header_114_activity_0_parity_window_crossing.json
and stream_blocks variant. Time forward, frequency direction varied per symbol;
not firmware-confirmed serialization. Noise/mask/selection limitations remain.

Near-match bias audit: bestpost-hoc evaluation two-bit check has184(0,0),
0(0,1),5(1,0),3(1,1) across192windows. Agreement97.3958%, marginal baseline
94.4010%, excess2.9948pp. Shiftcontrols mostly94.2708%, shift31=96.3542%.
Some alignment, but sparse selected evidence cannot identify encoder or BER.
Twofocusedtests pass; artifact local/parity_bias_audit.json. NoRFdecode.

Parity-window quality implemented: >=30qualified windows total, >=8perpair;
evaluation requires variable selected columns. 56338interleaved/55760block
configurations tested. Interleaved1684exactdiscovery checks, noneexacteval;
blocks0. Post-hoc maxeval.947917 is two-bit lowactivity relation (187/192),
not encoder; best3+bit.90625. Fivefocusedtests/lint pass. Results
blind_header_114_activity_0_parity_window.json and stream_blocks variant.
Much wider coverage, still no verified RFdecode; nearchecks require error-aware
full-code consistency rather than interpreting isolated selected relations.

Parity coverage audit:19256/21384candidate windows rejected by all-bits quality
gate (90.05%). Rare-change threshold0 leaves1724windows/5172pair configurations
perlayout; interleaved gives12two-bit exactdiscovery relations in overlapping
symbol4region, all fall to evaluation correlation.458333; blocks gives0.
No encoder supported. Fourtests/lint pass. Results blind_header_114_activity_0.json
and blind_header_114_stream_blocks_activity_0.json. Next: qualify individual
parity windows with minimum support instead of whole114bit-window gate.

DS7+DS8+DS9 manifest audit:258 distinct sessions/source manifests,85at10MS/s
(19DS7+13DS8+53DS9), none wider than10MHz. Ideal instantaneous carrier-center
bound43 before pilots/filter edges; contiguous114-BPSK-carrier word spans at
least26.484375MHz. Existing edge helper extracts24data carriers. DS pool is
useful for fragment/repetition validation, not automatically full-word decoding
or combining different passes. Raw availability/quality not checked here.
See DS789_HEADER_COVERAGE.md and local/ds789_header_coverage.json.

Separate-stream114 hypothesis tested: --layout stream_blocks treats each word
as3x38-bit encoder-output blocks before paired seven-tap checks. 5,010 eligible
configurations, no exact discovery relation. Synthetic positive control
distinguishes correct block permutation from wrong interleaving;3tests/lint pass.
Result local/blind_header_114_stream_blocks.json. Layout not firmware-confirmed;
noise/activity/fixed-mask limitations remain. No additional RF bits decoded.

Complete RX parser0xc6240 now emulated for300 synthetic short/long headers
with actual callees, featurequeryfalse. Prefix, first MCS/count, computed skip,
remaining payload all match. Declared long length60 also passes when different
from computed skip; arbitrary MCS IDs accepted without lookup on this path.
Thus parser success is weak evidence, not RF validation. Evidence
local/firmware/gmh-parser-verification.json. Feature-enabled fulltable branch
still untested end-to-end. Need code/re-encoding and independent mapping support.

TX/RX MCS-entry cross-check: helper tx0xc0f60 resolves widths8/12 through
relocation0x16fa48->0x11f258. Writes8-bit MCS then8/12-bit count (16/20total).
400 actual TX helper/RX initializer+reader cases pass, including crossings and
oversized-count truncation. Pending TX cache is reconstructed explicitly for
transfer; no full flush/parser/FEC path claimed. Evidence
local/firmware/mcs-entry-verification.json. Counts are N_CWs per RX diagnostics,
not satellite metadata. Next: full-header roundtrip and upstream flag meanings.

GMH padding verified: tx routine0xc1ac0 queried bits, adds zeros to align
(bits+8), appends8 zeros, then returns byte count. Caller0xc1294 supplies8;
non-signaling alignment32 bits. 768 emulated cases modes0/1/2 lengths0..255
include real writer word crossings and preserve inputs. Caller loads returned
bytes at0xc12bc and masks6bits at0xc1374 for long prefix: length unit is bytes
on this path. No proof the zero trailer survives later hardware processing.
Evidence local/firmware/gmh-padding-verification.json. Next: MCS entry writer
and upstream field validity/meaning, then RF candidate constraints.

TX header packing verified: tx_lmac 0xc1368..0xc13e0 creates short8/long16
prefixes; bit0/1=0 in non-signaling path, bit2=input flag, bit3=long flag,
bits4..5=unresolved inputs. Short bits6..7=count; long bits6..11=length,
bits12..15=count, consistent with RX diagnostic labels. 400 isolated emulated
cases match; actual writer0xe1430 confirms LSB-first cached placement. Results
local/firmware/gmh-prefix-verification.json. No full builder/FEC/RF roundtrip.
Next: trace remaining input meanings and appended codeword/MCS table writing.

Generator-independent 114-bit check: blind_header_114.py uses GF(2) elimination
on all seven-tap paired-stream relations at eligible within-symbol starts.
5,010 configurations, no exact discovery relation, hence none to evaluate.
Two tests pass with alternate synthetic generators, unseen words, corruption,
random and constant controls. Still restricted to direct serialization,
fixed-mask cancellation and activity-qualified columns; not exclusion of coding.
Next useful work is firmware placement/interleaving or header generation, not
another permutation of the same three guessed generators.

Downlink applicability progress: scheduler 0x92734 supplies ID0 to 0xe9ca0;
failure assertion names mcs_table_mcs_query_dl(MAC_GMH_MCS,...). Success uses
helper0x90020, which counts codewords by record+8 and accumulates symbols with
record+4 (0x90118–0x90134): 114 symbols per complete 32-bit unit. DL root is
0x1b1d90, distinct from 0x1afbe8 used by 0xe8520 and an UL consumer. All three
source-table selectors observed initializing DL have identical ID0 records.
This strengthens relevance of 114, but does not identify the encoder or prove
one unit spans the whole observed header. Evidence downlink-gmh-mcs-path.txt.

114-bit RF probe completed: 10,020 eligible within-symbol combinations with
assumed octal 133/171/165 generators, all stream permutations and both carrier
orders/directions. No exact discovery relation; selected error .413194 becomes
.513889 on separate evaluation frames. No supported decoder. Necessary parity
checks only, not termination-state validation. Result local/moving_header_code_114.json.
Three focused tests and lint pass. User explicitly directs future recording
work to use DS7+DS8+DS9; DS9 manifest located at
reports/2026_09_28_ds9_post_ds8/manifest.json (105 admitted recordings).
Next firmware work should constrain generator/interleaver/header-mode selection;
do not mistake this negative result for rejecting all 114-symbol encodings.

Packed-MCS progress: diagnostic branches identify MAC +4 as symbols/codeword
and +8 as bits/codeword. For all nonzero IDs, PHY second word gives candidate
N=64*(W&511), m=1+((W>>14)&7), K=8*((W>>17)&16383): ceil(N/m)=MAC+4,
K=MAC+8, bit31=even symbol count. Bits9..13 consistently index K/N ratios.
Entry0 in all three MAC source tables is 32 bits/114 symbols, compatible with
(32+6)*3 convolutional encoding. This is not validated RF decoding; next useful
test is a 114-bit terminated-code hypothesis, with applicability/order/scrambler
still unresolved. PHY entry0 duplicates68 and is not its coding definition.

Resolved PHY modcod source to constant 0xaeba0. Actual loader emulation verifies
all 8192 modeled-memory writes. There are 256 word-pairs, 132 unique; entries
133–255 and 68 repeat entry 0. MAC source tables at rx_lmac 0x12fb88/0x12f328
each contain IDs 0–132, supplying the GMH MCS lookup. For all 132 nonzero IDs
in both tables, PHY first word = ceil(MAC record field at +4 / 2) - 1.
Evidence: local/firmware/phy-modcod-table.json and verify_modcod_table.py.
Next: interpret the second packed word and MAC field units. No new RF semantic
fields decoded; ID 0 is a numerical exception, not a validated header mode.

PHY configuration progress: identified `init_modcod_table` at phyfw 0x5edf0
and `init_cgm_table` at 0x5ee40 through assertion-checked calls. Extracted two
256-word constants at 0xaf3a0/0xaf7a0; field meanings unverified. The 512-word
modcod source is loaded through object member 0x2d0 and written pair-swapped,
repeated sixteen times. Next: trace that member's producer, rather than infer
coding parameters from table names. No additional RF fields decoded yet.

Resolved indirect receive call: initialization uses factory 0xbe660 and vtable
0x188aa0; relocation 0x188ab0 resolves the method to 0xbe5b0. The seven-instruction
method reads a 32-bit register value through two pointers. 100 isolated emulated
cases verified exact memory reads and return values. Helper 0xfe6b0/0xfdc60 then
translates that value to a descriptor address. No FEC/descrambling is performed
in this immediate receive-method path. Next target: upstream hardware settings
or firmware blobs rather than treating this method as a software radio decoder.

Receive-path follow-up: routine 0x27100 obtains a descriptor through 0x63f50,
copies its first 16 bytes via verified memcpy PLT entry 0x21e70, then extracts
a separate payload pointer at descriptor offset 0x10 and wraps it for MAC.
Descriptor flag bytes are local interface metadata, not verified air-header
fields. Next target: resolve the virtual-method call at 0x63fb8 and its object
construction. This is static flow evidence, not an end-to-end RF decode.

Bit-reader follow-up: actual initialization, reading, and position-query routines
passed 11,064 reads over 200 byte buffers, including 5,255 word crossings.
Software-interface byte order is little-endian/LSB-first; RF bit order is still
unknown. The direct GMH caller at 0x313fc uses this same initialized reader.
See the firmware-header-analysis follow-up; the next unresolved link is the
PDU buffer's PHY/hardware origin, not the cached-word reader behavior.

Latest code analysis: receive-MAC function 0xc6240 has short/long/signaling
header paths and a conditional table-reading path with 20-bit entries split
into 8-bit MCS and 12-bit codeword-count values according to adjacent diagnostics.
The bit reader at 0xeada0 passed 100 isolated ARM64 emulation cases for its
non-crossing cached-word extraction path. This is downstream MAC evidence,
not yet RF field decoding. Details and limitations:
[firmware header analysis](../../docs/research/starlink-literature/firmware-header-analysis.md).

Firmware acquisition obstacle resolved: the public APKCombo app bundle was
downloaded and both embedded dish bundles parsed. Actual AArch64 `phyfw`,
`rx_lmac`, and `tx_lmac` binaries are now available under ignored
`docs/research/starlink-literature/local/firmware/catson-bin--*`. See the
[updated provenance and extraction findings](../../docs/research/starlink-literature/firmware-leads.md).
This supersedes the APK acquisition status below. No firmware-derived on-air
header interpretation has yet been verified. Next: static code-path analysis.

Latest local progress: [short-header probes](SHORT_HEADER_PARITY.md) tested
frequency prefixes with inferred parity masks and arbitrary within-symbol starts
with an assumed 133/171/165 convolutional code. Neither supplied a validated
decoder; the latter's discovery-selected candidate had 46.7% evaluation syndrome
errors. Public firmware inspection obtained a Linux partition but found no PHY
or lower-MAC runtime binaries. APK bundle acquisition remains unresolved.
These are completed bounded investigations, not running jobs or proof that a
known header is required. The full semantic-decoding objective remains incomplete.

Update 2026-09-28: the user requires public online sources only. The historical
reference request and blocker audits below are superseded as a work dependency:
a known header would help validation but is not a prerequisite for further work.
A public APK teardown reports embedded dish firmware bundles, providing a new
static-analysis lead. See [firmware source review](../../docs/research/starlink-literature/firmware-leads.md).
Acquisition, binary contents, and relevance to the radio header remain unverified.

The objective remains to decode and understand the additional header and short
tail regions. It is not complete. This checkpoint follows the 21-test analysis
suite and the expanded 20-frame full-band sample (seven raw-IQ-derived frames
and thirteen published hard-symbol frames).

Validated evidence includes the 60-state tail alphabet, pilot-referenced header
signs, matching sampled published decisions, and the observable low-phase LFSR.
The exact high-plane template representation does not uniquely identify the
transmitter descrambler. Counter, copy, and short-parity models have not provided
verified fields or an error-corrected header. Strong receiver agreement alone
also admits short-window discrepancies.

The current bottleneck is a discriminating header reference: a known transmitted
header paired with its symbols, a concrete encoder/interleaver definition, or
an implementation that supplies an independently checkable test vector. A user
question requesting an existing reference is pending. No new RF collection is
authorized or planned.

Blocker audit 2: rechecked the checkpoint, latest result files and literature
notes on the next goal continuation. No new labelled header, encoder/interleaver
definition or decoder reference is available, and no analysis process remains
pending. The reference question has not been answered. This turn supplies no
new decoding evidence; the same semantic-validation bottleneck remains. Keep
the goal active for now; neither completion nor the three-turn blocked threshold
has been established.

Blocker audit 3: the next continuation revalidated the checkpoint and unchanged
result files. No reference response or new discriminating evidence is available.
The same missing semantic-validation reference has persisted for three consecutive
audits. Mark the goal blocked, not complete. Resume when a known header test
vector, concrete coding/layout definition, or independently checkable decoder
becomes available. The published report and local datasets preserve the work.

Do not count another parameter sweep on the same inspected frames as independent
confirmation. To resume with a new hypothesis, state what evidence distinguishes
it from the existing alternatives, fit on discovery material only, and verify
an actual field or coding constraint on unused observations. More unlabelled
frames can improve statistics but do not by themselves resolve an arbitrary
fixed-mask/unknown-data ambiguity.
