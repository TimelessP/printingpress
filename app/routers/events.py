"""
API routes for events/notifications.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.models import Event
from app.services.state_manager import get_state_manager


router = APIRouter(prefix="/api", tags=["events"])


class EventsResponse(BaseModel):
    """Response for events listing."""
    events: list[Event]
    count: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Response for unread count."""
    count: int


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool


@router.get("/events", response_model=EventsResponse)
async def get_events(unread_only: bool = False):
    """Get all events/notifications."""
    state = get_state_manager()
    events = await state.get_events(unread_only=unread_only)
    unread_count = await state.get_unread_count()

    return EventsResponse(
        events=events,
        count=len(events),
        unread_count=unread_count,
    )


@router.get("/events/unread-count", response_model=UnreadCountResponse)
async def get_unread_count():
    """Get count of unread events."""
    state = get_state_manager()
    count = await state.get_unread_count()

    return UnreadCountResponse(count=count)


@router.post("/events/{event_id}/read", response_model=MessageResponse)
async def mark_event_read(event_id: str):
    """Mark an event as read."""
    state = get_state_manager()
    success = await state.mark_event_read(event_id)

    if success:
        return MessageResponse(message="Event marked as read", success=True)
    else:
        return MessageResponse(message="Event not found", success=False)


@router.post("/events/read-all", response_model=MessageResponse)
async def mark_all_events_read():
    """Mark all events as read."""
    state = get_state_manager()
    await state.mark_all_events_read()

    return MessageResponse(message="All events marked as read", success=True)
