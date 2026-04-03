"""
main.py — FastAPI application entry point.
Run with: uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from enforcement.policy_loader import load_policy, load_intent
from enforcement.armor_enforcer import ArmorEnforcer
from enforcement.audit_logger import AuditLogger
from agent.openclaw_agent import FinancialAgent
from execution.alpaca_client import AlpacaClient
from api.routes import router
from api.websocket import ws_router
import os

app = FastAPI(title="ArmorIQ Financial Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    intent_path = os.getenv("INTENT_FILE", "config/intent_model.yaml")
    policy_path = os.getenv("POLICY_FILE", "config/policy_model.yaml")
    audit_db = os.getenv("AUDIT_DB", "audit.db")

    intent = load_intent(intent_path)
    policy = load_policy(policy_path)
    audit = AuditLogger(audit_db)
    await audit.init()

    enforcer = ArmorEnforcer(intent, policy, audit)
    app.state.enforcer = enforcer
    app.state.audit = audit
    app.state.agent = FinancialAgent(enforcer)
    app.state.alpaca = AlpacaClient()
    print("✅ ArmorIQ backend started — enforcement layer active")


@app.on_event("shutdown")
async def shutdown():
    await app.state.audit.close()


app.include_router(router)
app.include_router(ws_router)