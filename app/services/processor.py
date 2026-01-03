"""
Book processing service for Printing Press.

Handles the async background task of:
1. Fetching book content from Gutenberg
2. Converting to standardized Markdown
3. Saving to library
4. Notifying user
"""

import asyncio
import re
import uuid
import html
from datetime import datetime
from pathlib import Path
from typing import Optional
import base64
from urllib.parse import urljoin

from app.models import (
    GutenbergBook,
    ProcessingItem,
    ProcessingStatus,
    LibraryEntry,
    Event,
    EventType,
)
from app.services.state_manager import get_state_manager
from app.services.gutenberg import get_gutenberg_service


class BookProcessor:
    """Processes books from Gutenberg into standardized Markdown."""

    def __init__(self, books_dir: Path):
        self.books_dir = books_dir
        self.markdown_dir = books_dir / "markdown"
        self._processing_tasks: dict[int, asyncio.Task] = {}

    async def start_processing(self, book: GutenbergBook) -> None:
        """Start processing a book in the background."""
        if book.id in self._processing_tasks:
            return  # Already processing

        task = asyncio.create_task(self._process_book(book))
        self._processing_tasks[book.id] = task

    async def _process_book(self, book: GutenbergBook) -> None:
        """Process a single book."""
        state = get_state_manager()
        gutenberg = get_gutenberg_service()

        try:
            # Update status: fetching
            await state.update_processing_status(
                book.id,
                ProcessingStatus.FETCHING,
                f"Fetching content for '{book.title}'...",
            )

            # Fetch content (text/html/plain) and base URL
            fetched = await gutenberg.fetch_book_content(book)
            if not fetched:
                raise ValueError("Could not fetch book content")
            # fetched is (content, base_url)
            content, base_url = fetched
            if not content:
                raise ValueError("Could not fetch book content")

            # Update status: converting
            await state.update_processing_status(
                book.id,
                ProcessingStatus.CONVERTING,
                "Converting to Markdown...",
            )

            # Convert to markdown
            markdown_content = await self._convert_to_markdown(content, book)

            # Embed images found in the markdown as data URLs
            try:
                markdown_content = await self._embed_images(markdown_content, base_url)
            except Exception as e:
                # Non-fatal: log and continue
                print(f"Warning: embedding images failed for {book.id}: {e}")

            # Convert relative URLs to absolute for audio/other media links
            try:
                markdown_content = self._absolutize_links(markdown_content, base_url)
            except Exception as e:
                # Non-fatal: log and continue
                print(f"Warning: absolutizing links failed for {book.id}: {e}")

            # Update status: fixing
            await state.update_processing_status(
                book.id,
                ProcessingStatus.FIXING,
                "Applying Markdown fixes...",
            )

            # Apply markdown fixes
            markdown_content = await self._fix_markdown(markdown_content)

            # Update status: saving
            await state.update_processing_status(
                book.id,
                ProcessingStatus.SAVING,
                "Saving to library...",
            )

            # Save to file
            filename = self._generate_filename(book)
            filepath = self.markdown_dir / filename
            filepath.write_text(markdown_content, encoding="utf-8")

            # Create library entry
            entry = LibraryEntry(
                id=book.id,
                title=book.title,
                authors=book.authors,
                subjects=book.subjects,
                languages=book.languages,
                markdown_path=f"markdown/{filename}",
                added_at=datetime.now(),
                word_count=len(markdown_content.split()),
                char_count=len(markdown_content),
            )
            await state.add_to_library(entry)

            # Update status: completed
            await state.update_processing_status(
                book.id,
                ProcessingStatus.COMPLETED,
                "Book added to library!",
            )

            # Remove from processing queue
            await state.remove_from_processing(book.id)

            # Create success event
            event = Event(
                id=str(uuid.uuid4()),
                event_type=EventType.BOOK_READY,
                title="Book Ready!",
                message=f"'{book.title}' has been added to your library.",
                book_id=book.id,
                created_at=datetime.now(),
            )
            await state.add_event(event)

        except Exception as e:
            # Update status: failed
            await state.update_processing_status(
                book.id,
                ProcessingStatus.FAILED,
                "Processing failed",
                error_message=str(e),
            )

            # Create failure event
            event = Event(
                id=str(uuid.uuid4()),
                event_type=EventType.PROCESSING_FAILED,
                title="Processing Failed",
                message=f"Failed to process '{book.title}': {str(e)}",
                book_id=book.id,
                created_at=datetime.now(),
            )
            await state.add_event(event)

            # Remove from processing queue after failure
            await state.remove_from_processing(book.id)

        finally:
            # Clean up task reference
            self._processing_tasks.pop(book.id, None)

    async def _convert_to_markdown(self, content: str, book: GutenbergBook) -> str:
        """Convert book content to standardized Markdown."""
        # Detect content type
        is_html = content.strip().startswith("<!DOCTYPE") or "<html" in content[:1000].lower()

        if is_html:
            markdown = self._html_to_markdown(content)
        else:
            markdown = self._text_to_markdown(content)

        # Add book metadata header
        authors_str = ", ".join(book.authors) if book.authors else "Unknown"
        header = f"""# {book.title}

**Author(s):** {authors_str}  
**Gutenberg ID:** {book.id}  
**Languages:** {", ".join(book.languages)}  

---

"""
        return header + markdown

    def _text_to_markdown(self, text: str) -> str:
        """Convert plain text to Markdown."""
        lines = text.split("\n")
        result_lines = []
        in_paragraph = False
        paragraph_lines = []

        for line in lines:
            stripped = line.strip()

            # Skip Gutenberg header/footer markers
            if "*** START OF" in line or "*** END OF" in line:
                continue
            if "***START OF" in line or "***END OF" in line:
                continue

            # Empty line ends paragraph
            if not stripped:
                if paragraph_lines:
                    result_lines.append(" ".join(paragraph_lines))
                    result_lines.append("")
                    paragraph_lines = []
                in_paragraph = False
                continue

            # Check for chapter headings
            if re.match(r"^(CHAPTER|Chapter|BOOK|Book|PART|Part|SECTION|Section)\s+[IVXLCDM\d]+", stripped):
                if paragraph_lines:
                    result_lines.append(" ".join(paragraph_lines))
                    result_lines.append("")
                    paragraph_lines = []
                result_lines.append(f"## {stripped}")
                result_lines.append("")
                continue

            # Check for all-caps headings
            if stripped.isupper() and len(stripped) < 100 and len(stripped) > 2:
                if paragraph_lines:
                    result_lines.append(" ".join(paragraph_lines))
                    result_lines.append("")
                    paragraph_lines = []
                result_lines.append(f"### {stripped.title()}")
                result_lines.append("")
                continue

            # Regular text - accumulate into paragraph
            paragraph_lines.append(stripped)

        # Flush remaining paragraph
        if paragraph_lines:
            result_lines.append(" ".join(paragraph_lines))

        return "\n".join(result_lines)

    def _html_to_markdown(self, html_content: str) -> str:
        """Convert HTML to Markdown (basic conversion)."""
        # Remove doctype and html structure
        content = re.sub(r"<!DOCTYPE[^>]*>", "", html_content, flags=re.IGNORECASE)
        content = re.sub(r"<html[^>]*>", "", content, flags=re.IGNORECASE)
        content = re.sub(r"</html>", "", content, flags=re.IGNORECASE)

        # Remove head section
        content = re.sub(r"<head[^>]*>.*?</head>", "", content, flags=re.IGNORECASE | re.DOTALL)

        # Remove body tags
        content = re.sub(r"<body[^>]*>", "", content, flags=re.IGNORECASE)
        content = re.sub(r"</body>", "", content, flags=re.IGNORECASE)

        def convert_heading(match, level):
            """Convert an HTML heading to markdown, preserving anchor IDs."""
            attrs = match.group(1)  # Attributes of the heading tag
            inner = match.group(2)  # Inner content of the heading
            
            # Extract id from heading tag attributes
            heading_id = None
            id_match = re.search(r'id=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if id_match:
                heading_id = id_match.group(1)
            
            # Also look for anchor tags with id inside the heading content
            if not heading_id:
                anchor_match = re.search(r'<a[^>]*id=["\']([^"\']+)["\'][^>]*>', inner, re.IGNORECASE)
                if anchor_match:
                    heading_id = anchor_match.group(1)
            
            # Remove any remaining HTML tags from inner content
            text = re.sub(r'<[^>]+>', '', inner).strip()
            
            # Build markdown heading with optional anchor
            hashes = '#' * level
            if heading_id and text:
                return f'{hashes} {text} {{#{heading_id}}}\n\n'
            elif text:
                return f'{hashes} {text}\n\n'
            else:
                return ''  # Skip empty headings

        # Convert headings, capturing attributes and content separately
        for i in range(1, 7):
            content = re.sub(
                rf"<h{i}([^>]*)>(.*?)</h{i}>",
                lambda m, level=i: convert_heading(m, level),
                content,
                flags=re.IGNORECASE | re.DOTALL,
            )

        # Convert paragraphs
        content = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", content, flags=re.IGNORECASE | re.DOTALL)

        # Convert line breaks
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)

        # Convert bold - strip internal whitespace to avoid **\ntext**
        def convert_bold(match):
            inner = match.group(2).strip()
            if inner:
                return f"**{inner}**"
            return ''
        content = re.sub(r"<(b|strong)[^>]*>(.*?)</\1>", convert_bold, content, flags=re.IGNORECASE | re.DOTALL)

        # Convert italic - strip internal whitespace
        def convert_italic(match):
            inner = match.group(2).strip()
            if inner:
                return f"*{inner}*"
            return ''
        content = re.sub(r"<(i|em)[^>]*>(.*?)</\1>", convert_italic, content, flags=re.IGNORECASE | re.DOTALL)

        # Convert links
        content = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r"[\2](\1)", content, flags=re.IGNORECASE | re.DOTALL)

        # Convert images to data URLs if possible (placeholder for now)
        content = re.sub(r'<img[^>]*src=["\']([^"\']*)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*/?>',
                r"![\2](\1)", content, flags=re.IGNORECASE)
        content = re.sub(r'<img[^>]*src=["\']([^"\']*)["\'][^>]*/?>',
                r"![image](\1)", content, flags=re.IGNORECASE)

        # Convert standalone anchor tags to markdown anchor format
        # These are used by Gutenberg for TOC links: <a name="linkXXX"> or <a id="linkXXX">
        # Handle anchors that may contain whitespace, comments, or nothing
        content = re.sub(r'<a[^>]*(?:name|id)=["\']([^"\']+)["\'][^>]*>(?:\s|<!--[^>]*-->)*</a>',
                r'{#\1}', content, flags=re.IGNORECASE)
        # Also handle anchors with actual text content inside
        content = re.sub(r'<a[^>]*(?:name|id)=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
                lambda m: f'{{#{m.group(1)}}} {m.group(2).strip()}' if m.group(2).strip() else f'{{#{m.group(1)}}}',
                content, flags=re.IGNORECASE)

        # Remove remaining tags
        content = re.sub(r"<[^>]+>", "", content)

        # Decode HTML entities
        content = html.unescape(content)

        # Clean up whitespace
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = content.strip()

        return content

    async def _embed_images(self, markdown: str, base_url: Optional[str]) -> str:
        """Find image references in the markdown, fetch them, and replace with data URLs.

        Supports Markdown image syntax and leftover HTML <img src=> occurrences.
        """
        if not base_url:
            return markdown

        gutenberg = get_gutenberg_service()

        # Collect candidate image URLs from markdown image syntax ![alt](url)
        img_urls = set()

        for m in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', markdown):
            url = m.group(1).strip()
            if url and not url.lower().startswith('data:'):
                img_urls.add(url)

        # Also catch any remaining <img src="..."> occurrences
        for m in re.finditer(r'<img[^>]*src=["\']([^"\']+)["\']', markdown, flags=re.IGNORECASE):
            url = m.group(1).strip()
            if url and not url.lower().startswith('data:'):
                img_urls.add(url)

        if not img_urls:
            return markdown

        # For each unique URL, fetch and replace
        replacements: dict[str, str] = {}

        for raw_url in img_urls:
            # Resolve relative URLs against base_url
            try:
                absolute = urljoin(base_url, raw_url)
            except Exception:
                absolute = raw_url

            # Fetch binary data
            data, content_type = await gutenberg.fetch_binary(absolute)
            if not data:
                # Skip replacement if fetch failed
                continue

            # If content type missing, try to infer from extension
            if not content_type:
                if absolute.lower().endswith('.png'):
                    content_type = 'image/png'
                elif absolute.lower().endswith('.jpg') or absolute.lower().endswith('.jpeg'):
                    content_type = 'image/jpeg'
                elif absolute.lower().endswith('.gif'):
                    content_type = 'image/gif'
                else:
                    content_type = 'application/octet-stream'

            b64 = base64.b64encode(data).decode('ascii')
            data_url = f"data:{content_type};base64,{b64}"

            replacements[raw_url] = data_url

        # Perform replacements in markdown
        def replace_fn(match):
            url = match.group(1).strip()
            return f"![{match.group(0).split('](')[0][2:]}]({replacements.get(url, url)})"

        # Replace markdown img links
        markdown = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', lambda m: f"![{m.group(1)}]({replacements.get(m.group(2).strip(), m.group(2).strip())})", markdown)

        # Replace html img src attributes
        markdown = re.sub(r'(<img[^>]*src=["\'])([^"\']+)(["\'])', lambda m: m.group(1) + replacements.get(m.group(2), m.group(2)) + m.group(3), markdown, flags=re.IGNORECASE)

        return markdown

    def _absolutize_links(self, markdown: str, base_url: Optional[str]) -> str:
        """Convert relative URLs in markdown links to absolute URLs.
        
        This handles non-image links like audio files (mp3, ogg, etc.) that
        should point to the original Gutenberg URLs.
        """
        if not base_url:
            return markdown

        def replace_link(match):
            text = match.group(1)
            url = match.group(2).strip()
            
            # Skip if already absolute, data URL, or anchor-only
            if url.startswith(('http://', 'https://', 'data:', '#', 'mailto:')):
                return match.group(0)
            
            # Resolve relative URL against base
            try:
                absolute = urljoin(base_url, url)
                return f"[{text}]({absolute})"
            except Exception:
                return match.group(0)

        # Match markdown links (but not images which start with !)
        # Pattern: [text](url) where it's not preceded by !
        markdown = re.sub(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', replace_link, markdown)

        return markdown

    async def _fix_markdown(self, markdown: str) -> str:
        """Apply fixes to ensure strict/clean Markdown."""
        # Remove page break markers
        markdown = re.sub(r"[-_=]{3,}", "", markdown)

        # Fix multiple blank lines
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        # Fix broken bold markers (** on one line, content** on another)
        # This happens when nested tags create empty bold spans
        markdown = re.sub(r'\*\*\s*\n+\s*([^*\n]+)\*\*', r'**\1**', markdown)
        
        # Also fix italic markers similarly
        markdown = re.sub(r'\*\s*\n+\s*([^*\n]+)\*', r'*\1*', markdown)
        
        # Remove orphaned bold/italic markers on their own lines
        markdown = re.sub(r'^\*\*\s*$', '', markdown, flags=re.MULTILINE)
        markdown = re.sub(r'^\*\s*$', '', markdown, flags=re.MULTILINE)

        # Ensure headings have blank line after
        markdown = re.sub(r"(^#{1,6} .+)(\n)([^\n])", r"\1\n\n\3", markdown, flags=re.MULTILINE)

        # Fix common OCR issues
        markdown = markdown.replace("ﬁ", "fi")
        markdown = markdown.replace("ﬂ", "fl")
        markdown = markdown.replace("ﬀ", "ff")
        markdown = markdown.replace("ﬃ", "ffi")
        markdown = markdown.replace("ﬄ", "ffl")

        # Normalize quotes
        markdown = markdown.replace(""", '"')
        markdown = markdown.replace(""", '"')
        markdown = markdown.replace("'", "'")
        markdown = markdown.replace("'", "'")

        # Normalize dashes
        markdown = markdown.replace("—", "---")
        markdown = markdown.replace("–", "--")

        # Remove trailing whitespace on lines
        lines = markdown.split("\n")
        lines = [line.rstrip() for line in lines]
        markdown = "\n".join(lines)

        return markdown.strip()

    def _generate_filename(self, book: GutenbergBook) -> str:
        """Generate a filename for the book."""
        # Sanitize title for filename
        safe_title = re.sub(r"[^\w\s-]", "", book.title)
        safe_title = re.sub(r"\s+", "_", safe_title)
        safe_title = safe_title[:50]  # Limit length

        return f"{book.id}_{safe_title}.md"

    async def cancel_processing(self, book_id: int) -> bool:
        """Cancel processing of a book."""
        if book_id in self._processing_tasks:
            self._processing_tasks[book_id].cancel()
            del self._processing_tasks[book_id]
            return True
        return False


# Global instance
_book_processor: Optional[BookProcessor] = None


def get_book_processor() -> BookProcessor:
    """Get the global book processor instance."""
    if _book_processor is None:
        raise RuntimeError("Book processor not initialized")
    return _book_processor


def init_book_processor(books_dir: Path) -> BookProcessor:
    """Initialize the global book processor."""
    global _book_processor
    _book_processor = BookProcessor(books_dir)
    return _book_processor
