"""
Pydantic models for Printing Press app.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GutenbergBook(BaseModel):
    """A book from Project Gutenberg (via Gutendex API)."""

    id: int
    title: str
    authors: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    download_count: int = 0
    formats: dict[str, str] = Field(default_factory=dict)  # media_type -> url

    @property
    def best_text_url(self) -> Optional[str]:
        """Get the best available text URL (prefer plain text UTF-8)."""
        preferred_formats = [
            "text/plain; charset=utf-8",
            "text/plain",
            "text/html; charset=utf-8",
            "text/html",
            "application/pdf",
        ]
        for fmt in preferred_formats:
            if fmt in self.formats:
                return self.formats[fmt]
        return None


class BasketItem(BaseModel):
    """An item in the user's basket, awaiting checkout."""

    book: GutenbergBook
    added_at: datetime = Field(default_factory=datetime.now)


class ProcessingStatus(str, Enum):
    """Status of a book being processed."""

    QUEUED = "queued"
    FETCHING = "fetching"
    CONVERTING = "converting"
    FIXING = "fixing"  # post-conversion markdown fixes
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingItem(BaseModel):
    """A book currently being processed."""

    book: GutenbergBook
    status: ProcessingStatus = ProcessingStatus.QUEUED
    started_at: datetime = Field(default_factory=datetime.now)
    progress_message: str = ""
    error_message: Optional[str] = None


class LibraryEntry(BaseModel):
    """A book in the local library (fully processed)."""

    id: int  # Gutenberg ID
    title: str
    authors: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    markdown_path: str  # relative path within books/markdown/
    added_at: datetime = Field(default_factory=datetime.now)
    word_count: int = 0
    char_count: int = 0


class EventType(str, Enum):
    """Types of events/notifications."""

    BOOK_READY = "book_ready"
    PROCESSING_FAILED = "processing_failed"
    INFO = "info"


class Event(BaseModel):
    """A notification event for the user."""

    id: str  # UUID
    event_type: EventType
    title: str
    message: str
    book_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    read: bool = False


class Bookmark(BaseModel):
    """A bookmark storing the user's reading position in a book."""

    book_id: int
    text_position: int  # character offset into the markdown content
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    label: Optional[str] = None  # optional user label


class SearchResult(BaseModel):
    """A search result with combined scoring."""

    entry: LibraryEntry
    score: float
    knn_score: float = 0.0
    substring_score: float = 0.0
    regex_score: float = 0.0


class AppState(BaseModel):
    """
    Complete application state (for JSON persistence).
    Basket and processing are in-memory only, but we track processing
    items so we can restore them to basket on restart.
    """

    basket: list[BasketItem] = Field(default_factory=list)
    processing: list[ProcessingItem] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    bookmarks: dict[int, Bookmark] = Field(default_factory=dict)  # book_id -> Bookmark
