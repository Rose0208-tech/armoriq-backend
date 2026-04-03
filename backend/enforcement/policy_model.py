"""
enforcement/policy_model.py
─────────────────────────────────────────────────────────────
Pydantic v2 models for the structured Policy Model and a
loader that reads config/policy_model.yaml at startup.
"""

from __future__ import annotations

from typing import Any, Literal
import yaml
from pydantic import BaseModel, Field


class PolicyRule(BaseModel):
    id: str
    name: str
    type: str
    description: str
    enforce_on: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    on_violation: Literal["BLOCK", "WARN"] = "BLOCK"


class PolicyModel(BaseModel):
    id: str
    rules: list[PolicyRule] = Field(default_factory=list)


def load_policy(path: str) -> PolicyModel:
    """Load and validate the policy model from a YAML file."""
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    policy_data = raw.get("policy", raw)
    return PolicyModel.model_validate(policy_data)