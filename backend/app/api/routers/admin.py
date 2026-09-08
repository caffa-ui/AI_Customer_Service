from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as APIPath, Query, Request
from langgraph.types import Command

from app.api.dependencies import AdminUserDependency, TicketServiceDependency
from app.api.schemas import RefundReviewRequest, RefundReviewResponse


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/refunds")
async def list_refunds(
    user_id: AdminUserDependency,
    ticket_service: TicketServiceDependency,
    status_filter: Annotated[
        str | None,
        Query(alias="status", pattern="^(pending|approved|rejected)$"),
    ] = None,
) -> dict:
    return {"items": await ticket_service.list_refund_tickets(status_filter)}


@router.post("/refunds/{ticket_id}/review", response_model=RefundReviewResponse)
async def review_refund(
    ticket_id: Annotated[str, APIPath(min_length=1, max_length=128)],
    payload: RefundReviewRequest,
    user_id: AdminUserDependency,
    ticket_service: TicketServiceDependency,
    request: Request,
) -> RefundReviewResponse:
    result = await ticket_service.review_refund(
        ticket_id, user_id, payload.decision, payload.review_note
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", "退款工单不存在"))
    ticket = result["ticket"]
    refund_graph = getattr(request.app.state, "refund_graph", None)
    thread_id = ticket.get("refund_thread_id")
    if refund_graph is not None and thread_id:
        await refund_graph.ainvoke(
            Command(resume={"decision": payload.decision, "review_note": payload.review_note}),
            config={"configurable": {"thread_id": thread_id}},
        )
    return RefundReviewResponse(ticket=ticket)
