"""FastAPI webhook receiver for GitHub pull_request events."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException, Request, status

from webhook.parser import parse_pr_payload
from webhook.verifier import verify_signature

logger = logging.getLogger(__name__)
app = FastAPI(title="DeployGuard Webhook")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
) -> dict:
    raw_body = await request.body()

    if not verify_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"ignored": True, "event": x_github_event}

    payload = await request.json()
    pr = parse_pr_payload(payload)
    if pr is None:
        return {"ignored": True, "reason": "not a main-targeting PR open/sync"}

    # Import here so the webhook boots even if Band credentials are missing (dev mode)
    try:
        from webhook.band_initiator import initiate_chain
        room_id = initiate_chain(pr)
        logger.info("Initiated chain for PR #%s in room %s", pr.pr_number, room_id)
        return {"accepted": True, "pr": pr.pr_number, "room": room_id}
    except Exception as exc:
        logger.exception("Failed to initiate Band chain for PR #%s", pr.pr_number)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
