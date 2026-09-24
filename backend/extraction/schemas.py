"""Extraction contracts -- spec extraction/schemas.py.

The canonical field vocabulary and the shape a vision provider must return.
Defining this once, strictly, is what lets Claude, Gemini and the mock provider
be interchangeable: they all have to produce the same structure or fail
validation, so a provider swap can never silently change pipeline semantics.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Canonical field vocabulary -- every mandatory declaration under the
# Legal Metrology (Packaged Commodities) Rules, 2011
# ---------------------------------------------------------------------------
FIELD_NAMES = (
    "mrp",
    "net_quantity",
    "unit_price",
    "mfg_date",
    "expiry_date",
    "manufacturer_name",
    "manufacturer_address",
    "country_of_origin",
    "customer_care",
    "fssai_licence",
    "batch_number",
    "product_name",
    "brand_name",
)

FIELD_LABELS: dict[str, str] = {
    "mrp": "Maximum Retail Price",
    "net_quantity": "Net Quantity",
    "unit_price": "Unit Sale Price",
    "mfg_date": "Month & Year of Manufacture",
    "expiry_date": "Best Before / Use By",
    "manufacturer_name": "Name of Manufacturer / Packer / Importer",
    "manufacturer_address": "Address of Manufacturer / Packer",
    "country_of_origin": "Country of Origin",
    "customer_care": "Consumer Care Details",
    "fssai_licence": "FSSAI Licence Number",
    "batch_number": "Batch / Lot Number",
    "product_name": "Name of Commodity",
    "brand_name": "Brand Name",
}

SurfaceLiteral = Literal["FRONT", "BACK", "SIDE", "BOTTOM", "CAP", "DIE_LINE"]


class BoundingBox(BaseModel):
    """Box in the coordinate space of the image the model was shown."""

    model_config = ConfigDict(extra="ignore")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @classmethod
    def from_any(cls, data: Any) -> "BoundingBox | None":
        """Accept the several shapes models actually emit.

        Providers are inconsistent -- dicts keyed x/y/w/h, [x0,y0,x1,y1] lists,
        or normalised 0-1000 coordinates. Normalising here keeps that mess out
        of the pipeline.
        """
        if data is None:
            return None
        try:
            if isinstance(data, dict):
                if {"x", "y", "width", "height"} <= data.keys():
                    return cls(
                        x=int(data["x"]), y=int(data["y"]),
                        width=int(data["width"]), height=int(data["height"]),
                    )
                if {"x0", "y0", "x1", "y1"} <= data.keys():
                    x0, y0, x1, y1 = (int(data[k]) for k in ("x0", "y0", "x1", "y1"))
                    return cls(x=x0, y=y0, width=max(1, x1 - x0), height=max(1, y1 - y0))
                if {"left", "top", "right", "bottom"} <= data.keys():
                    x0, y0 = int(data["left"]), int(data["top"])
                    x1, y1 = int(data["right"]), int(data["bottom"])
                    return cls(x=x0, y=y0, width=max(1, x1 - x0), height=max(1, y1 - y0))
            if isinstance(data, (list, tuple)) and len(data) == 4:
                x0, y0, x1, y1 = (int(v) for v in data)
                if x1 > x0 and y1 > y0:
                    return cls(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
                return cls(x=x0, y=y0, width=max(1, x1), height=max(1, y1))
        except (TypeError, ValueError):
            return None
        return None

    def scaled(self, fx: float, fy: float) -> "BoundingBox":
        return BoundingBox(
            x=int(self.x * fx), y=int(self.y * fy),
            width=max(1, int(self.width * fx)), height=max(1, int(self.height * fy)),
        )


class ExtractedFieldSchema(BaseModel):
    """One declaration the vision model claims to have read."""

    model_config = ConfigDict(extra="ignore")

    field_name: str
    value: str | None = None
    bbox: BoundingBox | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    surface: str | None = None
    is_present: bool = True
    notes: str | None = None

    @field_validator("field_name")
    @classmethod
    def _known_field(cls, v: str) -> str:
        key = v.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "maximum_retail_price": "mrp", "retail_sale_price": "mrp", "price": "mrp",
            "mrp_inclusive": "mrp", "net_weight": "net_quantity", "quantity": "net_quantity",
            "net_qty": "net_quantity", "unit_sale_price": "unit_price",
            "price_per_unit": "unit_price", "manufacture_date": "mfg_date",
            "date_of_manufacture": "mfg_date", "packed_on": "mfg_date",
            "best_before": "expiry_date", "use_by": "expiry_date",
            "expiry": "expiry_date", "manufacturer": "manufacturer_name",
            "packer": "manufacturer_name", "address": "manufacturer_address",
            "origin": "country_of_origin", "consumer_care": "customer_care",
            "customer_care_details": "customer_care", "fssai": "fssai_licence",
            "fssai_number": "fssai_licence", "fssai_license": "fssai_licence",
            "batch": "batch_number", "lot_number": "batch_number",
            "commodity_name": "product_name", "brand": "brand_name",
        }
        return aliases.get(key, key)

    @field_validator("value")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = re.sub(r"\s+", " ", str(v)).strip()
        # Models sometimes say "not found" instead of returning null.
        if s.lower() in ("", "none", "null", "n/a", "na", "not found",
                         "not present", "not visible", "absent", "-"):
            return None
        return s


class VisionExtractionResult(BaseModel):
    """A provider's complete reading of one surface."""

    model_config = ConfigDict(extra="ignore")

    fields: list[ExtractedFieldSchema] = Field(default_factory=list)
    surface_type: str | None = None
    provider: str = "unknown"
    model: str | None = None
    raw_response: str | None = None
    latency_ms: int = 0
    tokens_used: int | None = None
    error: str | None = None
    image_size: tuple[int, int] | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    def by_name(self) -> dict[str, ExtractedFieldSchema]:
        """Latest wins if a provider repeats a field."""
        return {f.field_name: f for f in self.fields}

    def present_fields(self) -> dict[str, str]:
        return {
            f.field_name: f.value
            for f in self.fields
            if f.is_present and f.value is not None
        }


