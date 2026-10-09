# Iteration84 RUNNING; iteration83 safely checkpointed

## Completed DS16 checkpoint (full experiment still running)

At64/148 completed, all63 DS16 members have results, DS17 has1/51 and DS18
has0/34. Both worker PIDs4121459/4121460 were confirmed live. All1375 frozen
source/input hashes match. No input or raw qualification failures in these64
members. Fresh uniform-control objectives reproduce the archived controls.

DS16 fitted-c: uniform0.5 mean0.979007km versus protected0.25 mean0.986470km;
25 improved/37 regressed/1 tied. Median0.834879->0.880849, p952.088464->2.201473,
worst3.204798->3.078813km. Frequency RMS67.065771->67.254591Hz, separately.
c0 mean1.321051->1.323053km;22 improved/40 regressed/1 tied; worst4.263626->4.206167.
The motivating DS16-051 improves3.204798->3.078813km, but this does not establish
broad benefit: DS16-004 regresses0.204099->0.420833km and DS16-050 regresses
2.245629->2.450794km. No per-case prior selection or policy change is made.
Full148 conclusions remain pending. After both84shards terminate, publish complete
comparison and resume83's immutable checkpoint. Do not launch extra fit workers.

## Current execution

83runnerexec29748 and40811 both TERMINAL exit0 at3-invocation bound; parents
4105802/4105803 and latestchildren4115659/4115664 confirmedgone. No83jobslive.
second-checkpoint.json in83pins577 result/region/census/attemptfiles,460clockfits.
All136first-checkpointhashes stillmatch. Both83and84sourceclosuresverified before84launch.
83unfinished; resume its same frozen shards after84comparison. Do notdiscardpartialfits.

ONLY LIVE numerical workers now84:
- shard0 exec43900, PythonPID4121459 (sudo4121437).
- shard1 exec81101, PythonPID4121460 (sudo4121438).
Both confirmedactive; firstDS16-001/002/003/004 complete,20attemptreceipts atcheck.
Every completedmember passed archived0.5objective anduniformwrappergradient
reconstruction beforefits. No inputfailures atthatcheck. Do notrestartlivethreads
on observationtimeouts, alterfrozennumericalcode, orlaunch83concurrently.

After84finishes, verifyall148statuses/bothworkertermination, regenerate report,
inspectplots, verifycontrolreproduction andpublish fullcomparison+receipts+integrity.
Then resume83checkpointedrecovery; its full148candidatecomparison remainsincomplete.
No productionchange, reserveoutcomeaccess ornewRF. Overallgoalactiveunachieved.

## Historical preparation record

Numerical freeze3b46e0928,1375 source/input hashes verified unchanged after adding
reporting code. All148 existing members,592 fits: uniform0.5 and protected0.25,
both c arms, same archived upstream seeds/clocks/banks/observations/budgets.
The new prior protects at most2position-confounded slope modes at the shared
hypothesis seed; no referenceposition or per-scan errorchoice. Fixedarchived0.5
fallback on independentqualificationfailure. Inputsfailed remainunavailable.

Runtime beforefittingeachcase reconstructs archived0.5scores within1e-6 and uniform
wrapper score/core/nuisancegradients against originalmodel within1e-10. Geometry
projector frozenbeforebotharms. Matched90s600 andc0 staticc/RFtimelocks.

Thirteen syntheticmodel/algebra/reporttests passed with PYTHONPATH=src:.
No optimizer called and no realrecording/reserveoutcome evaluated by84 yet.
Reporter smoke all148pending, no fabricatedfullmeans. It includes subgroups,
pairedregressions, rawfailures/fallbackstages, separateRMS, geometryranks andcontrol
reproductionaudit. GeneratedRESULTS/summary/comparison are untrackedsmokeoutputs;
regenerate afterrealresults beforepublishing. Preservefrozennumericalfiles.

Onlylive numericalexperiment83 (doNOToverlap84):
- shard0 runnerexec29748/PID4105802; latestchild4110873.
- shard1 runnerexec40811/PID4105803; latestchild4110896.
Runnerparents confirmedlive13:42elapsed; bothchildren~99%CPU. Initialchildren
4105804/4105805 exitedsuccessfully and serialrunner automatically resumed. At most
3invocations perrunner; parentcanremainlivebetweenchildprocesses. Waitforrunner
terminalstate, notjustachildexit. Originalfirstexec14971/36097 terminal0.
83stillfirsttwoDS16cases, nofinaltriggeredmemberselection yet; full148mean withheld.
Frozen83numericalprotocol3bf2877ef andrunner23957c223, report39512ad30.

After83runnerboundterminates, worker slots become available. Can schedule84's
boundedfull148comparison while retaining83immutablecheckpoints forlatercontinuation;
keepoverallgoalactive. Do not modify83or84frozen numericalsources to interleave.
No productionchange ornewRF. Latestcompletefull148researchmean82 is1.317354fitted
/1.666471zero;83control65 is1.360148/1.738896. Below1km goalunachieved. Never splice
singlecase81 .815491fitted/.889093zero rescue into cohortresults.
