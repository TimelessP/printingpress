"""
API routes for Gutenberg book search and basket management.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models import GutenbergBook, BasketItem
from app.services.gutenberg import get_gutenberg_service
from app.services.state_manager import get_state_manager


router = APIRouter(prefix="/api", tags=["gutenberg"])


class SearchResponse(BaseModel):
    """Response for Gutenberg search."""
    books: list[GutenbergBook]
    total: int
    page: int
    has_next: bool
    has_prev: bool


class BasketResponse(BaseModel):
    """Response for basket operations."""
    items: list[BasketItem]
    count: int


class AddToBasketRequest(BaseModel):
    """Request to add a book to basket."""
    book: GutenbergBook


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool


@router.get("/gutenberg/search", response_model=SearchResponse)
async def search_gutenberg(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    lang: Optional[str] = Query(None, description="Language filter (e.g., 'en')"),
):
    """Search Project Gutenberg for books."""
    service = get_gutenberg_service()

    languages = [lang] if lang else None
    books, total, next_url, prev_url = await service.search_books(
        query=q,
        page=page,
        languages=languages,
    )

    return SearchResponse(
        books=books,
        total=total,
        page=page,
        has_next=next_url is not None,
        has_prev=prev_url is not None,
    )


@router.get("/gutenberg/book/{book_id}", response_model=GutenbergBook)
async def get_gutenberg_book(book_id: int):
    """Get a specific book from Gutenberg by ID."""
    service = get_gutenberg_service()
    book = await service.get_book(book_id)

    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    return book


@router.get("/basket", response_model=BasketResponse)
async def get_basket():
    """Get all items in the basket."""
    state = get_state_manager()
    items = await state.get_basket()

    return BasketResponse(items=items, count=len(items))


@router.post("/basket", response_model=MessageResponse)
async def add_to_basket(request: AddToBasketRequest):
    """Add a book to the basket."""
    state = get_state_manager()

    # Check if already in library
    if await state.is_in_library(request.book.id):
        return MessageResponse(
            message="Book is already in your library",
            success=False,
        )

    # Check if already in basket
    basket = await state.get_basket()
    if any(item.book.id == request.book.id for item in basket):
        return MessageResponse(
            message="Book is already in your basket",
            success=False,
        )

    # Check if currently processing
    processing = await state.get_processing()
    if any(item.book.id == request.book.id for item in processing):
        return MessageResponse(
            message="Book is currently being processed",
            success=False,
        )

    item = BasketItem(book=request.book, added_at=datetime.now())
    await state.add_to_basket(item)

    return MessageResponse(
        message=f"Added '{request.book.title}' to basket",
        success=True,
    )


@router.delete("/basket/{book_id}", response_model=MessageResponse)
async def remove_from_basket(book_id: int):
    """Remove a book from the basket."""
    state = get_state_manager()
    removed = await state.remove_from_basket(book_id)

    if removed:
        return MessageResponse(message="Removed from basket", success=True)
    else:
        return MessageResponse(message="Book not found in basket", success=False)


@router.delete("/basket", response_model=MessageResponse)
async def clear_basket():
    """Clear all items from the basket."""
    state = get_state_manager()
    await state.clear_basket()

    return MessageResponse(message="Basket cleared", success=True)
