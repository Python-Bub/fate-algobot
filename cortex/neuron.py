"""Neuron units, synapses, and activation primitives for the trading cortex."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable


def sigmoid(x: float) -> float:
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def tanh(x: float) -> float:
    return math.tanh(max(-20.0, min(20.0, x)))


def relu(x: float) -> float:
    return max(0.0, x)


ACTIVATIONS: dict[str, Callable[[float], float]] = {
    "sigmoid": sigmoid,
    "tanh": tanh,
    "relu": relu,
}


@dataclass
class Neuron:
    """A single processing unit with bias, activation, and plasticity rate."""

    id: str
    layer: str
    bias: float = 0.0
    activation: float = 0.0
    plasticity: float = 0.08
    act_fn: str = "tanh"
    last_input: float = 0.0

    def fire(self, net_input: float) -> float:
        self.last_input = net_input
        fn = ACTIVATIONS.get(self.act_fn, tanh)
        self.activation = fn(net_input + self.bias)
        return self.activation

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "layer": self.layer,
            "bias": round(self.bias, 6),
            "plasticity": round(self.plasticity, 6),
            "act_fn": self.act_fn,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Neuron":
        return cls(
            id=str(d["id"]),
            layer=str(d["layer"]),
            bias=float(d.get("bias", 0.0)),
            plasticity=float(d.get("plasticity", 0.08)),
            act_fn=str(d.get("act_fn", "tanh")),
        )


@dataclass
class Synapse:
    """Directed edge with Hebbian-plastic weight and myelin conduction gain."""

    source: str
    target: str
    weight: float = 0.1
    myelin: float = 1.0
    last_pre: float = 0.0
    last_post: float = 0.0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "weight": round(self.weight, 6),
            "myelin": round(self.myelin, 6),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Synapse":
        return cls(
            source=str(d["source"]),
            target=str(d["target"]),
            weight=float(d.get("weight", 0.1)),
            myelin=float(d.get("myelin", 1.0)),
        )
