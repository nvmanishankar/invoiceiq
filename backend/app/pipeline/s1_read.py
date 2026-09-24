"""Stage 1: open the PDF, read the text layer, detect scans (cases 1.2, 1.3)."""

import io

import pdfplumber

from app.pipeline.context import RunContext, StageResult

MIN_CHARS_PER_PAGE = 50  # below this the page is treated as an image


def run(ctx: RunContext) -> StageResult:
    try:
        with pdfplumber.open(io.BytesIO(ctx.file_bytes)) as pdf:
            texts = [(p.extract_text() or "") for p in pdf.pages]
    except Exception:
        texts = None
    if not texts:
        ctx.halt = True
        ctx.add("1.3", "reject", "The file can't be opened (corrupt or password-protected).", ["AP"])
        return StageResult("fail", "File can't be opened", {})

    ctx.page_count = len(texts)
    ctx.text = "\n".join(texts)
    chars = len(ctx.text.strip())
    ctx.is_scan = chars < MIN_CHARS_PER_PAGE * ctx.page_count
    if ctx.is_scan:
        ctx.add("1.2", "info", "This is a scanned image, so it was read visually.", [], {"chars": chars})
    kind = "Scanned image, will read visually" if ctx.is_scan else "Text PDF"
    return StageResult("pass", f"{kind}, {ctx.page_count} page(s)", {"chars": chars, "pages": ctx.page_count, "scanned": ctx.is_scan})
