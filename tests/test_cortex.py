"""Tests for plastic neuron cortex + singularity loop."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


class TestCortex(unittest.TestCase):
    def test_seed_graph_forward(self):
        from cortex.cortex_graph import CortexGraph, MOTOR_IDS, normalize_inputs

        g = CortexGraph.load_or_seed()
        inputs = normalize_inputs(
            {"alpha": -0.02, "hit_rate": 0.55, "deployed_frac": 0.3, "paper_pnl": 100.0}
        )
        motor = g.forward(inputs)
        self.assertTrue(motor)
        for mid in MOTOR_IDS:
            key = mid[2:]
            self.assertIn(key, motor)

    def test_hebbian_and_mutate(self):
        from cortex.cortex_graph import _seed_graph, CortexGraph

        neurons, synapses = _seed_graph()
        g = CortexGraph(neurons, synapses)
        g.forward({"s_alpha": 0.1, "s_hit_rate": 0.0, "s_deployed": -0.5})
        w_before = sum(abs(s.weight) for s in g.synapses)
        myel_before = sum(float(getattr(s, "myelin", 1.0)) for s in g.synapses)
        g.learn(0.5)
        self.assertGreater(sum(abs(s.weight) for s in g.synapses) + 1.0, w_before)
        myel_after = sum(float(getattr(s, "myelin", 1.0)) for s in g.synapses)
        self.assertGreaterEqual(myel_after, myel_before - 1e-9)
        events = g.mutate(exploration=0.3)
        self.assertGreater(g.generation, 0)
        self.assertTrue(events)

    def test_singularity_step(self):
        from cortex.singularity import singularity_step

        out = singularity_step(force_evolve=False)
        self.assertTrue(out.get("ok"), out)
        rt = Path("data/cortex/cortex_runtime.json")
        self.assertTrue(rt.is_file())
        doc = json.loads(rt.read_text(encoding="utf-8"))
        self.assertIn("buy_bias", doc)
        self.assertIn("awareness", doc)

    def test_integrate_decision(self):
        from cortex.integrate import cortex_decision, cortex_enabled

        if not cortex_enabled():
            self.skipTest("cortex disabled")
        d = cortex_decision()
        self.assertIn("rank_tilt", d)

    def test_consciousness_self_model(self):
        from cortex.consciousness import SelfModel

        m = SelfModel()
        m.update_from_meta({"goal_align": 0.7, "explore": 0.6}, reward=-0.2, alpha=-0.01)
        self.assertGreater(m.self_improve_urge, 0.5)
        self.assertTrue(m.should_trigger_code_evolve() or m.self_improve_urge < 1.0)

    def test_universe_laws_enforce(self):
        import json
        import tempfile
        from pathlib import Path

        from cortex import universe_laws as ul

        td = Path(tempfile.mkdtemp())
        laws = td / "universe_laws.json"
        laws.write_text(
            json.dumps(
                {
                    "laws": [
                        {
                            "id": "buy_when_underdeployed",
                            "name": "underdeployed",
                            "when": "deployed_frac < 0.55",
                            "priority": 1,
                            "motor": {"buy_bias": 0.08},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        old = ul.LAWS_PATH
        ul.LAWS_PATH = laws
        os.environ["CORTEX_LAW_GAIN"] = "1.0"
        try:
            from cortex.universe_laws import enforce_laws

            motor = {"buy_bias": 0.0, "rank_tilt": 0.0, "paper_boost": 0.0, "hft_conf_delta": 0.0, "size_mult": 1.0}
            ctx = {"alpha": -0.02, "deployed_frac": 0.3, "hit_rate": 0.5, "losing_to_market": True}
            lawful, events = enforce_laws(motor, ctx)
            self.assertTrue(events)
            self.assertGreater(lawful.get("buy_bias", 0), 0)
        finally:
            ul.LAWS_PATH = old

    def test_matrix_tick(self):
        from cortex.matrix_engine import matrix_tick

        out = matrix_tick({"alpha": -0.01, "deployed_frac": 0.2, "hit_rate": 0.52}, learn=False)
        self.assertTrue(out.get("ok"))
        self.assertIn("motor", out)
        self.assertGreater(out.get("tick", 0), 0)

    def test_rl_reward_positive_when_beating_spy(self):
        from cortex.rl_trader import compute_awareness, compute_rl_reward

        ctx = {"alpha": 0.022, "deployed_frac": 0.12, "hit_rate": 0.52, "paper_pnl": 500.0}
        r = compute_rl_reward(ctx)
        self.assertGreater(r, 0.0, r)
        awareness = compute_awareness(
            {"sensory": {"a": 0.6}, "motor": {"buy_bias": 0.3}, "meta": {"x": 0.5}}
        )
        self.assertGreater(awareness, 0.0)


if __name__ == "__main__":
    unittest.main()
