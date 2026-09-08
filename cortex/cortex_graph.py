"""
Plastic neuron graph — sensory → association → motor + meta self-model layer.

Cross-domain inputs (market, neural ensemble, deployment, risk) flow through
synapses that strengthen/weaken via reward-modulated Hebbian plasticity.
"""

from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path
from typing import Any

from cortex.neuron import Neuron, Synapse, sigmoid

GRAPH_PATH = Path(os.getenv("CORTEX_GRAPH_PATH", "data/cortex/neuron_graph.json"))

# Sensory neuron ids (environment → cortex)
SENSORY_IDS = (
    "s_alpha",
    "s_hit_rate",
    "s_deployed",
    "s_paper_pnl",
    "s_neural_p",
    "s_rsi",
    "s_momentum",
    "s_drawdown",
    "s_hft_pulse",
)

# Association hidden layer
ASSOC_IDS = tuple(f"a_{i}" for i in range(12))

# Motor outputs (cortex → trading stack)
MOTOR_IDS = (
    "m_buy_bias",
    "m_rank_tilt",
    "m_paper_boost",
    "m_hft_conf_delta",
    "m_size_mult",
)

# Meta layer — self-model signals ("consciousness" metrics)
META_IDS = (
    "x_goal_align",
    "x_explore",
    "x_self_improve",
    "x_coherence",
)


def _seed_graph() -> tuple[dict[str, Neuron], list[Synapse]]:
    neurons: dict[str, Neuron] = {}
    for sid in SENSORY_IDS:
        neurons[sid] = Neuron(id=sid, layer="sensory", bias=0.0, act_fn="sigmoid", plasticity=0.02)
    for aid in ASSOC_IDS:
        neurons[aid] = Neuron(
            id=aid,
            layer="association",
            bias=random.uniform(-0.1, 0.1),
            act_fn="tanh",
            plasticity=0.08,
        )
    for mid in MOTOR_IDS:
        neurons[mid] = Neuron(
            id=mid,
            layer="motor",
            bias=random.uniform(-0.05, 0.05),
            act_fn="tanh",
            plasticity=0.10,
        )
    for xid in META_IDS:
        neurons[xid] = Neuron(
            id=xid,
            layer="meta",
            bias=random.uniform(-0.05, 0.05),
            act_fn="sigmoid",
            plasticity=0.06,
        )

    synapses: list[Synapse] = []
    rng = random.Random(42)

    def connect(src: str, tgt: str, w: float | None = None) -> None:
        synapses.append(Synapse(source=src, target=tgt, weight=w if w is not None else rng.uniform(-0.3, 0.3)))

    for sid in SENSORY_IDS:
        for aid in rng.sample(ASSOC_IDS, k=5):
            connect(sid, aid)
    for aid in ASSOC_IDS:
        for mid in MOTOR_IDS:
            if rng.random() < 0.7:
                connect(aid, mid)
        for xid in META_IDS:
            if rng.random() < 0.5:
                connect(aid, xid)
    for xid in META_IDS:
        for mid in MOTOR_IDS:
            if rng.random() < 0.4:
                connect(xid, mid, w=rng.uniform(-0.15, 0.15))
    # Recurrent association (working memory)
    for aid in ASSOC_IDS:
        other = rng.choice([a for a in ASSOC_IDS if a != aid])
        connect(aid, other, w=rng.uniform(-0.2, 0.2))

    return neurons, synapses


