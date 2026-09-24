"""Tax models by the buying company's country. India is validated; others use PO-declared rates."""

from app.tax.india_gst import IndiaGST
from app.tax.manual import ManualTax

MODELS = {"IN": IndiaGST}


def get_tax_model(country: str | None):
    return MODELS.get(country or "", ManualTax)()
