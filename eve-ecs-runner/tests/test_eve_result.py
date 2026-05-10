import unittest
from dataclasses import asdict

from eve_ecs_runner.eve_result import EveResult, JudgeDetail


class TestEveResultDefaults(unittest.TestCase):
    def test_default_values(self):
        r = EveResult()
        self.assertEqual(r.score, 0.0)
        self.assertEqual(r.judge_ratio, 0.0)
        self.assertEqual(r.detail_oss_url, "")
        self.assertEqual(r.report, {})
        self.assertEqual(r.details, [])
        self.assertEqual(r.judge_details, [])
        self.assertEqual(r.metadata, {})

    def test_to_dict_structure(self):
        r = EveResult(score=85.0, judge_ratio=1.0, detail_oss_url="oss://bucket/results.tgz")
        d = r.to_dict()
        self.assertEqual(d["score"], 85.0)
        self.assertEqual(d["judge_ratio"], 1.0)
        self.assertEqual(d["detail_oss_url"], "oss://bucket/results.tgz")
        self.assertIn("report", d)
        self.assertIn("details", d)
        self.assertIn("judge_details", d)
        self.assertIn("metadata", d)


class TestEveResultError(unittest.TestCase):
    def test_error_factory(self):
        r = EveResult.error("something broke")
        self.assertEqual(r.score, 0.0)
        self.assertEqual(r.report["error"], "something broke")
        self.assertEqual(r.report["total_instances"], 0)
        self.assertEqual(r.report["resolved_instances"], 0)
        self.assertEqual(r.metadata["status"], "failed")
        self.assertIn("timestamp", r.metadata)


class TestJudgeDetail(unittest.TestCase):
    def test_round_trip(self):
        jd = JudgeDetail(
            idx=0,
            prompt="test prompt",
            origin_prompt="test prompt",
            origin_prompt_hash="abc123",
            origin_prediction="pred",
            processed_prediction="pred",
            reference="ref",
            correct=True,
        )
        d = asdict(jd)
        self.assertEqual(d["idx"], 0)
        self.assertEqual(d["correct"], True)
        self.assertEqual(d["is_multiturn"], False)
        self.assertIsNone(d["group_score"])
        self.assertEqual(d["ext_info"], {})


if __name__ == "__main__":
    unittest.main()
