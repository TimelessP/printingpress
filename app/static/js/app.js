/* Printing Press - Main JavaScript */

// Theme management
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'system';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeButton(savedTheme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'system';
    const themes = ['light', 'dark', 'system'];
    const nextIndex = (themes.indexOf(current) + 1) % themes.length;
    const newTheme = themes[nextIndex];
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeButton(newTheme);
}

function updateThemeButton(theme) {
    const button = document.querySelector('.theme-switcher');
    if (button) {
        const titles = { light: 'Light mode (click for dark)', dark: 'Dark mode (click for system)', system: 'System mode (click for light)' };
        button.title = titles[theme] || 'Toggle theme';
    }
}

// Initialize theme on load
initTheme();

// Toast notifications
const toastContainer = document.createElement('div');
toastContainer.className = 'toast-container';
document.body.appendChild(toastContainer);

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// API helpers
async function apiRequest(endpoint, options = {}) {
    const response = await fetch(`/api${endpoint}`, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || 'Request failed');
    }

    // Handle empty responses (e.g., DELETE requests)
    const text = await response.text();
    if (!text) {
        return { success: true };
    }
    return JSON.parse(text);
}

// API object with all methods
const api = {
    // Search (Gutenberg)
    search: (query, page = 1) => apiRequest(`/gutenberg/search?q=${encodeURIComponent(query)}&page=${page}`),
    // Library search (local)
    searchLibrary: (query, limit = 50) => apiRequest(`/library/search?q=${encodeURIComponent(query)}&limit=${limit}`),
    
    // Basket
    getBasket: () => apiRequest('/basket'),
    addToBasket: (bookId) => apiRequest('/basket', { method: 'POST', body: JSON.stringify({ book_id: bookId }) }),
    removeFromBasket: (bookId) => apiRequest(`/basket/${bookId}`, { method: 'DELETE' }),
    clearBasket: () => apiRequest('/basket', { method: 'DELETE' }),
    checkout: () => apiRequest('/checkout', { method: 'POST' }),
    
    // Library
    getLibrary: () => apiRequest('/library'),
    getBook: (bookId) => apiRequest(`/library/book/${bookId}`),
    deleteBook: (bookId) => apiRequest(`/library/book/${bookId}`, { method: 'DELETE' }),
    saveBookPosition: (bookId, position) => apiRequest(`/bookmarks/${bookId}`, { method: 'POST', body: JSON.stringify({ text_position: position }) }),
    deleteBookmark: (bookId) => apiRequest(`/bookmarks/${bookId}`, { method: 'DELETE' }),
    
    // Events
    getEvents: () => apiRequest('/events'),
    markEventRead: (eventId) => apiRequest(`/events/${eventId}/read`, { method: 'POST' }),
    markAllEventsRead: () => apiRequest('/events/read-all', { method: 'POST' }),
    clearAllEvents: () => apiRequest('/events', { method: 'DELETE' }),
};

// Update unread count in nav
async function updateUnreadCount() {
    try {
        const data = await apiRequest('/events/unread-count');
        const badge = document.getElementById('unread-count');
        if (badge) {
            if (data.count > 0) {
                badge.textContent = data.count;
                badge.style.display = 'inline-flex';
            } else {
                badge.style.display = 'none';
            }
        }
    } catch (e) {
        console.error('Failed to update unread count:', e);
    }
}

// Update basket count in nav
async function updateBasketCount() {
    try {
        const data = await apiRequest('/basket');
        const badge = document.getElementById('basket-count');
        if (badge) {
            const count = data.items ? data.items.length : 0;
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline-flex';
            } else {
                badge.style.display = 'none';
            }
        }
    } catch (e) {
        console.error('Failed to update basket count:', e);
    }
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

// Format relative time
function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDate(dateString);
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Simple markdown to HTML converter
function markdownToHtml(markdown) {
    let html = escapeHtml(markdown);

    // Handle extended markdown heading syntax with ID: ## Title {#anchor-id}
    // Also generates IDs from heading text if none provided
    function convertHeading(match, hashes, text) {
        const level = hashes.length;
        let id = '';
        let title = text.trim();
        
        // Check for explicit ID syntax {#id}
        const idMatch = title.match(/\s*\{#([^}]+)\}\s*$/);
        if (idMatch) {
            id = idMatch[1];
            title = title.replace(/\s*\{#[^}]+\}\s*$/, '').trim();
        } else {
            // Generate ID from title text (slug format)
            id = title.toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-|-$/g, '')
                .substring(0, 50);
        }
        
        if (title) {
            return `<h${level} id="${id}">${title}</h${level}>`;
        }
        return '';  // Skip empty headings
    }
    
    // Headers with optional {#id} syntax - process from h3 down to h1
    html = html.replace(/^(###) (.+)$/gm, convertHeading);
    html = html.replace(/^(##) (.+)$/gm, convertHeading);
    html = html.replace(/^(#) (.+)$/gm, convertHeading);
    
    // Remove standalone hash marks (malformed headings from bad conversion)
    html = html.replace(/^#{1,6}\s*$/gm, '');

    // Convert standalone anchor markers {#id} to span anchors
    html = html.replace(/\{#([^}]+)\}/g, '<span id="$1"></span>');

    // Bold and italic
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Images MUST come before links: both use [...](...) syntax, so the link
    // regex would match ![alt](url) as [alt](url), leaving a stray "!"
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img alt="$1" src="$2">');

    // Links (after images, see above)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

    // Horizontal rules
    html = html.replace(/^---+$/gm, '<hr>');

    // Line breaks and paragraphs
    html = html.replace(/\n\n+/g, '</p><p>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p><\/p>/g, '');
    html = html.replace(/<p>(<h[1-6])/g, '$1');
    html = html.replace(/(<\/h[1-6]>)<\/p>/g, '$1');
    html = html.replace(/<p>(<hr>)<\/p>/g, '$1');

    return html;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    updateUnreadCount();
    updateBasketCount();

    // Poll for updates every 10 seconds
    setInterval(() => {
        updateUnreadCount();
        updateBasketCount();
    }, 10000);
});
