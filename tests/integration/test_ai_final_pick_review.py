import os
import unittest


class TestAiFinalPickReview(unittest.TestCase):
    def test_apply_blend_and_reject(self):
        from intel import ai_final_pick_review as m

        fake_json = (
            '{"reviews":['
            '{"ticker":"AAA","verdict":"approve","grade":"A","confidence":0.9,"profit_focus_score":0.95,"red_flags":[],"one_line":"ok"},'
            '{"ticker":"BBB","verdict":"reject","grade":"F","confidence":0.9,"profit_focus_score":0.1,"red_flags":["dilution"],"one_line":"bad"}'
            "]}"
        )

        def fake_post(_messages):
            return fake_json

        def fake_web(_ticker):
            return "snippet"

        m._post_chat = fake_post  # type: ignore[method-assign]
        m.build_web_context = fake_web  # type: ignore[method-assign]

        os.environ["USE_AI_FINAL_PICK_REVIEW"] = "true"
        os.environ["AI_PICK_REVIEW_WEIGHT"] = "0.5"
        os.environ["AI_PICK_REJECT_CONF"] = "0.5"

        picks = [
            {"ticker": "AAA", "p_up": 0.8, "score": 2.0, "execution_confidence": 0.7, "asym_action": "LONG"},
            {"ticker": "BBB", "p_up": 0.75, "score": 1.0, "execution_confidence": 0.65, "asym_action": "LONG"},
        ]
        out, meta = m.apply_ai_review_to_long_picks(picks, regime_name="bull", vix=18.0)
        self.assertTrue(meta.get("enabled"))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["ticker"], "AAA")
        self.assertIn("ai_blend_rank", out[0])

    def test_always_drop_f(self):
        from intel import ai_final_pick_review as m

        fake = '{"reviews":[{"ticker":"ZZZ","verdict":"approve","grade":"F","confidence":0.99,"profit_focus_score":0.95,"red_flags":[],"one_line":"trap"}]}'

        def fake_post(_messages):
            return fake

        m._post_chat = fake_post  # type: ignore[method-assign]
        m.build_web_context = lambda _t: "x"  # type: ignore[misc]

        os.environ["USE_AI_FINAL_PICK_REVIEW"] = "true"
        os.environ["AI_PICK_ALWAYS_DROP_F"] = "true"
        picks = [{"ticker": "ZZZ", "p_up": 0.9, "score": 3.0, "execution_confidence": 0.8, "asym_action": "LONG"}]
        out, meta = m.apply_ai_review_to_long_picks(picks, regime_name="bull", vix=18.0)
        self.assertTrue(meta.get("enabled"))
        self.assertEqual(len(out), 0)

    def test_fill_missing_review_row(self):
        from intel import ai_final_pick_review as m

        fake = '{"reviews":[{"ticker":"AAA","verdict":"approve","grade":"A","confidence":0.9,"profit_focus_score":0.9,"red_flags":[],"one_line":"ok"}]}'

        def fake_post(_messages):
            return fake

        m._post_chat = fake_post  # type: ignore[method-assign]
        m.build_web_context = lambda _t: "x"  # type: ignore[misc]

        os.environ["USE_AI_FINAL_PICK_REVIEW"] = "true"
        os.environ["AI_PICK_REJECT_CONF"] = "0.99"
        picks = [
            {"ticker": "AAA", "p_up": 0.8, "score": 2.0, "execution_confidence": 0.7, "asym_action": "LONG"},
            {"ticker": "BBB", "p_up": 0.7, "score": 1.5, "execution_confidence": 0.65, "asym_action": "LONG"},
        ]
        out, meta = m.apply_ai_review_to_long_picks(picks, regime_name="bull", vix=18.0)
        self.assertEqual(len(out), 2)
        by = {r["ticker"]: r for r in out}
        self.assertEqual(by["BBB"]["ai_pick_review"]["red_flags"], ["llm_omitted_ticker"])


if __name__ == "__main__":
    unittest.main()
