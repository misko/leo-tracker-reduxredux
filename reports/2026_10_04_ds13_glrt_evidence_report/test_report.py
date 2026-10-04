"""Portable scientific-accounting and standalone-document checks (no corpus)."""
import base64
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
from html.parser import HTMLParser
import io
import itertools
import json
import math
from pathlib import Path
import re
import unittest

import build_report
from render_markdown import markdown

HERE = Path(__file__).resolve().parent
ALIAS = 1 / 4.4e-6


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links, self.images, self.downloads, self.external = [], [], [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "a" and "href" in a:
            self.links.append(a["href"])
        if tag == "img":
            self.images.append(a)
        if "download" in a:
            self.downloads.append(a)
        if tag in ("script", "link", "iframe"):
            self.external.append(a)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = json.loads((HERE / "evidence/metrics.json").read_text())
        cls.rows = list(csv.DictReader(io.StringIO(gzip.decompress((HERE / "evidence/scan-A-candidates.csv.gz").read_bytes()).decode())))
        cls.lookup = {int(r["row_index"]): r for r in cls.rows}
        cls.groups = defaultdict(list)
        for row in cls.rows:
            cls.groups[row["group"]].append(row)
        cls.winners = {
            int(max(rs, key=lambda r: (float(r["refined_margin"]), -int(r["row_index"])))["row_index"])
            for rs in cls.groups.values()
        }

    def test_observation_units_and_winners(self):
        self.assertEqual(len(self.rows), 7382)
        self.assertEqual(len(self.groups), 3837)
        self.assertEqual(sum(len(v)>1 for v in self.groups.values()), 1946)
        self.assertEqual(sum(len(v)*(len(v)-1)//2 for v in self.groups.values()), 5901)
        actual = {int(r["row_index"]) for r in self.rows if int(r["top_candidate"])}
        self.assertEqual(actual, self.winners)
        for rows in self.groups.values():
            self.assertEqual(len({(r["receiver"], r["channel"], r["time_s"]) for r in rows}), 1)
        self.assertEqual(dict(Counter(map(len, self.groups.values()))), {int(k):v for k,v in self.metrics["multiplicity"].items()})
        self.assertEqual(sum(r["status"] != "refined" for r in self.rows), 5)
        self.assertEqual(sum(float(r["refined_margin"]) > float(r["original_margin"]) for r in self.rows), 6031)

    def test_pair_distributions_and_cutoffs(self):
        for cutoff, expected in [(None, build_report.load("pair-distribution"))] + [
            (r["cutoff"], r) for r in build_report.load("margin-cutoffs")["summaries"] + [build_report.load("margin-06")]
        ]:
            counts, pairs, multi, candidates = [0]*6, 0, 0, 0
            for rows in self.groups.values():
                keep = [r for r in rows if cutoff is None or float(r["refined_margin"]) >= cutoff]
                candidates += len(keep)
                multi += len(keep)>1
                for a,b in itertools.combinations(keep, 2):
                    gap = abs((float(a["refined_hz"])-float(b["refined_hz"])+ALIAS/2)%ALIAS-ALIAS/2)
                    index = sum(gap >= limit for limit in (10,50,100,300,1000))
                    counts[index] += 1
                    pairs += 1
            self.assertEqual(counts, expected["counts"])
            self.assertEqual(pairs, expected.get("pairs", expected.get("pair_count")))
            self.assertEqual(multi, expected["multi_candidate_probes"])
            if cutoff is not None:
                self.assertEqual(candidates, expected["candidates"])

    def test_detector_provenance_and_frequency_example(self):
        meta = json.loads((HERE / "evidence/detector-provenance.json").read_text())
        config = meta["scan_A_configuration"]
        self.assertEqual(config["probe_ms"],20)
        self.assertEqual(config["sample_rate_hz"],10000000)
        self.assertEqual(config["glrt64_margin_gate"],.025)
        self.assertEqual(config["maximum_acquisition_candidates"],8)
        self.assertEqual(len({tuple(r["probe_key"]) for r in meta["boundary_example"]}),1)
        for r in meta["boundary_example"]:
            self.assertAlmostEqual(r["acquired_cfo_hz"]+r["native_residual_cfo_hz"],r["tracking_cfo_hz"])
            spec = r["candidate_spec"]
            self.assertAlmostEqual(spec["fractional_exact_score"]-spec["fractional_control_score"],r["fractional_margin"])

    def test_solver_receipts_and_feasibility(self):
        for summary in self.metrics["results"]:
            d = build_report.load(summary["key"])
            for stage in ("initial", "final"):
                f = d[stage]
                aa = f["assignments"]
                self.assertEqual(len(aa), f["assigned"])
                self.assertEqual(len({a["row_index"] for a in aa}), len(aa))
                self.assertEqual(f["assigned"]+f["unassigned"], d["denominator"])
                self.assertEqual(f["objective"], f["assigned"]-10*f["satellites"])
                self.assertTrue(all(abs(a["residual_hz"]) <= 600 for a in aa))
                self.assertEqual(len({s["catalog_number"] for s in f["selected"]}), f["satellites"])
                self.assertTrue(all(abs(s["offset_s"]) <= 20 for s in f["selected"]))
                if summary["scan"] == "A":
                    self.assertEqual(len({(a["catalog_number"], self.lookup[a["row_index"]]["group"]) for a in aa}), len(aa))
                    lanes = defaultdict(list)
                    for a in aa:
                        r = self.lookup[a["row_index"]]
                        lanes[(a["catalog_number"], r["receiver"], r["channel"])].append(float(r["time_s"]))
                        if summary["stage"] == "top":
                            self.assertIn(a["row_index"], self.winners)
                    for times in lanes.values():
                        times.sort()
                        parts = [[times[0]]]
                        for t in times[1:]:
                            if t-parts[-1][-1]>5:
                                parts.append([])
                            parts[-1].append(t)
                        for part in parts:
                            self.assertGreaterEqual(len(part),10)
                            self.assertGreaterEqual(part[-1]-part[0],5)
                for s in f["selected"]:
                    errors = [a["residual_hz"] for a in aa if a["catalog_number"]==s["catalog_number"]]
                    self.assertEqual(len(errors), s["count"])
                    self.assertAlmostEqual(math.sqrt(sum(e*e for e in errors)/len(errors)), s["rms_hz"])
            rms = math.sqrt(sum(a["residual_hz"]**2 for a in d["final"]["assignments"])/d["final"]["assigned"])
            self.assertAlmostEqual(rms, summary["assigned_rms_hz"])
            self.assertEqual(d["initial"]["assigned"], d["final"]["assigned"])
            self.assertTrue(d["converged"])
            self.assertTrue(all(not t["accepted"] and t["trial_score"]<=t["before_score"] for t in d["trials"]))
            self.assertEqual(len(d["trials"]), summary["replacement_trials"])

    def test_coverage_by_lane(self):
        for arm, entries in build_report.load("top-coverage").items():
            d = build_report.load(f"A-top-{arm}")
            owners = {a["row_index"] for a in d["final"]["assignments"]}
            self.assertEqual(len(owners), 3644 if arm=="fitted-c" else 3648)
            self.assertEqual(d["denominator"], 3837)
            # The figure source may label the lane differently; numeric totals
            # are checked against the underlying candidates in display order.
            expected = [(len(owners), len(self.winners))]
            for rx in (0,1):
                for ch in (1,2,3,4):
                    ids = {i for i in self.winners if int(self.lookup[i]["receiver"])==rx and int(self.lookup[i]["channel"])==ch}
                    expected.append((len(ids & owners),len(ids)))
            self.assertEqual([(r["assigned_windows"],r["eligible_windows"]) for r in entries], expected)

    def test_portable_html_and_embedded_evidence(self):
        text = (HERE / "report.html").read_text()
        doc = Document(text)
        self.assertEqual(len(doc.ids),len(set(doc.ids)))
        self.assertEqual(len(doc.images),19)
        self.assertFalse(doc.external)
        self.assertNotIn("@@",text)
        for link in doc.links:
            self.assertTrue(link.startswith(("#","data:")))
            if link.startswith("#"):
                self.assertIn(link[1:],doc.ids)
        for img in doc.images:
            self.assertTrue(img["alt"])
            self.assertTrue(img["src"].startswith("data:image/png;base64,"))
            self.assertTrue(base64.b64decode(img["src"].split(",",1)[1]).startswith(b"\x89PNG\r\n\x1a\n"))
        for a in doc.downloads:
            name = a["download"]
            src = HERE / ("sources" if name.endswith(".py") else "evidence") / name
            self.assertEqual(base64.b64decode(a["href"].split(",",1)[1]),src.read_bytes())

    def test_evidence_hashes_and_deterministic_build(self):
        before = hashlib.sha256((HERE / "report.html").read_bytes()).hexdigest()
        before_md = (HERE / "report.md").read_bytes()
        self.assertEqual(build_report.build(),19)
        self.assertEqual(before,hashlib.sha256((HERE / "report.html").read_bytes()).hexdigest())
        self.assertEqual(before_md, (HERE / "report.md").read_bytes())

    def test_baseline_name_and_later_replay(self):
        for extension in ('html', 'md'):
            text = (HERE / f'report.{extension}').read_text()
            self.assertIn('Top-1 Absolute-Timing Baseline (T1-AT v1)', text)
            self.assertIn('t1_at_v1', text)
            self.assertIn('Historical snapshot scope.', text)
            self.assertIn('not IQ refinement, calibration, orbit discovery, or position estimation', text)
            self.assertIn('3,460 / 3,602', text)
        for arm in ('fitted-c', 'zero-c'):
            receipt = build_report.load(f'B-t1-at-v1-replay-{arm}')
            r, s = receipt['final'], receipt['summary']
            self.assertEqual(receipt['upstream_source_hashes_verified'], 35)
            self.assertTrue(s['exact_historical_stages_match'])
            self.assertEqual(r['assigned'], 3460)
            self.assertEqual(r['unassigned'], 142)
            self.assertEqual(r['satellites'], 32)
            self.assertEqual(r['objective'], 3140)
            self.assertEqual(len({a['row_index'] for a in r['assignments']}), 3460)
            self.assertAlmostEqual(s['rms_hz'], math.sqrt(sum(a['residual_hz']**2 for a in r['assignments'])/3460))
            self.assertEqual(len(receipt['trials']), 32)
            self.assertTrue(all(not t['accepted'] for t in receipt['trials']))

    def test_markdown_has_all_figures_sections_and_portable_links(self):
        text = (HERE / 'report.md').read_text()
        self.assertNotIn('data:', text)
        self.assertNotIn('@@', text)
        self.assertNotIn('<style', text)
        links = re.findall(r'\]\(([^)]+)\)', text)
        images = [p for p in links if p.startswith('assets/')]
        self.assertEqual(len(images), 19)
        self.assertEqual(len(set(images)), 19)
        for path in links:
            if path.startswith('#'):
                self.assertIn(f'id="{path[1:]}"', text)
            else:
                self.assertTrue((HERE/path).is_file(), path)
        html_doc = Document((HERE/'report.html').read_text())
        for ident in html_doc.ids:
            self.assertIn(f'id="{ident}"', text)
        self.assertIn('| --- |', text)
        self.assertIn('```text', text)
        self.assertIn('**94.97%** — 3,644', text)
        self.assertIn('**IQ → candidates** Several', text)

    def test_markdown_renderer_primitives(self):
        value = markdown('<h2 id="x">Title</h2><p><strong>Bold</strong> and <code>x</code></p>'
                         '<ul><li>One</li><li>Two</li></ul><table><tr><th>A</th><th>B</th></tr>'
                         '<tr><td>1</td><td>2</td></tr></table><pre>a\n  b</pre>')
        self.assertIn('## Title\n\n', value)
        self.assertIn('**Bold** and `x`', value)
        self.assertIn('\n\n- One\n- Two\n\n', value)
        self.assertIn('| A | B |\n| --- | --- |\n| 1 | 2 |', value)
        self.assertIn('```text\na\n  b\n```', value)


if __name__ == "__main__":
    unittest.main()
