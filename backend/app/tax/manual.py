"""Countries without a tax module: compare with the rate the user declared on the PO (case 8.8)."""

from app.pipeline.context import RunContext, StageResult, summarise

NOTE = "(declared on PO; not independently verified)"


class ManualTax:
    name = "PO-declared rates"

    def check(self, ctx: RunContext) -> StageResult:
        if ctx.po is None:
            return StageResult("info", "Skipped: no PO, so there's no declared rate to compare", {})
        before = len(ctx.findings)
        for pair in ctx.line_pairs:
            rate, po_rate = pair.inv.tax_rate, pair.po_line.tax_rate
            if rate is not None and rate != po_rate:
                ctx.add("8.8", "hold", f"{pair.inv.description}: {rate:g}% on the invoice vs {po_rate:g}% on "
                                       f"{ctx.po.po_id} {NOTE}.", ["Vendor"],
                        {"line": pair.inv.description, "invoice_rate": rate, "po_rate": po_rate})
        holds = ctx.findings[before:]
        if holds:
            return StageResult("warn", summarise(holds), {"model": self.name})
        ctx.add("8.8", "pass", f"Tax rates match {ctx.po.po_id} {NOTE}.", [])
        return StageResult("pass", f"Rates match the PO {NOTE}", {"model": self.name})
