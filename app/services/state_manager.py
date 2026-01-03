"""
State management service for Printing Press.

Handles JSON-based persistence for:
- App state (basket, processing queue, events, bookmarks)
- Library index (books/index.json)

On startup, any items in 'processing' state are moved back to basket.
"""

import json
from pathlib import Path
from typing import Optional
import asyncio
from datetime import datetime

from app.models import (
    AppState,
    BasketItem,
    ProcessingItem,
    ProcessingStatus,
    LibraryEntry,
    Event,
    Bookmark,
)


class StateManager:
    """Manages application state with JSON file persistence."""

    def __init__(self, data_dir: Path, books_dir: Path):
        self.data_dir = data_dir
        self.books_dir = books_dir
        self.state_file = data_dir / "state.json"
        self.index_file = books_dir / "index.json"

        # In-memory state
        self._state: AppState = AppState()
        self._library: list[LibraryEntry] = []
        self._lock = asyncio.Lock()

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.books_dir.mkdir(parents=True, exist_ok=True)
        (self.books_dir / "markdown").mkdir(parents=True, exist_ok=True)

    async def load(self) -> None:
        """Load state from disk. Move any 'processing' items back to basket."""
        async with self._lock:
            # Load app state
            if self.state_file.exists():
                try:
                    data = json.loads(self.state_file.read_text(encoding="utf-8"))
                    self._state = AppState.model_validate(data)
                except Exception as e:
                    print(f"Warning: Could not load state file: {e}")
                    self._state = AppState()

            # Move any processing items back to basket (app was restarted)
            if self._state.processing:
                for proc_item in self._state.processing:
                    basket_item = BasketItem(
                        book=proc_item.book,
                        added_at=proc_item.started_at,
                    )
                    self._state.basket.append(basket_item)
                self._state.processing = []
                await self._save_state_unlocked()

            # Load library index
            if self.index_file.exists():
                try:
                    data = json.loads(self.index_file.read_text(encoding="utf-8"))
                    self._library = [LibraryEntry.model_validate(entry) for entry in data]
                except Exception as e:
                    print(f"Warning: Could not load library index: {e}")
                    self._library = []

    async def _save_state_unlocked(self) -> None:
        """Save state to disk (must be called with lock held)."""
        self.state_file.write_text(
            self._state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    async def _save_state(self) -> None:
        """Save state to disk (acquires lock)."""
        async with self._lock:
            await self._save_state_unlocked()

    async def _save_library(self) -> None:
        """Save library index to disk. Must be called with lock held."""
        data = [entry.model_dump() for entry in self._library]
        # Convert datetime objects to ISO strings for JSON serialization
        self.index_file.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

    # --- Basket operations ---

    async def get_basket(self) -> list[BasketItem]:
        """Get all items in the basket."""
        async with self._lock:
            return list(self._state.basket)

    async def add_to_basket(self, item: BasketItem) -> None:
        """Add an item to the basket."""
        async with self._lock:
            # Don't add duplicates
            if any(b.book.id == item.book.id for b in self._state.basket):
                return
            self._state.basket.append(item)
            await self._save_state_unlocked()

    async def remove_from_basket(self, book_id: int) -> bool:
        """Remove an item from the basket by book ID. Returns True if removed."""
        async with self._lock:
            original_len = len(self._state.basket)
            self._state.basket = [b for b in self._state.basket if b.book.id != book_id]
            if len(self._state.basket) < original_len:
                await self._save_state_unlocked()
                return True
            return False

    async def clear_basket(self) -> list[BasketItem]:
        """Clear and return all basket items (for checkout)."""
        async with self._lock:
            items = list(self._state.basket)
            self._state.basket = []
            await self._save_state_unlocked()
            return items

    # --- Processing operations ---

    async def get_processing(self) -> list[ProcessingItem]:
        """Get all items being processed."""
        async with self._lock:
            return list(self._state.processing)

    async def add_to_processing(self, item: ProcessingItem) -> None:
        """Add an item to processing queue."""
        async with self._lock:
            self._state.processing.append(item)
            await self._save_state_unlocked()

    async def update_processing_status(
        self,
        book_id: int,
        status: ProcessingStatus,
        progress_message: str = "",
        error_message: Optional[str] = None,
    ) -> None:
        """Update the status of a processing item."""
        async with self._lock:
            for item in self._state.processing:
                if item.book.id == book_id:
                    item.status = status
                    item.progress_message = progress_message
                    if error_message:
                        item.error_message = error_message
                    break
            await self._save_state_unlocked()

    async def remove_from_processing(self, book_id: int) -> Optional[ProcessingItem]:
        """Remove and return a processing item."""
        async with self._lock:
            for i, item in enumerate(self._state.processing):
                if item.book.id == book_id:
                    removed = self._state.processing.pop(i)
                    await self._save_state_unlocked()
                    return removed
            return None

    # --- Library operations ---

    async def get_library(self) -> list[LibraryEntry]:
        """Get all library entries."""
        async with self._lock:
            return list(self._library)

    async def get_library_ids(self) -> set[int]:
        """Get set of all book IDs in the library."""
        async with self._lock:
            return {entry.id for entry in self._library}

    async def get_library_entry(self, book_id: int) -> Optional[LibraryEntry]:
        """Get a specific library entry by book ID."""
        async with self._lock:
            for entry in self._library:
                if entry.id == book_id:
                    return entry
            return None

    async def add_to_library(self, entry: LibraryEntry) -> None:
        """Add a book to the library."""
        async with self._lock:
            # Update if exists, otherwise add
            for i, existing in enumerate(self._library):
                if existing.id == entry.id:
                    self._library[i] = entry
                    break
            else:
                self._library.append(entry)
            await self._save_library()

    async def remove_from_library(self, book_id: int) -> bool:
        """Remove a library entry and its file from disk. Returns True if removed."""
        async with self._lock:
            for i, entry in enumerate(self._library):
                if entry.id == book_id:
                    # Remove file if exists
                    try:
                        file_path = self.books_dir / entry.markdown_path
                        if file_path.exists():
                            file_path.unlink()
                    except Exception as e:
                        print(f"Warning: could not remove book file {entry.markdown_path}: {e}")

                    # Remove from in-memory index
                    self._library.pop(i)

                    # Remove any bookmarks
                    if book_id in self._state.bookmarks:
                        del self._state.bookmarks[book_id]

                    # Save library and state
                    await self._save_library()
                    await self._save_state_unlocked()
                    return True

            return False

    async def is_in_library(self, book_id: int) -> bool:
        """Check if a book is already in the library."""
        async with self._lock:
            return any(entry.id == book_id for entry in self._library)

    # --- Events operations ---

    async def get_events(self, unread_only: bool = False) -> list[Event]:
        """Get events/notifications."""
        async with self._lock:
            if unread_only:
                return [e for e in self._state.events if not e.read]
            return list(self._state.events)

    async def get_unread_count(self) -> int:
        """Get count of unread events."""
        async with self._lock:
            return sum(1 for e in self._state.events if not e.read)

    async def add_event(self, event: Event) -> None:
        """Add a new event."""
        async with self._lock:
            self._state.events.insert(0, event)  # newest first
            # Keep only last 100 events
            self._state.events = self._state.events[:100]
            await self._save_state_unlocked()

    async def mark_event_read(self, event_id: str) -> bool:
        """Mark an event as read."""
        async with self._lock:
            for event in self._state.events:
                if event.id == event_id:
                    event.read = True
                    await self._save_state_unlocked()
                    return True
            return False

    async def mark_all_events_read(self) -> None:
        """Mark all events as read."""
        async with self._lock:
            for event in self._state.events:
                event.read = True
            await self._save_state_unlocked()

    async def clear_all_events(self) -> None:
        """Clear all events."""
        async with self._lock:
            self._state.events.clear()
            await self._save_state_unlocked()

    # --- Bookmark operations ---

    async def get_bookmark(self, book_id: int) -> Optional[Bookmark]:
        """Get bookmark for a book."""
        async with self._lock:
            return self._state.bookmarks.get(book_id)

    async def get_all_bookmarks(self) -> dict[int, Bookmark]:
        """Get all bookmarks."""
        async with self._lock:
            return dict(self._state.bookmarks)

    async def set_bookmark(self, bookmark: Bookmark) -> None:
        """Set/update a bookmark."""
        async with self._lock:
            bookmark.updated_at = datetime.now()
            self._state.bookmarks[bookmark.book_id] = bookmark
            await self._save_state_unlocked()

    async def delete_bookmark(self, book_id: int) -> bool:
        """Delete a bookmark."""
        async with self._lock:
            if book_id in self._state.bookmarks:
                del self._state.bookmarks[book_id]
                await self._save_state_unlocked()
                return True
            return False


# Global instance (initialized in main.py)
state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get the global state manager instance."""
    if state_manager is None:
        raise RuntimeError("State manager not initialized")
    return state_manager


def init_state_manager(data_dir: Path, books_dir: Path) -> StateManager:
    """Initialize the global state manager."""
    global state_manager
    state_manager = StateManager(data_dir, books_dir)
    return state_manager