class SurfaceExtraction(BaseModel):
    """Per-surface record carried through the pipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    surface_type: str
    image_key: str
    sha256: str
    result: VisionExtractionResult
    unwarp_method: str = "none"
    px_per_mm: float | None = None


# ---------------------------------------------------------------------------
# The instruction given to every vision provider
# ---------------------------------------------------------------------------
EXTRACTION_SYSTEM_PROMPT = """\
You are a Legal Metrology compliance inspector examining a photograph of Indian \
packaged-commodity labelling under the Legal Metrology (Packaged Commodities) \
Rules, 2011.

Read ONLY what is physically printed on the package. Your output becomes evidence \
in a statutory enforcement proceeding, so accuracy matters far more than \
completeness.

Rules you must follow:
1. Transcribe values EXACTLY as printed, including currency symbols and units.
2. If a declaration is not visible on this surface, return it with \
"is_present": false and "value": null. NEVER infer, complete, or guess a value \
from product knowledge -- a plausible invention is worse than a reported absence.
3. Give a tight bounding box around the printed text for every field you DO find, \
in pixels of the image as supplied.
4. Confidence must reflect how clearly you can actually read the text: 0.9+ only \
for crisp unambiguous print, below 0.6 when blur, glare or curvature leaves you \
uncertain.
5. Report partially obscured text as what you can see, and say so in "notes".

Respond with JSON only -- no prose, no markdown fences."""


EXTRACTION_USER_PROMPT = """\
Extract these declarations from the {surface} surface of this package.

Fields to look for:
- mrp                     Maximum/Retail Sale Price, e.g. "MRP Rs. 45.00 (incl. of all taxes)"
- net_quantity            Net quantity with unit, e.g. "250 g", "1 L", "10 N"
- unit_price              Unit sale price, e.g. "Rs. 0.18 per g"
- mfg_date                Month and year of manufacture/packing, e.g. "03/2026"
- expiry_date             Best before / use by date
- manufacturer_name       Name of manufacturer, packer or importer
- manufacturer_address    Full address including PIN code
- country_of_origin       Country of origin
- customer_care           Consumer care phone and/or email
- fssai_licence           14-digit FSSAI licence number
- batch_number            Batch or lot number
- product_name            Name of the commodity
- brand_name              Brand name

Image dimensions: {width} x {height} pixels.

Return exactly this JSON structure:
{{
  "fields": [
    {{
      "field_name": "mrp",
      "value": "Rs. 45.00",
      "bbox": {{"x": 120, "y": 340, "width": 210, "height": 48}},
      "confidence": 0.95,
      "is_present": true,
      "notes": null
    }}
  ]
}}

Include an entry for EVERY field listed above. Use "is_present": false with \
"value": null and "bbox": null for anything not visible on this surface."""
