"""
API routes for checkout and book processing.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.models import ProcessingItem, ProcessingStatus
from app.services.state_manager import get_state_manager
from app.services.processor import get_book_processor


router = APIRouter(prefix="/api", tags=["checkout"])


class CheckoutResponse(BaseModel):
    """Response for checkout operation."""
    message: str
    processing_count: int
    items: list[ProcessingItem]


class ProcessingResponse(BaseModel):
    """Response for processing status."""
    items: list[ProcessingItem]
    count: int


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout():
    """
    Checkout all items in the basket.
    
    Moves all basket items to processing and starts background tasks
    to fetch and convert each book.
    """
    state = get_state_manager()
    processor = get_book_processor()

    # Get and clear basket
    basket_items = await state.clear_basket()

    if not basket_items:
        return CheckoutResponse(
            message="Basket is empty",
            processing_count=0,
            items=[],
        )

    # Move each item to processing and start background task
    processing_items = []
    for basket_item in basket_items:
        proc_item = ProcessingItem(
            book=basket_item.book,
            status=ProcessingStatus.QUEUED,
        )
        await state.add_to_processing(proc_item)
        processing_items.append(proc_item)

        # Start async processing
        await processor.start_processing(basket_item.book)

    return CheckoutResponse(
        message=f"Started processing {len(processing_items)} book(s)",
        processing_count=len(processing_items),
        items=processing_items,
    )


@router.get("/processing", response_model=ProcessingResponse)
async def get_processing_status():
    """Get status of all books currently being processed."""
    state = get_state_manager()
    items = await state.get_processing()

    return ProcessingResponse(items=items, count=len(items))


@router.delete("/processing/{book_id}", response_model=MessageResponse)
async def cancel_processing(book_id: int):
    """Cancel processing of a specific book."""
    state = get_state_manager()
    processor = get_book_processor()

    # Try to cancel the processing task
    cancelled = await processor.cancel_processing(book_id)

    if cancelled:
        # Remove from processing queue
        await state.remove_from_processing(book_id)
        return MessageResponse(message="Processing cancelled", success=True)
    else:
        return MessageResponse(
            message="Book not found in processing queue",
            success=False,
        )
