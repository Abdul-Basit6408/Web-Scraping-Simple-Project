

from datetime import datetime
from html.parser import HTMLParser
import json
import os
import html
import webbrowser
import threading
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None
    ttk = None
    filedialog = None
    messagebox = None


def fetch_html(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(str(exc)) from exc


class BooksParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.books = []
        self._in_article = False
        self._capture_price = False
        self._current_book = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "article" and "product_pod" in attrs.get("class", ""):
            self._in_article = True
            self._current_book = {}
            return

        if not self._in_article or self._current_book is None:
            return

        if tag == "a" and "title" in attrs:
            self._current_book["title"] = attrs["title"]
            return

        if tag == "p":
            classes = attrs.get("class", "")
            if "price_color" in classes:
                self._capture_price = True
            elif "star-rating" in classes:
                rating_class = next(
                    (item for item in classes.split() if item != "star-rating"),
                    "",
                )
                rating_map = {
                    "One": "⭐",
                    "Two": "⭐⭐",
                    "Three": "⭐⭐⭐",
                    "Four": "⭐⭐⭐⭐",
                    "Five": "⭐⭐⭐⭐⭐",
                }
                self._current_book["rating"] = rating_map.get(rating_class, "?")

    def handle_data(self, data):
        if self._capture_price and self._current_book is not None:
            self._current_book["price"] = data.strip()

    def handle_endtag(self, tag):
        if tag == "p" and self._capture_price:
            self._capture_price = False

        if tag == "article" and self._in_article:
            self._in_article = False
            if self._current_book:
                self._current_book.setdefault("price", "")
                self._current_book.setdefault("rating", "?")
                self._current_book.setdefault("title", "")
                self.books.append(self._current_book)
            self._current_book = None


class QuotesParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.quotes = []
        self.has_next = False
        self._in_quote = False
        self._capture_text = False
        self._capture_author = False
        self._current_quote = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "li" and attrs.get("class") == "next":
            self.has_next = True

        if tag == "div" and attrs.get("class") == "quote":
            self._in_quote = True
            self._current_quote = {"tags": []}
            return

        if not self._in_quote or self._current_quote is None:
            return

        if tag == "span" and attrs.get("class") == "text":
            self._capture_text = True
            return

        if tag == "small" and attrs.get("class") == "author":
            self._capture_author = True
            return

        if tag == "a" and attrs.get("class") == "tag":
            self._current_quote["_capture_tag"] = True

    def handle_data(self, data):
        if self._current_quote is None:
            return

        if self._capture_text:
            self._current_quote["text"] = self._current_quote.get("text", "") + data
        elif self._capture_author:
            self._current_quote["author"] = self._current_quote.get("author", "") + data
        elif self._current_quote.get("_capture_tag"):
            self._current_quote.setdefault("tags", []).append(data)

    def handle_endtag(self, tag):
        if tag == "span" and self._capture_text:
            self._capture_text = False

        if tag == "small" and self._capture_author:
            self._capture_author = False

        if tag == "a" and self._current_quote is not None:
            self._current_quote.pop("_capture_tag", None)

        if tag == "div" and self._in_quote:
            self._in_quote = False
            if self._current_quote:
                self._current_quote.setdefault("text", "")
                self._current_quote.setdefault("author", "")
                self._current_quote.setdefault("tags", [])
                self.quotes.append(self._current_quote)
            self._current_quote = None


# ── SCRAPER 1: Books ─────────────────────────────────────────
def scrape_books():
    print("📚 Scraping books...")
    try:
        html_text = fetch_html("https://books.toscrape.com/")
    except RuntimeError as e:
        print("❌ Books request failed:", e)
        return []

    parser = BooksParser()
    parser.feed(html_text)
    books = parser.books

    print(f"   ✅ {len(books)} books collected.")
    return books


# ── SCRAPER 2: Quotes ────────────────────────────────────────
def scrape_quotes():
    print("💬 Scraping quotes...")
    quotes = []
    page = 1

    while True:
        try:
            html_text = fetch_html(f"https://quotes.toscrape.com/page/{page}/")
        except RuntimeError:
            break

        parser = QuotesParser()
        parser.feed(html_text)
        quotes.extend(
            {
                "text": quote.get("text", "").strip(),
                "author": quote.get("author", "").strip(),
                "tags": [tag.strip() for tag in quote.get("tags", []) if tag.strip()],
            }
            for quote in parser.quotes
        )

        if not parser.has_next:
            break

        page += 1

    print(f"   ✅ {len(quotes)} quotes collected.")
    return quotes


# ── HTML BUILDER ─────────────────────────────────────────────
def build_html(books, quotes):
    timestamp = datetime.now().strftime("%d %B %Y, %I:%M %p")

    # Books rows
    book_rows = ""
    for i, b in enumerate(books, 1):
        row_class = "even" if i % 2 == 0 else "odd"
        book_rows += f"""
        <tr class="{row_class}">
            <td class="num">{i}</td>
            <td class="title">{html.escape(b['title'])}</td>
            <td class="price">{b['price']}</td>
            <td class="rating">{b['rating']}</td>
        </tr>"""

    # Quotes rows
    quote_rows = ""
    for i, q in enumerate(quotes, 1):
        row_class = "even" if i % 2 == 0 else "odd"
        tag_pills = "".join(f'<span class="pill">{t}</span>' for t in q["tags"])

        quote_rows += f"""
        <tr class="{row_class}">
            <td class="num">{i}</td>
            <td class="quote-text">{html.escape(q['text'])}</td>
            <td class="author">{q['author']}</td>
            <td class="tags">{tag_pills}</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Web Scraper Report</title>
</head>
<body>
<h1>Web Scraper Report</h1>
<p>Generated: {timestamp}</p>

<h2>Books ({len(books)})</h2>
<table border="1">
<tr><th>#</th><th>Title</th><th>Price</th><th>Rating</th></tr>
{book_rows}
</table>

<h2>Quotes ({len(quotes)})</h2>
<table border="1">
<tr><th>#</th><th>Quote</th><th>Author</th><th>Tags</th></tr>
{quote_rows}
</table>

</body>
</html>"""

    return html_content


def save_report(output_file, books, quotes):
    html_data = build_html(books, quotes)
    with open(output_file, "w", encoding="utf-8") as file_handle:
        file_handle.write(html_data)
    return html_data


def build_browser_app_html(report_name):
        return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
<title>Web Scraper Studio</title>
<style>
    :root {{
        color-scheme: light;
        --bg: #f5efe6;
        --panel: rgba(255, 255, 255, 0.76);
        --panel-strong: #ffffff;
        --text: #1f2328;
        --muted: #667085;
        --accent: #0f766e;
        --accent-2: #b45309;
        --line: rgba(31, 35, 40, 0.12);
        --shadow: 0 18px 60px rgba(15, 23, 42, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
        margin: 0;
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
        color: var(--text);
        background:
            radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 32%),
            radial-gradient(circle at top right, rgba(180, 83, 9, 0.16), transparent 28%),
            linear-gradient(180deg, #fbf7f2, var(--bg));
        min-height: 100vh;
    }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 28px; }}
    .hero {{
        display: grid;
        gap: 18px;
        grid-template-columns: minmax(0, 1.8fr) minmax(320px, 1fr);
        align-items: stretch;
    }}
    .panel {{
        background: var(--panel);
        backdrop-filter: blur(16px);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: var(--shadow);
    }}
    .hero-copy {{ padding: 28px; }}
    .eyebrow {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(15, 118, 110, 0.12);
        color: var(--accent);
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }}
    h1 {{ margin: 14px 0 10px; font-size: clamp(34px, 5vw, 60px); line-height: 0.95; letter-spacing: -0.05em; }}
    .lede {{ margin: 0; color: var(--muted); max-width: 68ch; font-size: 16px; line-height: 1.55; }}
    .hero-aside {{ padding: 24px; display: grid; gap: 14px; }}
    .stats {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .stat {{ background: var(--panel-strong); border: 1px solid var(--line); border-radius: 18px; padding: 16px; }}
    .stat b {{ display: block; font-size: 24px; margin-bottom: 6px; }}
    .stat span {{ color: var(--muted); font-size: 13px; }}
    .controls {{ margin-top: 18px; display: grid; gap: 12px; grid-template-columns: repeat(12, minmax(0, 1fr)); }}
    .field {{ display: grid; gap: 6px; grid-column: span 4; }}
    .field.wide {{ grid-column: span 6; }}
    label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
    input {{
        width: 100%;
        padding: 14px 14px;
        border-radius: 14px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.9);
        font: inherit;
    }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
    button, .link-button {{
        appearance: none;
        border: 0;
        border-radius: 14px;
        padding: 13px 16px;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
    }}
    .primary {{ background: var(--accent); color: white; }}
    .secondary {{ background: #fff; color: var(--text); border: 1px solid var(--line); }}
    .ghost {{ background: rgba(15, 118, 110, 0.08); color: var(--accent); }}
    .workspace {{ margin-top: 18px; display: grid; gap: 16px; grid-template-columns: 1fr; }}
    .section {{ padding: 20px; }}
    .section-head {{ display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 14px; }}
    .section-head h2 {{ margin: 0; font-size: 20px; }}
    .section-head p {{ margin: 0; color: var(--muted); }}
    .tables {{ display: grid; gap: 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 18px; overflow: hidden; border: 1px solid var(--line); }}
    thead th {{ text-align: left; background: #f7f8fa; color: #4b5563; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; padding: 14px 16px; position: sticky; top: 0; }}
    tbody td {{ padding: 14px 16px; border-top: 1px solid var(--line); vertical-align: top; }}
    tbody tr:nth-child(even) {{ background: rgba(15, 118, 110, 0.03); }}
    .tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .pill {{ padding: 6px 10px; border-radius: 999px; background: rgba(180, 83, 9, 0.12); color: var(--accent-2); font-size: 12px; font-weight: 700; }}
    .quote-text {{ max-width: 72ch; }}
    .log {{ height: 180px; overflow: auto; padding: 16px; background: #101722; color: #d1e7e5; border-radius: 18px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }}
    .muted {{ color: var(--muted); }}
    .busy {{ opacity: 0.6; pointer-events: none; }}
    .bar {{ margin-top: 12px; height: 8px; border-radius: 999px; background: rgba(15, 118, 110, 0.12); overflow: hidden; }}
    .bar > div {{ width: 0%; height: 100%; background: linear-gradient(90deg, var(--accent), #14b8a6); transition: width 180ms ease; }}
    @media (max-width: 980px) {{
        .hero {{ grid-template-columns: 1fr; }}
        .field, .field.wide {{ grid-column: span 12; }}
        .stats {{ grid-template-columns: 1fr; }}
    }}
</style>
</head>
<body>
    <div class="shell">
        <div class="hero">
            <section class="panel hero-copy">
                <div class="eyebrow">Interactive Mac scraper</div>
                <h1>Web Scraper Studio</h1>
                <p class="lede">Scrape books and quotes, filter the results live, and export a local HTML report. Everything runs on your machine, so this works cleanly on macOS without extra packages.</p>

                <div class="controls">
                    <div class="field wide">
                        <label for="reportName">Report name</label>
                        <input id="reportName" value="{html.escape(report_name)}" />
                    </div>
                    <div class="field">
                        <label for="bookFilter">Book filter</label>
                        <input id="bookFilter" placeholder="Title or keyword" />
                    </div>
                    <div class="field">
                        <label for="quoteFilter">Quote filter</label>
                        <input id="quoteFilter" placeholder="Text, author, or tag" />
                    </div>
                    <div class="field wide">
                        <label>Saved report</label>
                        <div class="muted" id="reportStatus">The first scrape will create the report.</div>
                    </div>
                </div>

                <div class="actions">
                    <button class="primary" id="scrapeAll">Scrape All</button>
                    <button class="secondary" id="scrapeBooks">Books Only</button>
                    <button class="secondary" id="scrapeQuotes">Quotes Only</button>
                    <a class="link-button ghost" id="openReport" href="#" target="_blank" rel="noreferrer">Open Report</a>
                </div>

                <div class="bar" aria-hidden="true"><div id="progressFill"></div></div>
            </section>

            <aside class="panel hero-aside">
                <div class="stats">
                    <div class="stat"><b id="bookCount">0</b><span>books loaded</span></div>
                    <div class="stat"><b id="quoteCount">0</b><span>quotes loaded</span></div>
                    <div class="stat"><b id="visibleCount">0</b><span>visible rows</span></div>
                </div>
                <div>
                    <div class="muted" style="font-size:12px; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:8px;">Status</div>
                    <div id="statusText" style="font-size:18px; font-weight:700; line-height:1.4;">Ready.</div>
                </div>
                <div class="muted">Open the report after a scrape completes. It is saved locally with the name you choose above.</div>
            </aside>
        </div>

        <main class="workspace">
            <section class="panel section">
                <div class="section-head">
                    <div>
                        <h2>Books</h2>
                        <p>Filter the live table with the search box above.</p>
                    </div>
                    <div class="muted" id="booksVisible">0 visible</div>
                </div>
                <div style="overflow:auto; max-height: 340px;">
                    <table>
                        <thead><tr><th>#</th><th>Title</th><th>Price</th><th>Rating</th></tr></thead>
                        <tbody id="booksBody"></tbody>
                    </table>
                </div>
            </section>

            <section class="panel section">
                <div class="section-head">
                    <div>
                        <h2>Quotes</h2>
                        <p>Search by quote text, author, or tags.</p>
                    </div>
                    <div class="muted" id="quotesVisible">0 visible</div>
                </div>
                <div style="overflow:auto; max-height: 360px;">
                    <table>
                        <thead><tr><th>#</th><th>Quote</th><th>Author</th><th>Tags</th></tr></thead>
                        <tbody id="quotesBody"></tbody>
                    </table>
                </div>
            </section>

            <section class="panel section">
                <div class="section-head">
                    <div>
                        <h2>Activity Log</h2>
                        <p>Each scrape updates this panel.</p>
                    </div>
                </div>
                <div id="log" class="log">Ready.</div>
            </section>
        </main>
    </div>

<script>
    const state = {{ books: [], quotes: [], reportUrl: "", busy: false }};
    const reportName = document.getElementById("reportName");
    const bookFilter = document.getElementById("bookFilter");
    const quoteFilter = document.getElementById("quoteFilter");
    const statusText = document.getElementById("statusText");
    const log = document.getElementById("log");
    const booksBody = document.getElementById("booksBody");
    const quotesBody = document.getElementById("quotesBody");
    const progressFill = document.getElementById("progressFill");
    const booksVisible = document.getElementById("booksVisible");
    const quotesVisible = document.getElementById("quotesVisible");
    const visibleCount = document.getElementById("visibleCount");
    const bookCount = document.getElementById("bookCount");
    const quoteCount = document.getElementById("quoteCount");
    const reportStatus = document.getElementById("reportStatus");
    const openReport = document.getElementById("openReport");
    const controls = document.querySelectorAll("button, input, a");

    function setBusy(isBusy, message) {{
        state.busy = isBusy;
        controls.forEach((node) => {{
            if (node.tagName === "A") {{
                node.style.pointerEvents = isBusy ? "none" : "";
                node.style.opacity = isBusy ? "0.6" : "";
            }} else {{
                node.disabled = isBusy && node.tagName === "BUTTON";
            }}
        }});
        document.body.classList.toggle("busy", isBusy);
        progressFill.style.width = isBusy ? "72%" : "0%";
        if (message) statusText.textContent = message;
    }}

    function addLog(message) {{
        const timestamp = new Date().toLocaleTimeString();
        log.textContent = `[${{timestamp}}] ${{message}}\n` + log.textContent;
    }}

    function matchesBook(book) {{
        const needle = bookFilter.value.trim().toLowerCase();
        return !needle || book.title.toLowerCase().includes(needle);
    }}

    function matchesQuote(quote) {{
        const needle = quoteFilter.value.trim().toLowerCase();
        if (!needle) return true;
        const haystack = `${{quote.text}} ${{quote.author}} ${{quote.tags.join(" ")}}`.toLowerCase();
        return haystack.includes(needle);
    }}

    function render() {{
        booksBody.innerHTML = "";
        quotesBody.innerHTML = "";

        const visibleBooks = state.books.filter(matchesBook);
        const visibleQuotes = state.quotes.filter(matchesQuote);

        visibleBooks.forEach((book, index) => {{
            const row = document.createElement("tr");
            row.innerHTML = `<td>${{index + 1}}</td><td>${{escapeHtml(book.title)}}</td><td>${{escapeHtml(book.price)}}</td><td>${{escapeHtml(book.rating)}}</td>`;
            booksBody.appendChild(row);
        }});

        visibleQuotes.forEach((quote, index) => {{
            const row = document.createElement("tr");
            row.innerHTML = `<td>${{index + 1}}</td><td class="quote-text">${{escapeHtml(quote.text)}}</td><td>${{escapeHtml(quote.author)}}</td><td><div class="tags">${{quote.tags.map((tag) => `<span class="pill">${{escapeHtml(tag)}}</span>`).join("")}}</div></td>`;
            quotesBody.appendChild(row);
        }});

        bookCount.textContent = state.books.length;
        quoteCount.textContent = state.quotes.length;
        booksVisible.textContent = `${{visibleBooks.length}} visible`;
        quotesVisible.textContent = `${{visibleQuotes.length}} visible`;
        visibleCount.textContent = `${{visibleBooks.length + visibleQuotes.length}} visible`;
    }}

    function escapeHtml(value) {{
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }}

    async function scrape(mode) {{
        setBusy(true, `Scraping ${{mode}}...`);
        addLog(`Starting ${{mode}} scrape`);

        try {{
            const response = await fetch(`/api/scrape?mode=${{encodeURIComponent(mode)}}&report=${{encodeURIComponent(reportName.value.trim() || "scraper_report.html")}}`);
            const payload = await response.json();
            if (!response.ok) {{
                throw new Error(payload.error || "Scrape failed");
            }}

            state.books = payload.books || state.books;
            state.quotes = payload.quotes || state.quotes;
            state.reportUrl = payload.report_url || state.reportUrl;
            reportStatus.textContent = payload.report_name ? `Saved as ${{payload.report_name}}` : "Report saved.";
            openReport.href = state.reportUrl;
            statusText.textContent = payload.message;
            addLog(payload.message);
            render();
        }} catch (error) {{
            statusText.textContent = error.message;
            addLog(`Error: ${{error.message}}`);
            alert(error.message);
        }} finally {{
            setBusy(false, statusText.textContent);
        }}
    }}

    document.getElementById("scrapeAll").addEventListener("click", () => scrape("all"));
    document.getElementById("scrapeBooks").addEventListener("click", () => scrape("books"));
    document.getElementById("scrapeQuotes").addEventListener("click", () => scrape("quotes"));
    bookFilter.addEventListener("input", render);
    quoteFilter.addEventListener("input", render);

    render();
</script>
</body>
</html>"""


class ScraperAppServer(ThreadingHTTPServer):
        def __init__(self, server_address, RequestHandlerClass):
                super().__init__(server_address, RequestHandlerClass)
                self.report_path = os.path.join(
                        os.path.expanduser("~"),
                        "Downloads",
                        "scraper_report.html",
                )


class ScraperBrowserHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
                return

        def _send_text(self, text, content_type="text/html; charset=utf-8", status=200):
                encoded = text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        def _send_json(self, payload, status=200):
                body = json.dumps(payload, ensure_ascii=False)
                self._send_text(body, content_type="application/json; charset=utf-8", status=status)

        def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path == "/":
                        report_name = os.path.basename(self.server.report_path)
                        self._send_text(build_browser_app_html(report_name))
                        return

                if parsed.path == "/api/scrape":
                        query = parse_qs(parsed.query)
                        mode = query.get("mode", ["all"])[0]
                        requested_name = query.get("report", [os.path.basename(self.server.report_path)])[0]
                        report_name = os.path.basename(requested_name) or "scraper_report.html"
                        self.server.report_path = os.path.join(
                                os.path.expanduser("~"),
                                "Downloads",
                                report_name,
                        )

                        try:
                                if mode == "books":
                                        books = scrape_books()
                                        quotes = self.server.last_quotes or []
                                elif mode == "quotes":
                                        books = self.server.last_books or []
                                        quotes = scrape_quotes()
                                else:
                                        books = scrape_books()
                                        quotes = scrape_quotes()

                                self.server.last_books = books
                                self.server.last_quotes = quotes

                                save_report(self.server.report_path, books, quotes)

                                payload = {
                                        "ok": True,
                                    "message": f"Saved {len(books)} books and {len(quotes)} quotes.",
                                        "books": books,
                                        "quotes": quotes,
                                    "report_name": report_name,
                                        "report_url": f"http://{self.server.server_address[0]}:{self.server.server_address[1]}/report",
                                }
                                self._send_json(payload)
                        except Exception as exc:
                                self._send_json({"ok": False, "error": str(exc)}, status=500)
                        return

                if parsed.path == "/report":
                        if not os.path.exists(self.server.report_path):
                                self._send_text("Report not created yet.", content_type="text/plain; charset=utf-8", status=404)
                                return

                        with open(self.server.report_path, "r", encoding="utf-8") as file_handle:
                                self._send_text(file_handle.read())
                        return

                self._send_text("Not found.", content_type="text/plain; charset=utf-8", status=404)


def run_browser_gui():
        server = ScraperAppServer(("127.0.0.1", 0), ScraperBrowserHandler)
        server.last_books = []
        server.last_quotes = []

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{server.server_address[1]}/"
        print(f"Interactive GUI available at {url}")
        webbrowser.open(url)

        try:
                thread.join()
        except KeyboardInterrupt:
                server.shutdown()
                server.server_close()


if tk is not None:
    class ScraperApp(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("Web Scraper Studio")
            self.geometry("1120x760")
            self.minsize(980, 680)

            self.books = []
            self.quotes = []
            self.output_file = os.path.join(
                os.path.expanduser("~"),
                "Downloads",
                "scraper_report.html",
            )

            self.filter_books_var = tk.StringVar()
            self.filter_quotes_var = tk.StringVar()
            self.status_var = tk.StringVar(value="Ready.")
            self.output_var = tk.StringVar(value=self.output_file)

            self._build_style()
            self._build_ui()

        def _build_style(self):
            style = ttk.Style(self)
            if "aqua" in style.theme_names():
                style.theme_use("aqua")
            style.configure("Header.TLabel", font=("Helvetica Neue", 18, "bold"))
            style.configure("Subtle.TLabel", foreground="#666666")
            style.configure("Accent.TButton", padding=(14, 8))
            style.configure("Primary.TButton", padding=(14, 8))

        def _build_ui(self):
            container = ttk.Frame(self, padding=18)
            container.pack(fill=tk.BOTH, expand=True)

            top = ttk.Frame(container)
            top.pack(fill=tk.X)

            title_block = ttk.Frame(top)
            title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)

            ttk.Label(title_block, text="Web Scraper Studio", style="Header.TLabel").pack(anchor=tk.W)
            ttk.Label(
                title_block,
                text="Scrape books and quotes, review results live, and export an HTML report.",
                style="Subtle.TLabel",
            ).pack(anchor=tk.W, pady=(4, 0))

            actions = ttk.Frame(top)
            actions.pack(side=tk.RIGHT)

            self.scrape_all_button = ttk.Button(actions, text="Scrape All", style="Primary.TButton", command=self.scrape_all)
            self.scrape_all_button.grid(row=0, column=0, padx=(0, 8))

            self.scrape_books_button = ttk.Button(actions, text="Books Only", command=self.scrape_books_only)
            self.scrape_books_button.grid(row=0, column=1, padx=(0, 8))

            self.scrape_quotes_button = ttk.Button(actions, text="Quotes Only", command=self.scrape_quotes_only)
            self.scrape_quotes_button.grid(row=0, column=2, padx=(0, 8))

            self.open_report_button = ttk.Button(actions, text="Open Report", command=self.open_report)
            self.open_report_button.grid(row=0, column=3)

            options = ttk.Frame(container, padding=(0, 16, 0, 12))
            options.pack(fill=tk.X)

            ttk.Label(options, text="Book filter:").grid(row=0, column=0, sticky=tk.W)
            book_entry = ttk.Entry(options, textvariable=self.filter_books_var)
            book_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 16))
            book_entry.bind("<KeyRelease>", lambda _event: self.refresh_tables())

            ttk.Label(options, text="Quote filter:").grid(row=0, column=2, sticky=tk.W)
            quote_entry = ttk.Entry(options, textvariable=self.filter_quotes_var)
            quote_entry.grid(row=0, column=3, sticky=tk.EW, padx=(8, 16))
            quote_entry.bind("<KeyRelease>", lambda _event: self.refresh_tables())

            ttk.Label(options, text="Report path:").grid(row=0, column=4, sticky=tk.W)
            output_entry = ttk.Entry(options, textvariable=self.output_var)
            output_entry.grid(row=0, column=5, sticky=tk.EW, padx=(8, 8))

            browse_button = ttk.Button(options, text="Browse", command=self.choose_output)
            browse_button.grid(row=0, column=6)

            options.columnconfigure(1, weight=1)
            options.columnconfigure(3, weight=1)
            options.columnconfigure(5, weight=2)

            self.progress = ttk.Progressbar(container, mode="indeterminate")
            self.progress.pack(fill=tk.X, pady=(0, 10))

            tabs = ttk.Notebook(container)
            tabs.pack(fill=tk.BOTH, expand=True)

            self.books_frame = ttk.Frame(tabs, padding=8)
            self.quotes_frame = ttk.Frame(tabs, padding=8)
            tabs.add(self.books_frame, text="Books")
            tabs.add(self.quotes_frame, text="Quotes")

            self._build_books_table()
            self._build_quotes_table()

            log_frame = ttk.LabelFrame(container, text="Activity", padding=10)
            log_frame.pack(fill=tk.BOTH, expand=False, pady=(14, 0))

            self.log_text = tk.Text(log_frame, height=7, wrap=tk.WORD, relief=tk.FLAT)
            self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
            log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self.log_text.configure(yscrollcommand=log_scroll.set)

            status_bar = ttk.Frame(container)
            status_bar.pack(fill=tk.X, pady=(10, 0))
            ttk.Label(status_bar, textvariable=self.status_var).pack(anchor=tk.W)

        def _build_books_table(self):
            filter_frame = ttk.Frame(self.books_frame)
            filter_frame.pack(fill=tk.X, pady=(0, 8))
            ttk.Label(filter_frame, text="Live title search updates this table.", style="Subtle.TLabel").pack(anchor=tk.W)

            columns = ("#", "title", "price", "rating")
            self.books_tree = ttk.Treeview(self.books_frame, columns=columns, show="headings", height=16)
            headings = {
                "#": "#",
                "title": "Title",
                "price": "Price",
                "rating": "Rating",
            }
            widths = {"#": 60, "title": 620, "price": 120, "rating": 120}
            for column in columns:
                self.books_tree.heading(column, text=headings[column])
                self.books_tree.column(column, width=widths[column], anchor=tk.W)

            scrollbar = ttk.Scrollbar(self.books_frame, orient=tk.VERTICAL, command=self.books_tree.yview)
            self.books_tree.configure(yscrollcommand=scrollbar.set)
            self.books_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _build_quotes_table(self):
            filter_frame = ttk.Frame(self.quotes_frame)
            filter_frame.pack(fill=tk.X, pady=(0, 8))
            ttk.Label(filter_frame, text="Live text and author search updates this table.", style="Subtle.TLabel").pack(anchor=tk.W)

            columns = ("#", "text", "author", "tags")
            self.quotes_tree = ttk.Treeview(self.quotes_frame, columns=columns, show="headings", height=16)
            headings = {
                "#": "#",
                "text": "Quote",
                "author": "Author",
                "tags": "Tags",
            }
            widths = {"#": 60, "text": 620, "author": 180, "tags": 260}
            for column in columns:
                self.quotes_tree.heading(column, text=headings[column])
                self.quotes_tree.column(column, width=widths[column], anchor=tk.W)

            scrollbar = ttk.Scrollbar(self.quotes_frame, orient=tk.VERTICAL, command=self.quotes_tree.yview)
            self.quotes_tree.configure(yscrollcommand=scrollbar.set)
            self.quotes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def choose_output(self):
            path = filedialog.asksaveasfilename(
                initialdir=os.path.expanduser("~") + "/Downloads",
                initialfile="scraper_report.html",
                defaultextension=".html",
                filetypes=[("HTML files", "*.html"), (
                    "All files", "*.*"
                )],
            )
            if path:
                self.output_file = path
                self.output_var.set(path)

        def append_log(self, message):
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)

        def set_busy(self, busy, message=None):
            state = tk.DISABLED if busy else tk.NORMAL
            for button in (
                self.scrape_all_button,
                self.scrape_books_button,
                self.scrape_quotes_button,
                self.open_report_button,
            ):
                button.configure(state=state)

            if busy:
                self.progress.start(12)
            else:
                self.progress.stop()

            if message:
                self.status_var.set(message)

        def scrape_all(self):
            self._start_job("all")

        def scrape_books_only(self):
            self._start_job("books")

        def scrape_quotes_only(self):
            self._start_job("quotes")

        def _start_job(self, mode):
            self.set_busy(True, "Scraping in progress...")
            self.append_log(f"Starting {mode} scrape...")

            thread = threading.Thread(target=self._worker, args=(mode,), daemon=True)
            thread.start()

        def _worker(self, mode):
            result = {"books": self.books, "quotes": self.quotes, "error": None}

            try:
                if mode in ("all", "books"):
                    result["books"] = scrape_books()
                if mode in ("all", "quotes"):
                    result["quotes"] = scrape_quotes()

                result["html"] = save_report(self.output_file, result["books"], result["quotes"])
            except Exception as exc:
                result["error"] = str(exc)

            self.after(0, lambda: self._finish_job(mode, result))

        def _finish_job(self, mode, result):
            self.set_busy(False)

            if result["error"]:
                self.status_var.set("Scrape failed.")
                self.append_log(f"Error: {result['error']}")
                if messagebox is not None:
                    messagebox.showerror("Scrape failed", result["error"])
                return

            self.books = result["books"]
            self.quotes = result["quotes"]
            self.refresh_tables()
            self.status_var.set(
                f"Saved {len(self.books)} books and {len(self.quotes)} quotes to {self.output_file}"
            )
            self.append_log(self.status_var.get())
            webbrowser.open(f"file://{self.output_file}")

        def refresh_tables(self):
            book_filter = self.filter_books_var.get().strip().lower()
            quote_filter = self.filter_quotes_var.get().strip().lower()

            for row in self.books_tree.get_children():
                self.books_tree.delete(row)
            for index, book in enumerate(self.books, 1):
                if book_filter and book_filter not in book["title"].lower():
                    continue
                self.books_tree.insert(
                    "",
                    tk.END,
                    values=(index, book["title"], book["price"], book["rating"]),
                )

            for row in self.quotes_tree.get_children():
                self.quotes_tree.delete(row)
            for index, quote in enumerate(self.quotes, 1):
                searchable = " ".join([quote["text"], quote["author"], " ".join(quote["tags"])]).lower()
                if quote_filter and quote_filter not in searchable:
                    continue
                self.quotes_tree.insert(
                    "",
                    tk.END,
                    values=(index, quote["text"], quote["author"], ", ".join(quote["tags"])),
                )

        def open_report(self):
            if os.path.exists(self.output_file):
                webbrowser.open(f"file://{self.output_file}")
                return

            if messagebox is not None:
                messagebox.showinfo("Open Report", "The report has not been created yet.")


def run_gui():
    if tk is not None:
        try:
            app = ScraperApp()
            app.mainloop()
            return
        except Exception:
            pass

    run_browser_gui()


# ── MAIN ─────────────────────────────────────────────────────
if __name__ == "__main__":
    run_gui()