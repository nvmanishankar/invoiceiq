"""Stage 8: tax, using the model for the buying company's country (cases 8.1-8.8)."""

from app.pipeline.context import RunContext, StageResult
from app.tax import get_tax_model


def run(ctx: RunContext) -> StageResult:
    if ctx.vendor is None:
        return StageResult("info", "Skipped: vendor unknown, so the expected tax can't be worked out", {})
    model = get_tax_model(ctx.company.country)
    result = model.check(ctx)
    result.details.setdefault("model", model.name)
    return result
