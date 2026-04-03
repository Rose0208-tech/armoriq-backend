"""REST API endpoints."""
from __future__ import annotations
import uuid
import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Any

router = APIRouter()


class RunRequest(BaseModel):
    instruction: str


class DirectTestRequest(BaseModel):
    action: dict[str, Any]


@router.post("/agent/run")
async def run_agent(body: RunRequest, request: Request):
    session_id = str(uuid.uuid4())
    agent = request.app.state.agent
    asyncio.create_task(agent.run(body.instruction, session_id))
    return {"session_id": session_id, "status": "RUNNING"}


@router.get("/agent/status/{session_id}")
async def agent_status(session_id: str, request: Request):
    agent = request.app.state.agent
    return agent.get_session_status(session_id)


@router.post("/enforce/test")
async def test_enforcement(body: DirectTestRequest, request: Request):
    """
    Directly test the enforcement layer with any action.
    This bypasses the LLM and calls ArmorEnforcer directly.
    Use this to prove ALLOW/BLOCK works for the demo.
    """
    enforcer = request.app.state.enforcer
    session_id = str(uuid.uuid4())
    result = await enforcer.validate(body.action, session_id)
    return {
        "action": body.action,
        "decision": "ALLOW" if result.allowed else "BLOCK",
        "rule_id": result.rule_id,
        "reason": result.reason,
        "event_id": result.event_id,
        "session_id": session_id
    }


@router.get("/policy")
async def get_policy(request: Request):
    enforcer = request.app.state.enforcer
    return {
        "intent": enforcer.intent.model_dump(),
        "policy": enforcer.policy.model_dump(),
    }


@router.get("/audit/log")
async def get_audit_log(request: Request, limit: int = 100):
    audit = request.app.state.audit
    decisions = await audit.get_decisions(limit=limit)
    return {"decisions": decisions}


@router.get("/portfolio")
async def get_portfolio(request: Request):
    try:
        alpaca = request.app.state.alpaca
        return {
            "positions": alpaca.get_portfolio(),
            "account": alpaca.get_account(),
            "orders": alpaca.get_orders(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    return {"status": "ok"}