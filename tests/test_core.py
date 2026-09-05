from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxes.coverage import build_report, should_stop  # noqa: E402
from boxes.evidence import Evidence  # noqa: E402
from boxes.ontology import Objective, _clean_departments  # noqa: E402
from boxes.qa import answer  # noqa: E402


class EvidenceTrustTests(unittest.TestCase):
    def test_government_source_is_primary_and_inspectable(self) -> None:
        item = Evidence(
            text="A sufficiently long primary-source passage " * 8,
            url="https://history.nasa.gov/example",
            title="NASA historical record",
            publish_date="1958-07-29",
        )
        self.assertEqual(item.source_tier, "primary")
        self.assertGreaterEqual(item.quality_score, 0.85)

    def test_director_upload_keeps_explicit_tier(self) -> None:
        item = Evidence(text="reference", url="", source_domain="director")
        self.assertEqual(item.source_tier, "director")


class CoverageTests(unittest.TestCase):
    @patch("boxes.coverage.embed_texts", return_value=[[1.0, 0.0]])
    def test_quality_contributes_to_research_completeness(self, _embed) -> None:
        objective = Objective("obj01", "WORLD", "The world")
        evidence = [Evidence(
            text=("archival evidence " * 20) + str(i),
            url=f"https://archive{i}.gov/item",
            title=f"Record {i}", publish_date="1958", objective_id="obj01",
        ) for i in range(8)]
        vectors = np.asarray([[1.0, 0.0] for _ in evidence], dtype=np.float32)
        report = build_report([objective], evidence, vectors)
        self.assertGreater(report.per_objective[0].quality, 0.8)
        self.assertGreater(report.overall_coverage, 0.8)
        stopped, reason = should_stop(report, 0.5, rounds_done=1, max_rounds=2)
        self.assertTrue(stopped)
        self.assertIn("completeness", reason)


class GroundedAnswerTests(unittest.TestCase):
    @patch("boxes.qa.llm.generate_json")
    def test_only_valid_citations_are_returned(self, generate) -> None:
        generate.return_value = {
            "answer": "The archive supports the date. [S1]",
            "sufficient": True,
            "cited_sources": [1, 1, 99, "bad"],
        }
        result = answer("When?", [{"title": "Record", "text": "1958"}], [0.91])
        self.assertTrue(result["sufficient"])
        self.assertEqual(result["cited_indices"], [1])


class OntologyContractTests(unittest.TestCase):
    def test_emergent_departments_require_known_array_values(self) -> None:
        self.assertEqual(_clean_departments(["script", "sound", "unknown"]), ["script", "sound"])
        self.assertEqual(_clean_departments("script"), [])


if __name__ == "__main__":
    unittest.main()
