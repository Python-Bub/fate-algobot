import os
import unittest

from intel.llm_signal_agent import score_text_with_llm
from runtime.degradation_policy import decide_degradation
from self_modify.shadow_validator import validate_candidate_changes


class TestAIRuntimeHardening(unittest.TestCase):
    def test_llm_fallback_neutral_without_key(self):
        os.environ["USE_LLM_SIGNAL"] = "true"
        os.environ["LLM_API_KEY"] = ""
        out = score_text_with_llm("This stock is amazing and will 10x.", symbol="AAPL")
        self.assertIn("sentiment", out)
        self.assertGreaterEqual(out["sentiment"], -1.0)
        self.assertLessEqual(out["sentiment"], 1.0)

    def test_degradation_policy(self):
        h = decide_degradation(avg_score_ms=4000, error_rate=0.3, symbol_count=200)
        self.assertEqual(h.mode, "degraded_high")

    def test_shadow_validator_shape(self):
        rep = validate_candidate_changes({"BUY_THRESHOLD": 0.55, "ORDER_NOTIONAL": 600})
        self.assertIn("ok", rep)
        self.assertIn("reason", rep)


if __name__ == "__main__":
    unittest.main()

