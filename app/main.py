"""
Printing Press - FastAPI Application

A book management app that fetches books from Project Gutenberg,
converts them to Markdown, and provides a searchable library.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.routers import gutenberg, checkout, library, events
from app.services.state_manager import init_state_manager, get_state_manager
from app.services.gutenberg import close_gutenberg_service
from app.services.processor import init_book_processor
from app.services.search import get_search_service


# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
BOOKS_DIR = BASE_DIR / "books"
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("Starting Printing Press...")

    # Initialize state manager
    state = init_state_manager(DATA_DIR, BOOKS_DIR)
    await state.load()

    # Initialize book processor
    init_book_processor(BOOKS_DIR)

    # Set books directory in library router
    library.set_books_dir(BOOKS_DIR)

    # Build search index
    search = get_search_service()
    await search.rebuild_index(BOOKS_DIR)

    print("Printing Press ready!")

    yield

    # Shutdown
    print("Shutting down Printing Press...")
    await close_gutenberg_service()


# Create app
app = FastAPI(
    title="Printing Press",
    description="A book management app powered by Project Gutenberg",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include API routers
app.include_router(gutenberg.router)
app.include_router(checkout.router)
app.include_router(library.router)
app.include_router(events.router)


# Web UI routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page - Search Gutenberg."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/basket", response_class=HTMLResponse)
async def basket_page(request: Request):
    """Basket page."""
    return templates.TemplateResponse("basket.html", {"request": request})


@app.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    """Library page."""
    return templates.TemplateResponse("library.html", {"request": request})


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    """Events/notifications page."""
    return templates.TemplateResponse("events.html", {"request": request})


@app.get("/read/{book_id}", response_class=HTMLResponse)
async def read_page(request: Request, book_id: int):
    """Book reader page."""
    return templates.TemplateResponse("reader.html", {"request": request, "book_id": book_id})


@app.get("/api/status")
async def status():
    """Health check endpoint."""
    state = get_state_manager()
    basket = await state.get_basket()
    processing = await state.get_processing()
    library_entries = await state.get_library()
    unread = await state.get_unread_count()

    return {
        "status": "ok",
        "basket_count": len(basket),
        "processing_count": len(processing),
        "library_count": len(library_entries),
        "unread_events": unread,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
