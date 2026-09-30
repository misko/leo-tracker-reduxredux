"""Build a portable evidence review from hash-checked local receipts; no RF I/O."""

import base64
import hashlib
import html
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_entries(ledger):
    entries = ledger["associations"]
    seen, sources = set(), {}
    required = {"id", "scope", "kind", "evidence", "source", "ranked_interpretations",
                "firmware_constraint", "falsifier", "test_status"}
    for row in entries:
        if required - row.keys():
            raise ValueError("Incomplete association")
        if row["id"] in seen:
            raise ValueError("Duplicate association ID")
        seen.add(row["id"])
        if not {"path", "sha256"} <= row["source"].keys():
            raise ValueError("Missing association provenance")
    def verify(value):
        if isinstance(value, dict):
            if {"path", "sha256"} <= value.keys():
                path = Path(value["path"])
                if path not in sources:
                    sources[path] = digest(path)
                expected = value["sha256"].removeprefix("sha256:")
                if sources[path] != expected:
                    raise ValueError(f"Source hash mismatch: {path}")
            for child in value.values():
                verify(child)
        elif isinstance(value, list):
            for child in value:
                verify(child)
    verify(ledger)
    return entries, sources


def escaped(value):
    return html.escape(str(value), quote=True)


def render_entry(row):
    fields = [("Scope", row["scope"]), ("Association type", row["kind"]),
              ("Ranked interpretations", " → ".join(row["ranked_interpretations"])),
              ("Firmware constraint", row["firmware_constraint"]),
              ("Falsifiable requirement", row["falsifier"]),
              ("Test status", row["test_status"])]
    description = "".join(f"<dt>{escaped(k)}</dt><dd>{escaped(v)}</dd>" for k, v in fields)
    # Include the entire row, not just evidence: coordinates/parity can be siblings.
    payload = escaped(json.dumps(row, indent=2, ensure_ascii=False))
    return (f'<details class="entry"><summary>{escaped(row["id"])} — '
            f'{escaped(row["kind"])}</summary><dl>{description}</dl>'
            f'<details><summary>Complete evidence and provenance</summary>'
            f'<pre>{payload}</pre></details></details>')


def figure(name, caption):
    data = base64.b64encode((BASE / "local" / name).read_bytes()).decode()
    return (f'<figure><img alt="{escaped(caption)}" src="data:image/png;base64,{data}">'
            f'<figcaption>{escaped(caption)}</figcaption></figure>')


