"""
Gutenberg service for searching and fetching books from Project Gutenberg.

Uses the Gutendex API (https://gutendex.com) for search.
"""

import httpx
from typing import Optional

from app.models import GutenbergBook


GUTENDEX_BASE_URL = "https://gutendex.com"


class GutenbergService:
    """Service for interacting with Project Gutenberg via Gutendex API."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_books(
        self,
        query: str,
        page: int = 1,
        languages: Optional[list[str]] = None,
    ) -> tuple[list[GutenbergBook], int, Optional[str], Optional[str]]:
        """
        Search for books on Project Gutenberg.

        Args:
            query: Search query (searches title, author, subject)
            page: Page number (1-indexed)
            languages: Filter by language codes (e.g., ["en"])

        Returns:
            Tuple of (books, total_count, next_url, prev_url)
        """
        client = await self._get_client()

        params = {"search": query, "page": page}
        if languages:
            params["languages"] = ",".join(languages)

        response = await client.get(f"{GUTENDEX_BASE_URL}/books/", params=params)
        response.raise_for_status()

        data = response.json()

        books = []
        for item in data.get("results", []):
            authors = [
                a.get("name", "Unknown")
                for a in item.get("authors", [])
            ]
            book = GutenbergBook(
                id=item["id"],
                title=item.get("title", "Unknown Title"),
                authors=authors,
                subjects=item.get("subjects", []),
                languages=item.get("languages", []),
                download_count=item.get("download_count", 0),
                formats=item.get("formats", {}),
            )
            books.append(book)

        return (
            books,
            data.get("count", 0),
            data.get("next"),
            data.get("previous"),
        )

    async def get_book(self, book_id: int) -> Optional[GutenbergBook]:
        """
        Get a specific book by ID.

        Args:
            book_id: The Gutenberg book ID

        Returns:
            GutenbergBook if found, None otherwise
        """
        client = await self._get_client()

        try:
            response = await client.get(f"{GUTENDEX_BASE_URL}/books/{book_id}/")
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return None

        item = response.json()

        authors = [
            a.get("name", "Unknown")
            for a in item.get("authors", [])
        ]

        return GutenbergBook(
            id=item["id"],
            title=item.get("title", "Unknown Title"),
            authors=authors,
            subjects=item.get("subjects", []),
            languages=item.get("languages", []),
            download_count=item.get("download_count", 0),
            formats=item.get("formats", {}),
        )

    async def fetch_book_content(self, book: GutenbergBook) -> Optional[str]:
        """
        Fetch the text content of a book.

        Args:
            book: The book to fetch

        Returns:
            The book content as text, or None if not available
        """
        url = book.best_text_url
        if not url:
            return None

        client = await self._get_client()

        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Handle different content types
            content_type = response.headers.get("content-type", "")

            # Return tuple of (text_content, base_url) so callers can resolve relative image URLs
            if "text/plain" in content_type:
                return response.text, str(response.url)
            elif "text/html" in content_type:
                # Return HTML as-is; caller will convert
                return response.text, str(response.url)
            elif "application/pdf" in content_type:
                # PDF would need special handling (pypdf, etc.)
                # For now, return None
                return None
            else:
                # Try to decode as text
                return response.text, str(response.url)

        except Exception as e:
            print(f"Error fetching book content: {e}")
            return None

    async def fetch_binary(self, url: str) -> tuple[Optional[bytes], Optional[str]]:
        """Fetch binary content from a URL and return (content_bytes, content_type).

        Returns (None, None) on failure.
        """
        client = await self._get_client()
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            return response.content, content_type
        except Exception as e:
            print(f"Error fetching binary resource {url}: {e}")
            return None, None


# Global instance
_gutenberg_service: Optional[GutenbergService] = None


def get_gutenberg_service() -> GutenbergService:
    """Get the global Gutenberg service instance."""
    global _gutenberg_service
    if _gutenberg_service is None:
        _gutenberg_service = GutenbergService()
    return _gutenberg_service


async def close_gutenberg_service() -> None:
    """Close the global Gutenberg service."""
    global _gutenberg_service
    if _gutenberg_service:
        await _gutenberg_service.close()
        _gutenberg_service = None
