from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Text Study home page from book.json registry files.")
    parser.add_argument("--text-study-root", type=Path, default=Path("exports/text_study"))
    parser.add_argument("--title", default="USCPA Text Study Home")
    return parser.parse_args()


def read_books(text_study_root: Path) -> list[dict[str, Any]]:
    books_root = text_study_root / "books"
    books: list[dict[str, Any]] = []

    for path in sorted(books_root.glob("*/book.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] skip invalid book.json: {path} ({exc})")
            continue

        book_id = str(data.get("book_id") or path.parent.name)
        title = str(data.get("title") or book_id.replace("_", " ").title())
        reader_href = str(data.get("reader_href") or f"./books/{book_id}/reader.html")
        status = str(data.get("status") or "ready")
        created_at = str(data.get("created_at") or "")
        pages = data.get("pages")

        books.append(
            {
                "book_id": book_id,
                "title": title,
                "reader_href": reader_href,
                "status": status,
                "created_at": created_at,
                "pages": pages,
            }
        )

    return books


def render_home(title: str, books: list[dict[str, Any]]) -> str:
    cards: list[str] = []

    for book in books:
        page_label = ""
        if isinstance(book.get("pages"), int):
            page_label = f'<span class="meta-pill">{book["pages"]} pages</span>'

        created_label = ""
        if book.get("created_at"):
            created_label = f'<span class="meta-pill">{html.escape(str(book["created_at"]))}</span>'

        cards.append(
            f'''      <article class="study-card">
        <div>
          <p class="eyebrow">{html.escape(str(book["book_id"]))}</p>
          <h2>{html.escape(str(book["title"]))}</h2>
          <div class="meta-row">
            {page_label}
            <span class="meta-pill">{html.escape(str(book["status"]))}</span>
            {created_label}
          </div>
        </div>
        <a class="open-link" href="{html.escape(str(book["reader_href"]))}">Open Reader</a>
      </article>'''
        )

    cards_html = "\n".join(cards) if cards else '''      <article class="empty-card">
        <h2>No books yet</h2>
        <p>Run the pipeline to generate a Text Study reader.</p>
      </article>'''

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f3ee;
      --card: #fffdf8;
      --ink: #1f2933;
      --muted: #687385;
      --border: #e3dacb;
      --accent: #8b5e34;
      --accent-dark: #684220;
      --shadow: 0 18px 40px rgba(31, 41, 51, 0.10);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(139, 94, 52, 0.12), transparent 32rem),
        var(--bg);
    }}

    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 56px 28px;
    }}

    .hero {{
      margin-bottom: 28px;
    }}

    .eyebrow {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}

    h1 {{
      margin: 0;
      font-size: clamp(34px, 5vw, 56px);
      line-height: 1.04;
      letter-spacing: -0.04em;
    }}

    .study-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 420px));
      gap: 22px;
      align-items: stretch;
      justify-content: start;
    }}

    .study-card,
    .empty-card {{
      min-height: 230px;
      padding: 26px;
      border: 1px solid var(--border);
      border-radius: 28px;
      background: var(--card);
      box-shadow: var(--shadow);
    }}

    .study-card {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}

    h2 {{
      margin: 0;
      font-size: 26px;
      letter-spacing: -0.02em;
    }}

    .meta-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }}

    .meta-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 5px 10px;
      border-radius: 999px;
      background: #f1eadf;
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
    }}

    .open-link {{
      display: inline-flex;
      width: fit-content;
      align-items: center;
      justify-content: center;
      margin-top: 24px;
      padding: 12px 16px;
      border-radius: 999px;
      background: var(--accent);
      color: white;
      font-weight: 750;
      text-decoration: none;
    }}

    .open-link:hover {{
      background: var(--accent-dark);
    }}

    .empty-card p {{
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <p class="eyebrow">Text Study Library</p>
      <h1>{html.escape(title)}</h1>
    </section>

    <section class="study-grid">
{cards_html}
    </section>
  </main>
</body>
</html>
'''


def main() -> None:
    args = parse_args()
    root = args.text_study_root
    root.mkdir(parents=True, exist_ok=True)

    books = read_books(root)
    output = root / "index.html"
    output.write_text(render_home(args.title, books), encoding="utf-8")
    print(f"[home] wrote {output}")


if __name__ == "__main__":
    main()
