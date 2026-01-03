# Printing Press 📚

A self-hosted web application for searching, downloading, and reading books from [Project Gutenberg](https://www.gutenberg.org/). Books are converted to standardized Markdown with embedded images and stored locally for offline reading.

## Features

- **Search**: Query Project Gutenberg's catalog via the [Gutendex API](https://gutendex.com/)
- **Basket & Checkout**: Queue books for download and process them in the background
- **Markdown Conversion**: Converts HTML/plain-text books to clean, readable Markdown
- **Image Embedding**: Fetches book illustrations and embeds them as base64 data URLs
- **Library**: Browse and search your downloaded books with full-text search (KNN + substring + regex scoring)
- **Reader**: Read books in a clean preview mode or view the raw Markdown source
- **Bookmarks**: Save your reading position and jump back later
- **Events/Notifications**: Get notified when books finish processing

## Quick Start

### Prerequisites

- Python 3.12+
- Internet connection (for fetching books from Gutenberg)

### Setup

```bash
# Clone the repository
git clone <repo-url> printingpress
cd printingpress

# Set up the development environment
./dev-prepare.sh

# Run the server
./run.sh
```

Then open http://127.0.0.1:8000 in your browser.

### Manual Setup

```bash
# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create data directories
mkdir -p data books/markdown

# Run the server
uvicorn app.main:app --reload
```

## Project Structure

```
printingpress/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── models/
│   │   └── schemas.py       # Pydantic models
│   ├── routers/
│   │   ├── gutenberg.py     # Search & basket endpoints
│   │   ├── checkout.py      # Processing endpoints
│   │   ├── library.py       # Library & bookmarks endpoints
│   │   └── events.py        # Notifications endpoints
│   ├── services/
│   │   ├── gutenberg.py     # Gutendex API client
│   │   ├── processor.py     # Book processing (fetch, convert, embed images)
│   │   ├── state_manager.py # JSON persistence for app state
│   │   └── search.py        # Full-text search service
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS and JavaScript
├── books/
│   ├── index.json           # Library index
│   └── markdown/            # Downloaded books as .md files
├── data/
│   └── state.json           # App state (basket, events, bookmarks)
├── requirements.txt
├── dev-prepare.sh           # Development environment setup
├── run.sh                   # Run the server
└── README.md
```

## API Endpoints

### Gutenberg / Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/gutenberg/search?q=...` | Search Project Gutenberg |
| GET | `/api/gutenberg/book/{id}` | Get book metadata by ID |

### Basket

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/basket` | List basket items |
| POST | `/api/basket` | Add book to basket |
| DELETE | `/api/basket/{book_id}` | Remove from basket |
| DELETE | `/api/basket` | Clear basket |

### Checkout / Processing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/checkout` | Start processing all basket items |
| GET | `/api/processing` | Get processing status |
| DELETE | `/api/processing/{book_id}` | Cancel processing |

### Library

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/library` | List all library books |
| GET | `/api/library/search?q=...` | Search library |
| GET | `/api/library/book/{id}` | Get book content |
| DELETE | `/api/library/book/{id}` | Delete book from library |

### Bookmarks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bookmarks` | List all bookmarks |
| GET | `/api/bookmarks/{book_id}` | Get bookmark for book |
| POST | `/api/bookmarks/{book_id}` | Set bookmark |
| DELETE | `/api/bookmarks/{book_id}` | Delete bookmark |

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/events` | List events |
| GET | `/api/events/unread-count` | Get unread count |
| POST | `/api/events/{id}/read` | Mark event as read |
| POST | `/api/events/mark-all-read` | Mark all as read |

## Configuration

Environment variables for `run.sh`:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8000` | Server port |
| `RELOAD` | `1` | Enable auto-reload (set to `0` for production) |

Example:

```bash
HOST=0.0.0.0 PORT=9000 RELOAD=0 ./run.sh
```

## Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- **HTTP Client**: [httpx](https://www.python-httpx.org/)
- **Data Validation**: [Pydantic](https://docs.pydantic.dev/)
- **Templates**: [Jinja2](https://jinja.palletsprojects.com/)
- **Persistence**: JSON files (no database required)

## License

MIT
