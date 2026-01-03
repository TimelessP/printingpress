"""
Search service for Printing Press library.

Combines three search methods with custom scoring:
1. KNN (K-Nearest Neighbors) - semantic similarity (in-memory)
2. Substring search - exact text matching
3. Regex search - pattern matching

Each method contributes to a final combined score.
"""

import re
from typing import Optional
from difflib import SequenceMatcher

from app.models import LibraryEntry, SearchResult
from app.services.state_manager import get_state_manager


class SearchService:
    """
    Search service using combined scoring from multiple search methods.
    
    All search indexes are in-memory only for simplicity.
    """

    def __init__(self):
        # In-memory cache of book content for search
        self._content_cache: dict[int, str] = {}
        # Simple word-based vectors for KNN (no external dependencies)
        self._word_vectors: dict[int, dict[str, float]] = {}

    async def build_index(self, entries: list[LibraryEntry], books_dir) -> None:
        """Build search indexes from library entries."""
        from pathlib import Path

        self._content_cache.clear()
        self._word_vectors.clear()

        for entry in entries:
            try:
                filepath = Path(books_dir) / entry.markdown_path
                if filepath.exists():
                    content = filepath.read_text(encoding="utf-8")
                    self._content_cache[entry.id] = content.lower()

                    # Build simple word frequency vector for KNN
                    self._word_vectors[entry.id] = self._build_word_vector(content)
            except Exception as e:
                print(f"Error indexing book {entry.id}: {e}")

    def _build_word_vector(self, text: str) -> dict[str, float]:
        """Build a simple TF (term frequency) vector from text."""
        # Tokenize and normalize
        words = re.findall(r"\b[a-z]{3,}\b", text.lower())

        # Count frequencies
        freq: dict[str, int] = {}
        for word in words:
            freq[word] = freq.get(word, 0) + 1

        # Normalize to TF (term frequency)
        total = sum(freq.values()) or 1
        return {word: count / total for word, count in freq.items()}

    def _knn_score(self, query: str, book_id: int) -> float:
        """
        Calculate KNN-style similarity score based on cosine similarity
        of word vectors.
        """
        if book_id not in self._word_vectors:
            return 0.0

        query_vector = self._build_word_vector(query)
        doc_vector = self._word_vectors[book_id]

        if not query_vector or not doc_vector:
            return 0.0

        # Cosine similarity
        dot_product = sum(
            query_vector.get(word, 0) * doc_vector.get(word, 0)
            for word in set(query_vector) | set(doc_vector)
        )

        query_norm = sum(v ** 2 for v in query_vector.values()) ** 0.5
        doc_norm = sum(v ** 2 for v in doc_vector.values()) ** 0.5

        if query_norm == 0 or doc_norm == 0:
            return 0.0

        return dot_product / (query_norm * doc_norm)

    def _substring_score(self, query: str, book_id: int, entry: LibraryEntry) -> float:
        """
        Calculate substring match score.
        
        Considers:
        - Exact matches in title (high weight)
        - Exact matches in author names (medium weight)
        - Exact matches in content (lower weight per match, but cumulative)
        """
        query_lower = query.lower()
        score = 0.0

        # Title matches (highest weight)
        if query_lower in entry.title.lower():
            # Bonus for exact match
            if query_lower == entry.title.lower():
                score += 1.0
            else:
                # Partial match - score by how much of title is matched
                score += 0.7 * (len(query_lower) / len(entry.title))

        # Author matches (medium weight)
        for author in entry.authors:
            if query_lower in author.lower():
                score += 0.5
                break

        # Subject matches
        for subject in entry.subjects:
            if query_lower in subject.lower():
                score += 0.3
                break

        # Content matches (cumulative but capped)
        if book_id in self._content_cache:
            content = self._content_cache[book_id]
            matches = content.count(query_lower)
            # Log scale to prevent super-long books from dominating
            if matches > 0:
                import math
                score += 0.2 * math.log(1 + matches)

        return min(score, 2.0)  # Cap at 2.0

    def _regex_score(self, query: str, book_id: int, entry: LibraryEntry) -> float:
        """
        Calculate regex match score.
        
        Treats the query as a potential regex pattern.
        Falls back to escaped literal if invalid regex.
        """
        # Try to compile as regex
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            # Invalid regex - escape and use as literal
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        score = 0.0

        # Title matches
        if pattern.search(entry.title):
            score += 0.8

        # Author matches
        for author in entry.authors:
            if pattern.search(author):
                score += 0.4
                break

        # Content matches
        if book_id in self._content_cache:
            content = self._content_cache[book_id]
            matches = pattern.findall(content)
            if matches:
                import math
                score += 0.3 * math.log(1 + len(matches))

        return min(score, 1.5)  # Cap at 1.5

    async def search(
        self,
        query: str,
        limit: int = 50,
    ) -> list[SearchResult]:
        """
        Search the library using combined scoring.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            List of SearchResult objects sorted by combined score
        """
        if not query.strip():
            return []

        state = get_state_manager()
        entries = await state.get_library()

        results: list[SearchResult] = []

        for entry in entries:
            # Calculate individual scores
            knn = self._knn_score(query, entry.id)
            substring = self._substring_score(query, entry.id, entry)
            regex = self._regex_score(query, entry.id, entry)

            # Combined score (weighted sum)
            # Weights can be tuned based on preference
            combined = (knn * 0.3) + (substring * 0.5) + (regex * 0.2)

            if combined > 0.01:  # Threshold to filter noise
                results.append(SearchResult(
                    entry=entry,
                    score=combined,
                    knn_score=knn,
                    substring_score=substring,
                    regex_score=regex,
                ))

        # Sort by combined score (descending)
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:limit]

    async def rebuild_index(self, books_dir) -> None:
        """Rebuild search indexes from current library."""
        state = get_state_manager()
        entries = await state.get_library()
        await self.build_index(entries, books_dir)

    def invalidate_book(self, book_id: int) -> None:
        """Remove a book from the search cache."""
        self._content_cache.pop(book_id, None)
        self._word_vectors.pop(book_id, None)

    async def add_book_to_index(self, entry: LibraryEntry, books_dir) -> None:
        """Add a single book to the search index."""
        from pathlib import Path

        try:
            filepath = Path(books_dir) / entry.markdown_path
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                self._content_cache[entry.id] = content.lower()
                self._word_vectors[entry.id] = self._build_word_vector(content)
        except Exception as e:
            print(f"Error indexing book {entry.id}: {e}")


# Global instance
_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """Get the global search service instance."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
