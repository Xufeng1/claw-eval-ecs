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
        self.assertNotIn("report", d)
        self.assertIn("details", d)
        self.assertIn("judge_details", d)
        self.assertIn("metadata", d)

    def test_to_dict_flattens_report(self):
        r = EveResult(
            score=50.0,
            report={
                "total_instances": 300,
                "resolved_instances": 171,
                "trials_per_task": 3,
                "metrics": {
                    "pass_at_k": 171,
                    "pass_hat_k": 103,
                    "avg_score": 0.546,
                },
                "resource_usage": {
                    "total_tokens": 999,
                    "model_input_tokens": 600,
                },
            },
        )
        d = r.to_dict()
        self.assertNotIn("report", d)
        self.assertEqual(d["total_instances"], 300)
        self.assertEqual(d["resolved_instances"], 171)
        self.assertEqual(d["trials_per_task"], 3)
        self.assertEqual(d["metrics_pass_at_k"], 171)
        self.assertEqual(d["metrics_pass_hat_k"], 103)
        self.assertEqual(d["metrics_avg_score"], 0.546)
        self.assertEqual(d["resource_usage_total_tokens"], 999)
        self.assertEqual(d["resource_usage_model_input_tokens"], 600)
        self.assertEqual(d["score"], 50.0)


class TestEveResultError(unittest.TestCase):
    def test_error_factory(self):
        r = EveResult.error("something broke")
        self.assertEqual(r.score, 0.0)
        self.assertEqual(r.report["error"], "something broke")
        self.assertEqual(r.report["total_instances"], 0)
        self.assertEqual(r.report["resolved_instances"], 0)
        self.assertEqual(r.metadata["status"], "failed")
        self.assertIn("timestamp", r.metadata)

    def test_error_factory_to_dict(self):
        r = EveResult.error("something broke")
        d = r.to_dict()
        self.assertNotIn("report", d)
        self.assertEqual(d["error"], "something broke")
        self.assertEqual(d["total_instances"], 0)
        self.assertEqual(d["resolved_instances"], 0)


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