def main():
    ledger_path = BASE / "local/association-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    entries, sources = checked_entries(ledger)
    body = """<h1>Starlink firmware and symbol-association review</h1>
<p>Research checkpoint • 29 September 2026 • DS7/DS8/DS9/DS10 • No new RF collection</p>
<p><strong>We recover reproducible structure, but have not decoded a satellite
identity or mapped the extra early symbols to a message field.</strong>
Firmware execution clarifies software packing and hardware configuration;
it does not yet connect a received carrier position to a decoded header byte.</p>
<h2>Scope and evidence quality</h2>
<p>This portable report embeds every entry in the current association ledger,
including historical public-reference associations for provenance only. New
recording analyses are restricted to DS7–DS10. Entries include hypotheses,
negative results and abstentions; they are not independent discoveries. The
195-receipt catalog is broader than the completed semantic audit. This remains
an active investigation, not an exhaustive finished review.</p>
<h2>Ranked findings</h2>
<table><tr><th>Finding</th><th>Evidence</th><th>Interpretation limit</th></tr>
<tr><td>Known repeated T-code dominates many signatures</td><td>871 qualified
frame/window units retain one state within their tested windows; 399 of 428
two-frame comparisons change state.</td><td>Neither independent sample counts
nor a satellite address. Known pilots and T-code must be separated from messages.</td></tr>
<tr><td>Early real-axis structure is shared by receivers</td><td>Symbols 3/4/6:
mean correlations .410/.471/.487 over three DS10 excerpts; coupled-session
family ranks .04348. DS10 quadrature comparisons fail the corrected screen.
In DS9, middle-excerpt Q survives the same fixed I-leakage correction
(.220 to .211), while the last excerpt falls from .017 to .003.
DS9's two-excerpt corrected ranks cannot be below 2/23; this neither proves
extra bits nor supports generalizing the DS10 negative result.</td>
<td>Same-excerpt receiver covariance, not cross-visit bit correspondence.
Only one session; cyclic-reference assumptions and coarse rank resolution apply.</td></tr>
<tr><td>Frozen sign pairs do not transfer convincingly</td><td>Seven pairs,
three excerpts, 2,277 joint rotations; none of 21 pair/visit tests passes the
family correction.</td><td>No verified fixed copy/complement or FEC relation.</td></tr>
<tr><td>Satellite specificity is unsupported</td><td>The leading matched
real-sign effect loses support under trajectory controls (rank .356).
Wider carriers weaken its effect; wider-feature trajectory ranks are 1.</td>
<td>Conditional orbit labels, sparse cross-session support, time/channel confounds.
SATAddr must not be equated with NORAD.</td></tr>
<tr><td>Some dendrogram splits are fragile</td><td>94.276% of word-distribution
pair distances are maximal. Input reordering changes some cuts. Early phase
trees tolerate reordering but change when DS10 joins the corpus.</td>
<td>A stable or visually distinct branch is not a decoded enum or identity.</td></tr>
</table>
<h2>What the actual firmware changes</h2>
<p>Bounded AArch64 execution verifies LSB-first software writing and multiple
8/16-bit prefix branches. Initialization identifies mode 3 as SAT-RX, mode 4
as UT-TRX and default 5 as UNSET. These are device roles, not observed per-frame
flags. Two PHY variants use different object offsets for their CGM destinations.
Executed 20-entry and 60-entry builders make threshold masks; their consumers
and comparisons do not establish a message interleaver or T-code generator.</p>
<p>A purported sequence update is a bitmap OR, and both equality and mismatch
paths select the same value 2. A receive descriptor's metadata and payload
pointer are separate. These findings weaken attempts to label clusters directly
from software constants. FEC generators, scrambling state, codeword placement
and the RF-to-buffer mapping remain unresolved.</p>
<p>Another 72 actual receive-parser branch executions show that two prefix bits
select table parsing only under a particular feature setting and positive entry
count. Three nonzero values select the same branch. Short-form accounting uses
16 bits per entry while the table loop requests 20; runtime validity of that
combination is unproven. This is not a four-class RF field identification.</p>
<p>An uplink-associated SYSINFO format decision selects 114/228 in a resource-budget
calculation and 16/24 after codeword conversion. These distinct quantities cannot
be interchanged with entry widths 16/20 or prefix widths 8/16. The capacity
calculation was executed in 72 bounded cases. Caller/source diagnostics link this
to terminal uplink scheduling; it is not evidence of 114/228 switching in our
Ku downlink recordings. RF placement remains unknown.</p>
<p>The separate downlink accounting assay is in RX-LMAC. It carries partial bits
and accounts for 114 symbols per complete 32-bit unit, verified over 2,112 cases.
Its audited caller replenishes unused GMH capacity, with another 384 cases
checking a carry and a saturating bookkeeping counter. Neither that counter nor
the replenishment operation establishes a transmitted field or header boundary.</p>
<h2>Controls and interpretation</h2>
<p>Experiments use frozen features/coordinates, held frames or receivers,
session/channel/rate strata, circular rotations and family corrections where
support permits. Some strata allow only two permutations; those assays abstain.
Reported ranks are conditional on their reference schemes, not population
probabilities or correction across every historical experiment. Reusing formerly
held data for audit does not make it a new independent confirmation.</p>
<p>Known late-waveform error is comparable on core and extra carriers across
506 held frames. It is not early-header BER. Phase histograms discard ordering:
permuting 99.97% of sample positions in the audited example leaves its histogram
unchanged. Such features cannot locate ordered bitfields.</p>
<h2>Visual evidence</h2>"""
    for name, caption in [
        ("receiver-family.png", "Receiver correlation with joint family and session controls."),
        ("serialized-layout.png",
         "Executed SYSINFO serialization layouts; no established RF mapping."),
        ("ds9-leakage-transfer.png", "Frozen DS10 I-leakage correction transferred to DS9."),
        ("pair-transfer.png",
         "Frozen sign pairs on held RX1 frames; excess over cyclic reference."),
        ("tie-stability.png", "Dendrogram sensitivity to input reordering."),
        ("corpus-extension.png", "Partition sensitivity when DS10 observations are added."),
    ]:
        body += figure(name, caption)
    body += (f'<h2>Association ledger: {len(entries)} entries</h2>'
             '<p>Search matches complete evidence, including collapsed details. '
             'Rankings are judgments, not posterior probabilities.</p>'
             '<label>Filter <input id="query" type="search" placeholder="e.g. SATAddr, '
             'DS10, receiver, counter"></label><p id="count"></p><div id="ledger">')
    body += "".join(render_entry(row) for row in entries) + "</div>"
    body += '<h2>Shared firmware constraints and receipts</h2>'
    for key, value in ledger.items():
        if key.startswith("shared_") and isinstance(value, dict):
            body += (f'<details><summary>{escaped(key)}</summary><pre>'
                     f'{escaped(json.dumps(value, indent=2))}</pre></details>')
    body += '<h2>Remaining work and reproducibility</h2><p>'
    body += ("Complete the remaining receipt-level semantic inventory; pursue RF field "
             "tests only when an independent firmware constraint supplies a falsifiable "
             "mapping. Existing patent PN and candidate convolutional scans are not "
             "new constraints and were not repeated. No raw IQ or firmware is embedded.</p>")
    body += (f'<p>Ledger SHA256: <code>{digest(ledger_path)}</code>. '
             'Run <code>python publish_review.py</code> after the component producers '
             'and <code>association_ledger.py</code>. The build verifies every ledger '
             'source hash, including nested/shared firmware references, and rejects duplicate IDs. '
             'This checks declared references, not every undeclared dependency. Detailed tests and '
             'assay reports are in the same research directory.</p><ul>')
    for path, sha in sorted(sources.items()):
        body += f'<li><code>{escaped(path)}</code> — <code>{sha}</code></li>'
    body += "</ul>"
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Starlink firmware and symbol associations</title><style>
body{max-width:1150px;margin:3em auto;padding:0 1em;color:#182331;background:#fafafa;
font:17px/1.55 system-ui}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%}
td,th{border:1px solid #bbc6d0;padding:.65em;text-align:left;vertical-align:top}
img{max-width:100%}figure{margin:2em 0}figcaption{color:#465366}
.entry{background:white;border:1px solid #ccd4dc;margin:.6em 0;padding:.7em}
summary{cursor:pointer}dt{font-weight:bold}dd{margin:0 0 .7em}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
code{overflow-wrap:anywhere}input{font:inherit;width:min(600px,90%);padding:.4em}
[hidden]{display:none!important}</style><main>""" + body + """</main><script>
const rows=[...document.querySelectorAll('.entry')];
const query=document.getElementById('query'),count=document.getElementById('count');
const texts=rows.map(r=>r.textContent.toLowerCase());
function filter(){let n=0;const q=query.value.toLowerCase();
rows.forEach((r,i)=>{r.hidden=!texts[i].includes(q);if(!r.hidden)n++});
count.textContent=`${n} of ${rows.length} entries shown`;}
query.addEventListener('input',filter);filter();</script></html>"""
    output = BASE / "local/review.html"
    output.write_text(page)
    receipt = dict(ledger_sha256=digest(ledger_path), report_sha256=digest(output),
                   method_sha256=digest(Path(__file__)), entries=len(entries),
                   sources=[dict(path=str(p), sha256=s) for p, s in sorted(sources.items())])
    (BASE / "local/review-build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Built {output}: {len(entries)} entries, {len(sources)} checked sources")


if __name__ == "__main__":
    main()
