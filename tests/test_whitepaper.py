#!/usr/bin/env python3
"""Hardware-free evidence and generated/checked-in PDF contracts."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("whitepaper_builder", ROOT / "scripts/build_whitepaper.py")
paper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper)


class WhitepaperTests(unittest.TestCase):
    def test_reviewed_evidence_and_source_constraints(self):
        evidence = paper.load_evidence()
        source = (paper.PAPER / "synapse-whitepaper.md").read_text()
        paper.validate_source(source, evidence)
        self.assertEqual(len(evidence["headline_models"]), 4)
        self.assertFalse(evidence["mistral_research_only"]["headline_eligible"])

    def test_invalid_evidence_is_not_rendered_as_success(self):
        evidence = paper.load_evidence()
        def corrupt_local_median(data):
            row = data["headline_models"][2]
            row["accelerated_tok_s"] += 1
            row["relative_gain_percent"] = 100*(row["accelerated_tok_s"]/row["control_tok_s"] - 1)
            row["display_gain_percent"] = round(row["relative_gain_percent"])
        mutations = [
            lambda data: data.update(quality_qualified=True),
            lambda data: data.update(peer_reviewed=True),
            lambda data: data["protocol"].update(repetitions=1),
            lambda data: data["headline_models"].pop(),
            lambda data: data["headline_models"][0].update(accelerated_tok_s=0),
            lambda data: data["headline_models"][0].update(display_gain_percent=999),
            lambda data: data["headline_models"][0].update(cache_mib=0),
            lambda data: data["mistral_research_only"].update(headline_eligible=True),
            lambda data: data["mistral_research_only"].update(native_equivalence_passed=True),
            corrupt_local_median,
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            for mutate in mutations:
                changed = copy.deepcopy(evidence)
                mutate(changed)
                path.write_text(json.dumps(changed))
                with self.subTest(change=changed):
                    with self.assertRaises(ValueError):
                        paper.load_evidence(path)

    def test_unknown_directives_and_unsafe_links_fail(self):
        with self.assertRaises(ValueError):
            paper.story_from_markdown("<!-- unknown -->", paper.load_evidence(), paper.styles())
        for link in ("javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.com/file"):
            with self.subTest(link=link), self.assertRaises(ValueError):
                paper.inline("[unsafe](" + link + ")")

    def check_pdf(self, path):
        reader = PdfReader(path)
        self.assertEqual(len(reader.pages), 17)
        self.assertEqual(len(reader.outline), 15)
        self.assertIn("SYNAPSE", reader.metadata.title)
        self.assertEqual(reader.metadata.author, "SYNAPSE contributors")
        fingerprint = hashlib.sha256(
            (paper.PAPER / "synapse-whitepaper.md").read_bytes()
            + (paper.PAPER / "evidence.json").read_bytes()
            + (ROOT / "scripts/build_whitepaper.py").read_bytes()).hexdigest()
        self.assertIn(fingerprint, reader.metadata.subject)
        texts = [page.extract_text() for page in reader.pages]
        self.assertTrue(all(len(text.strip()) >= 200 for text in texts))
        text = "\n".join(texts)
        for value in ("25.69", "39.46", "25.39", "43.88", "12.67", "17.28", "45.50", "77.99",
                      "21.09", "23.96", "33.01"):
            self.assertIn(value, text)
        self.assertNotIn("33.01", texts[7])
        self.assertIn("independent native-reference equivalence fails", " ".join(text.split()))
        for private in ("/home/", "/media/", ".copilot/", "Bearer ", "--api-key", "TODO", "TBD"):
            self.assertNotIn(private, text)
        root = reader.trailer["/Root"]
        self.assertNotIn("/AcroForm", root)
        self.assertNotIn("/OpenAction", root)
        if root.get("/Names") is not None:
            names = root["/Names"].get_object()
            self.assertNotIn("/EmbeddedFiles", names)
            self.assertNotIn("/JavaScript", names)
        annotations = 0
        for page in reader.pages:
            self.assertAlmostEqual(float(page.mediabox.width), paper.WIDTH, places=2)
            self.assertAlmostEqual(float(page.mediabox.height), paper.HEIGHT, places=2)
            for annotation in page.get("/Annots", []):
                annotations += 1
                action = annotation.get_object().get("/A")
                if action is not None:
                    self.assertIn(action["/S"], ("/URI", "/GoTo"))
                    if action["/S"] == "/URI":
                        self.assertTrue(action["/URI"].startswith("https://"))
        self.assertGreaterEqual(annotations, 40)

    def test_checked_in_pdf_matches_current_sources(self):
        self.check_pdf(paper.PAPER / "synapse-whitepaper.pdf")

    def test_render_is_complete_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.pdf", Path(directory) / "second.pdf"
            paper.build(first)
            paper.build(second)
            self.check_pdf(first)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
