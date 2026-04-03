"""
enforcement/intent_model.py
─────────────────────────────────────────────────────────────
Pydantic v2 models for the structured Intent Model and a
loader that reads config/intent_model.yaml at startup.
"""

from __future__ import annotations

from typing import Optional
import yaml
from pydantic import BaseModel, Field


class DirectoryScope(BaseModel):
    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)


class IntentScope(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    data_directories: DirectoryScope = Field(default_factory=DirectoryScope)


class IntentModel(BaseModel):
    id: str
    description: str
    authorized_goals: list[str] = Field(default_factory=list)
    scope: IntentScope = Field(default_factory=IntentScope)
    delegated_to: Optional[str] = None


def load_intent(path: str) -> IntentModel:
    """Load and validate the intent model from a YAML file."""
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    intent_data = raw.get("intent", raw)
    return IntentModel.model_validate(intent_data)