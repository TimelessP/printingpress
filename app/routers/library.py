"""
API routes for library, search, and reading books.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models import LibraryEntry, SearchResult, Bookmark
from app.services.state_manager import get_state_manager
from app.services.search import get_search_service


router = APIRouter(prefix="/api", tags=["library"])


class LibraryResponse(BaseModel):
    """Response for library listing."""
    entries: list[LibraryEntry]
    count: int


class LibrarySearchResponse(BaseModel):
    """Response for library search."""
    results: list[SearchResult]
    count: int
    query: str


class BookContentResponse(BaseModel):
    """Response for book content."""
    entry: LibraryEntry
    content: str
    bookmark: Optional[Bookmark] = None


class BookmarkRequest(BaseModel):
    """Request to set a bookmark."""
    text_position: int
    label: Optional[str] = None


class BookmarkResponse(BaseModel):
    """Response for bookmark operations."""
    bookmark: Optional[Bookmark] = None
    message: str
    success: bool


class AllBookmarksResponse(BaseModel):
    """Response for all bookmarks."""
    bookmarks: dict[int, Bookmark]
    count: int


class MessageResponse(BaseModel):
    """Generic message response used by several endpoints."""
    message: str
    success: bool


# This will be set from main.py
BOOKS_DIR: Optional[Path] = None


def set_books_dir(path: Path) -> None:
    """Set the books directory path."""
    global BOOKS_DIR
    BOOKS_DIR = path


@router.get("/library", response_model=LibraryResponse)
async def get_library():
    """Get all books in the library."""
    state = get_state_manager()
    entries = await state.get_library()

    return LibraryResponse(entries=entries, count=len(entries))


@router.get("/library/search", response_model=LibrarySearchResponse)
async def search_library(
    q: str = Query(..., description="Search query"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """
    Search the library.
    
    Uses combined scoring from KNN, substring, and regex matching.
    """
    search = get_search_service()
    results = await search.search(q, limit=limit)

    return LibrarySearchResponse(
        results=results,
        count=len(results),
        query=q,
    )


@router.get("/library/book/{book_id}", response_model=BookContentResponse)
async def get_book_content(book_id: int):
    """Get a book's content and metadata for reading."""
    if BOOKS_DIR is None:
        raise HTTPException(status_code=500, detail="Books directory not configured")

    state = get_state_manager()
    entry = await state.get_library_entry(book_id)

    if not entry:
        raise HTTPException(status_code=404, detail="Book not found in library")

    # Read content
    filepath = BOOKS_DIR / entry.markdown_path
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Book file not found")

    content = filepath.read_text(encoding="utf-8")

    # Get bookmark if exists
    bookmark = await state.get_bookmark(book_id)

    return BookContentResponse(
        entry=entry,
        content=content,
        bookmark=bookmark,
    )


@router.get("/library/book/{book_id}/info", response_model=LibraryEntry)
async def get_book_info(book_id: int):
    """Get a book's metadata without content."""
    state = get_state_manager()
    entry = await state.get_library_entry(book_id)

    if not entry:
        raise HTTPException(status_code=404, detail="Book not found in library")

    return entry


@router.get("/bookmarks", response_model=AllBookmarksResponse)
async def get_all_bookmarks():
    """Get all bookmarks."""
    state = get_state_manager()
    bookmarks = await state.get_all_bookmarks()

    return AllBookmarksResponse(bookmarks=bookmarks, count=len(bookmarks))


@router.get("/bookmarks/{book_id}", response_model=BookmarkResponse)
async def get_bookmark(book_id: int):
    """Get bookmark for a specific book."""
    state = get_state_manager()
    bookmark = await state.get_bookmark(book_id)

    if bookmark:
        return BookmarkResponse(
            bookmark=bookmark,
            message="Bookmark found",
            success=True,
        )
    else:
        return BookmarkResponse(
            bookmark=None,
            message="No bookmark for this book",
            success=False,
        )


@router.post("/bookmarks/{book_id}", response_model=BookmarkResponse)
async def set_bookmark(book_id: int, request: BookmarkRequest):
    """Set or update a bookmark for a book."""
    from datetime import datetime

    state = get_state_manager()

    # Verify book exists
    entry = await state.get_library_entry(book_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Book not found in library")

    bookmark = Bookmark(
        book_id=book_id,
        text_position=request.text_position,
        label=request.label,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    await state.set_bookmark(bookmark)

    return BookmarkResponse(
        bookmark=bookmark,
        message="Bookmark saved",
        success=True,
    )


@router.delete("/bookmarks/{book_id}", response_model=BookmarkResponse)
async def delete_bookmark(book_id: int):
    """Delete a bookmark."""
    state = get_state_manager()
    deleted = await state.delete_bookmark(book_id)

    if deleted:
        return BookmarkResponse(
            bookmark=None,
            message="Bookmark deleted",
            success=True,
        )
    else:
        return BookmarkResponse(
            bookmark=None,
            message="Bookmark not found",
            success=False,
        )


@router.delete("/library/book/{book_id}", response_model=MessageResponse)
async def delete_library_book(book_id: int):
    """Permanently delete a book from the library (file + index + bookmarks)."""
    state = get_state_manager()

    # Check exists
    entry = await state.get_library_entry(book_id)
    if not entry:
        return MessageResponse(message="Book not found in library", success=False)

    removed = await state.remove_from_library(book_id)

    if removed:
        # Invalidate search cache if present
        try:
            from app.services.search import get_search_service
            search = get_search_service()
            search.invalidate_book(book_id)
        except Exception:
            pass

        return MessageResponse(message="Book deleted from library", success=True)
    else:
        return MessageResponse(message="Failed to delete book", success=False)
