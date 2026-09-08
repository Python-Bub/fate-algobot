import unittest

from self_modify.change_validator import validate_param_changes, validate_live_metrics


class TestPolicyGuardrails(unittest.TestCase):
    def test_param_validation_accepts_bounded(self):
        v = validate_param_changes({"BUY_THRESHOLD": 0.61, "ORDER_NOTIONAL": 400})
        self.assertIn("BUY_THRESHOLD", v.accepted)
        self.assertIn("ORDER_NOTIONAL", v.accepted)

    def test_param_validation_rejects_out_of_bounds(self):
        v = validate_param_changes({"BUY_THRESHOLD": 1.0})
        self.assertIn("BUY_THRESHOLD", v.rejected)

    def test_live_metric_reject(self):
        v = validate_live_metrics({"drawdown": -0.2, "hit_rate": 0.5, "sharpe_proxy": 0.2})
        self.assertFalse(v.ok)


if __name__ == "__main__":
    unittest.main()