class CortexGraph:
    def __init__(self, neurons: dict[str, Neuron], synapses: list[Synapse], generation: int = 0) -> None:
        self.neurons = neurons
        self.synapses = synapses
        self.generation = generation
        self._by_target: dict[str, list[Synapse]] = {}
        self._reindex()

    def _reindex(self) -> None:
        self._by_target = {}
        for s in self.synapses:
            self._by_target.setdefault(s.target, []).append(s)

    def forward(self, inputs: dict[str, float]) -> dict[str, float]:
        """Single feed-forward pass; sensory values clamped to [0,1] or [-1,1]."""
        for nid in SENSORY_IDS:
            if nid in self.neurons:
                v = float(inputs.get(nid, inputs.get(nid[2:], 0.0)))
                self.neurons[nid].activation = sigmoid(v) if nid != "s_drawdown" else sigmoid(-v)

        for layer in ("association", "motor", "meta"):
            for nid, n in self.neurons.items():
                if n.layer != layer:
                    continue
                net = 0.0
                for syn in self._by_target.get(nid, []):
                    pre = self.neurons[syn.source].activation
                    syn.last_pre = pre
                    myel = float(getattr(syn, "myelin", 1.0) or 1.0)
                    net += pre * syn.weight * myel
                n.fire(net)

        out: dict[str, float] = {}
        for mid in MOTOR_IDS:
            out[mid[2:]] = float(self.neurons[mid].activation)
        for xid in META_IDS:
            out[xid[2:]] = float(self.neurons[xid].activation)
        return out

    def learn(self, reward: float, lr: float | None = None) -> dict[str, float]:
        """Reward-modulated Hebbian update across all synapses."""
        lr = lr if lr is not None else float(os.getenv("CORTEX_LEARN_RATE", "0.04"))
        reward = max(-1.0, min(1.0, float(reward)))
        deltas: dict[str, float] = {}
        for syn in self.synapses:
            pre_n = self.neurons.get(syn.source)
            post_n = self.neurons.get(syn.target)
            if pre_n is None or post_n is None:
                continue
            syn.last_post = post_n.activation
            delta = lr * pre_n.plasticity * syn.last_pre * syn.last_post * reward
            syn.weight = max(-1.5, min(1.5, syn.weight + delta))
            # Myelination: rewarded co-firing conducts faster; unused edges demyelinate.
            hebb = abs(syn.last_pre * syn.last_post)
            myel = float(getattr(syn, "myelin", 1.0) or 1.0)
            if reward > 0 and hebb > 1e-6:
                myel = min(2.5, myel + 0.015 * hebb * reward)
            else:
                myel = max(0.55, myel * (0.997 if reward < 0 else 0.999))
            syn.myelin = myel
            key = f"{syn.source}->{syn.target}"
            deltas[key] = round(delta, 6)
        return deltas

    def mutate(self, exploration: float = 0.5) -> list[str]:
        """Singularity topology mutation — grow/prune synapses, nudge biases."""
        events: list[str] = []
        rng = random.Random()
        prune_thresh = float(os.getenv("CORTEX_PRUNE_WEIGHT", "0.02"))
        before = len(self.synapses)
        self.synapses = [s for s in self.synapses if abs(s.weight) >= prune_thresh]
        pruned = before - len(self.synapses)
        if pruned:
            events.append(f"pruned_{pruned}_synapses")

        n_add = max(1, int(exploration * 3))
        all_ids = list(self.neurons.keys())
        existing = {(s.source, s.target) for s in self.synapses}
        for _ in range(n_add):
            src, tgt = rng.choice(all_ids), rng.choice(all_ids)
            if src == tgt or (src, tgt) in existing:
                continue
            if self.neurons[src].layer == "motor":
                continue
            w = rng.uniform(-0.25, 0.25) * exploration
            self.synapses.append(Synapse(source=src, target=tgt, weight=w))
            existing.add((src, tgt))
            events.append(f"grew_{src}->{tgt}")

        for n in self.neurons.values():
            if n.layer in ("association", "meta"):
                n.bias += rng.uniform(-0.03, 0.03) * exploration
                n.bias = max(-1.0, min(1.0, n.bias))

        self.generation += 1
        self._reindex()
        events.append(f"gen_{self.generation}")
        return events

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "neurons": [n.to_dict() for n in self.neurons.values()],
            "synapses": [s.to_dict() for s in self.synapses],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CortexGraph":
        neurons = {n["id"]: Neuron.from_dict(n) for n in d.get("neurons", [])}
        synapses = [Synapse.from_dict(s) for s in d.get("synapses", [])]
        return cls(neurons, synapses, generation=int(d.get("generation", 0)))

    @classmethod
    def load_or_seed(cls) -> "CortexGraph":
        if GRAPH_PATH.is_file():
            try:
                return cls.from_dict(json.loads(GRAPH_PATH.read_text(encoding="utf-8")))
            except Exception:
                pass
        neurons, synapses = _seed_graph()
        g = cls(neurons, synapses, generation=0)
        g.save()
        return g

    def save(self) -> None:
        GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
        GRAPH_PATH.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def normalize_inputs(raw: dict[str, Any]) -> dict[str, float]:
    """Map live metrics → sensory neuron inputs."""
    alpha = raw.get("alpha")
    hit = float(raw.get("hit_rate", 0.5) or 0.5)
    deployed = float(raw.get("deployed_frac", 0.0) or 0.0)
    pnl = float(raw.get("paper_pnl", 0.0) or 0.0)
    neural_p = raw.get("neural_p_up")
    rsi = float(raw.get("rsi_14", 50.0) or 50.0)
    mom = float(raw.get("momentum_5d", 0.0) or 0.0)
    dd = float(raw.get("drawdown", 0.0) or 0.0)
    hft = float(raw.get("hft_pulse", 0.5) or 0.5)

    return {
        "s_alpha": float(alpha if alpha is not None else 0.0) * 10.0,
        "s_hit_rate": (hit - 0.5) * 2.0,
        "s_deployed": deployed * 2.0 - 1.0,
        "s_paper_pnl": math.tanh(pnl / 5000.0),
        "s_neural_p": (float(neural_p) - 0.5) * 2.0 if neural_p is not None else 0.0,
        "s_rsi": (rsi - 50.0) / 50.0,
        "s_momentum": math.tanh(mom * 5.0),
        "s_drawdown": dd,
        "s_hft_pulse": hft * 2.0 - 1.0,
    }
