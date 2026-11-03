import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from cohort import digest
from package_report import assets,package


class ReportPackageTests(unittest.TestCase):
    def fixture(self,root,html='<img src="plot.png"><a href="https://example.test">external</a>'):
        (root/'report.html').write_text(html);(root/'plot.png').write_bytes(b'figure bytes')
        (root/'report-receipt.json').write_text(json.dumps(dict(status='in_progress',rendered_utc='2026-10-04T00:00:00Z',
            outputs={'report.html':digest((root/'report.html').read_bytes())})))

    def test_portable_archive_preserves_draft_status_and_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            target=package(root,root/'delivery')
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.read('plot.png'),b'figure bytes')
                self.assertEqual(json.loads(archive.read('bundle-manifest.json'))['status'],'draft')
                self.assertIsNone(archive.testzip())
            with self.assertRaises(FileExistsError):package(root,root/'delivery')
            self.assertFalse(list((root/'delivery').glob('.report-*')))

    def test_missing_or_escaping_asset_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for link in ('missing.png','../outside.png','%2e%2e/outside.png'):
                self.fixture(root,f'<img src="{link}">')
                with self.assertRaises(ValueError):assets(root)

    def test_changed_html_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);(root/'report.html').write_text('<p>changed</p>')
            with self.assertRaisesRegex(ValueError,'differs'):package(root,root/'delivery')
