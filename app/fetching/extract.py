"""HTML/PDF → plain text extraction + deterministic truncation.

No LLM anywhere in this module: truncation is code, so one source
verification costs exactly one fixed-size prompt (docs/04 §2 cost
discipline).
"""
import io
import re
from html.parser import HTMLParser

from pypdf import PdfReader

MAX_FETCH_CHARS = 12_000
HEAD_CHARS = 10_000
TAIL_CHARS = 2_000
TRUNCATION_MARKER = "\n\n[... middle of document truncated ...]\n\n"
MAX_PDF_PAGES = 60

# Tags whose text we keep. Everything else (nav soup, link lists) is
# dropped so the model sees the document's actual prose.
_KEEP_TAGS = ("title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li")
_SKIP_TAGS = ("script", "style")


class _TextExtractor(HTMLParser):
    """Collect text inside kept tags; drop script/style entirely."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _KEEP_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _KEEP_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def _collapse(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def html_to_text(html: str) -> str:
    """Extract title/headings/paragraph text; collapse whitespace.

    Malformed HTML never raises — whatever was collected is returned.
    """
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass  # keep partial text from a broken page
    return _collapse(" ".join(parser.parts))


def pdf_to_text(data: bytes) -> str:
    """Extract text from a PDF, capped at MAX_PDF_PAGES pages.

    A page that fails to extract is skipped (empty string), not fatal.
    Raises only if the PDF is unreadable at the file level — the caller
    turns that into an explicit fetch failure.
    """
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")  # one broken page must not kill the extract
    return _collapse("\n".join(parts))


def truncate(text: str) -> str:
    """Deterministic, head-biased truncation to MAX_FETCH_CHARS.

    Head-biased on purpose: references and conclusions live at the END
    of documents, so the tail is kept too. This is code, never an LLM
    summarization call.
    """
    if len(text) <= MAX_FETCH_CHARS:
        return text
    head = text[:HEAD_CHARS]
    tail = text[len(text) - TAIL_CHARS:]
    return head + TRUNCATION_MARKER + tail
