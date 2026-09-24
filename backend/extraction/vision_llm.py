"""Vision LLM extraction -- spec extraction/vision_llm.py.

Three interchangeable providers behind one interface:

  ClaudeVisionProvider   Anthropic Claude Vision -- the configured primary
  GeminiVisionProvider   Google Gemini Vision
  MockVisionProvider     deterministic offline extraction for demos and tests

The model *proposes*; nothing here is trusted on its own.  Every value it
returns is re-read by deterministic OCR against the same pixel crop
(ocr_verify) and then cross-checked arithmetically by the rules engine.  That
is the guarantee the architecture rests on: an AI hallucination cannot become a
legal notice, because a hallucinated value has no pixels to corroborate it.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
from abc import ABC, abstractmethod

import numpy as np

from app.config import settings
from extraction.schemas import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT,
    FIELD_NAMES,
    BoundingBox,
    ExtractedFieldSchema,
    VisionExtractionResult,
)

logger = logging.getLogger("metrix.vision")

# Downscale before upload: full-resolution phone photos cost tokens and latency
# without improving reading accuracy on declarations this size.
MAX_EDGE_PX = 1568


def _encode(image: np.ndarray, fmt: str = "JPEG", quality: int = 90) -> tuple[str, tuple[int, int], float]:
    """Encode to base64, returning the sent size and the scale that was applied."""
    from PIL import Image

    pil = Image.fromarray(image.astype(np.uint8))
    original = pil.size
    scale = 1.0
    if max(pil.size) > MAX_EDGE_PX:
        scale = MAX_EDGE_PX / max(pil.size)
        pil = pil.resize(
            (max(1, int(pil.width * scale)), max(1, int(pil.height * scale))),
            Image.LANCZOS,
        )
    buf = io.BytesIO()
    pil.save(buf, format=fmt, quality=quality)
    logger.debug("Encoded %s -> %s (scale %.3f)", original, pil.size, scale)
    return base64.b64encode(buf.getvalue()).decode(), pil.size, scale


def _encode_within(
    image: np.ndarray, max_bytes: int, quality: int = 88,
) -> tuple[str, tuple[int, int], float]:
    """Encode to base64 while staying under a byte budget.

    NVIDIA's inline-image path rejects anything much above ~180 KB and directs
    you to its asset-upload API instead. For a single pack photograph, stepping
    the quality and then the long edge down until it fits is far simpler than a
    two-step upload, and the loss is mostly in flat background rather than in
    the printed text the extractor cares about.

    Returns the same triple as `_encode` so the caller's coordinate mapping is
    unchanged: the scale is what maps a model-space box back to original pixels.
    """
    from PIL import Image

    pil = Image.fromarray(image.astype(np.uint8))
    original_edge = max(pil.size)
    edge = min(original_edge, MAX_EDGE_PX)

    # Quality first: it costs no spatial detail, which is what OCR needs most.
    for edge_attempt in range(4):
        working = pil
        if max(pil.size) > edge:
            ratio = edge / max(pil.size)
            working = pil.resize(
                (max(1, int(pil.width * ratio)), max(1, int(pil.height * ratio))),
                Image.LANCZOS,
            )
        for q in (quality, 75, 62, 50):
            buf = io.BytesIO()
            working.save(buf, format="JPEG", quality=q, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                scale = working.size[0] / pil.size[0]
                logger.debug(
                    "Encoded %s -> %s q=%d %.0f KB (budget %.0f KB)",
                    pil.size, working.size, q, len(data) / 1024, max_bytes / 1024,
                )
                return base64.b64encode(data).decode(), working.size, scale
        edge = int(edge * 0.75)
        if edge < 480:
            break

    # Nothing fit. Send the smallest attempt rather than failing the surface --
    # an over-budget request that the API refuses is still a clearer outcome
    # than silently dropping the panel.
    scale = working.size[0] / pil.size[0]
    logger.warning(
        "Could not encode surface under %.0f KB; sending %.0f KB",
        max_bytes / 1024, len(data) / 1024,
    )
    return base64.b64encode(data).decode(), working.size, scale


def _close_unbalanced(fragment: str) -> str:
    """Close brackets a model opened and forgot to close.

    Small open-weight models routinely stop mid-structure with
    `finish_reason: "stop"` -- not truncation, just a failure to emit the last
    `]}`. Measured on llama-3.2-11b, which returned all thirteen declarations
    correctly and then ended one bracket short. Discarding a complete, correct
    extraction over two missing characters would be the wrong trade.

    A stack rather than two counters, because the closing order follows the
    nesting order: `{"fields":[{...}` must be closed `]}` and not `}]`.
    Brackets inside string literals are ignored, so an address like
    "Shop No. 4 [Rear]" cannot corrupt the count.
    """
    stack: list[str] = []
    in_string = escaped = False

    for ch in fragment:
        if escaped:
            escaped = False
            continue
        if in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and stack[-1] == ("{" if ch == "}" else "["):
                stack.pop()

    repaired = fragment
    if in_string:
        repaired += '"'
    # A value may have been cut mid-way ("confidence": ), leaving a trailing
    # separator or a key with nothing after it. Neither is recoverable, so shed
    # them before closing rather than emitting invalid JSON.
    previous = None
    while previous != repaired:
        previous = repaired
        repaired = re.sub(r'[,:]\s*$', '', repaired.rstrip())
        repaired = re.sub(r',\s*"[^"]*"\s*$', '', repaired.rstrip())
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    return repaired


def _parse_json(text: str) -> dict:
    """Extract a JSON object from a model response.

    Models wrap JSON in prose or fences no matter how firmly asked not to, so
    the fence is stripped and the outermost braces located before parsing. A
    structurally incomplete but otherwise valid response is repaired rather
    than discarded -- see `_close_unbalanced`.
    """
    if not text:
        raise ValueError("empty response")

    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.MULTILINE)

    for candidate in (cleaned, _close_unbalanced(cleaned)):
        try:
            return _as_field_payload(json.loads(candidate))
        except json.JSONDecodeError:
            pass

    # Fall back to the outermost structure anywhere in the response, so a model
    # that prefixes a sentence still yields its object.
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if starts:
        fragment = cleaned[min(starts):]
        for candidate in (fragment, _close_unbalanced(fragment)):
            try:
                return _as_field_payload(json.loads(candidate))
            except json.JSONDecodeError:
                pass

    # Last structural attempt: harvest the field objects wherever they sit.
    #
    # llama-3.2-11b emits one object per line prefixed with a stray empty array
    # -- `[] {"field_name": "mrp", ...}` -- which is neither an object nor an
    # array and defeats every whole-document parse. The objects themselves are
    # well-formed, so they are collected individually rather than the whole
    # reading being thrown away over an envelope the model invented.
    harvested = _scan_field_objects(cleaned)
    if harvested:
        return {"fields": harvested}

    raise ValueError(f"no JSON object found in response: {text[:200]!r}")


_FIELD_OBJECT_RE = re.compile(r'\{[^{}]*?"field_name"\s*:\s*"[^"]+?"[^{}]*\}')


def _scan_field_objects(text: str) -> list[dict]:
    """Collect every well-formed field object appearing anywhere in the text."""
    found: list[dict] = []
    seen: set[str] = set()
    for match in _FIELD_OBJECT_RE.finditer(text):
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        name = obj.get("field_name")
        if isinstance(name, str) and name not in seen:
            seen.add(name)
            found.append(obj)
    return found


# Label text a model uses for each declaration, longest first so
# "unit sale price" is matched before "price".
_PROSE_LABELS: list[tuple[str, str]] = [
    ("unit sale price", "unit_price"),
    ("unit price", "unit_price"),
    ("maximum retail price", "mrp"),
    ("retail sale price", "mrp"),
    ("mrp", "mrp"),
    ("net quantity", "net_quantity"),
    ("net weight", "net_quantity"),
    ("net qty", "net_quantity"),
    ("date of manufacture", "mfg_date"),
    ("manufacturing date", "mfg_date"),
    ("manufacture date", "mfg_date"),
    ("packed on", "mfg_date"),
    ("mfg date", "mfg_date"),
    ("best before", "expiry_date"),
    ("use by", "expiry_date"),
    ("expiry date", "expiry_date"),
    ("expiry", "expiry_date"),
    ("manufacturer address", "manufacturer_address"),
    ("manufactured by", "manufacturer_name"),
    ("marketed by", "manufacturer_name"),
    ("manufacturer", "manufacturer_name"),
    ("address", "manufacturer_address"),
    ("country of origin", "country_of_origin"),
    ("consumer care", "customer_care"),
    ("customer care", "customer_care"),
    ("helpline", "customer_care"),
    ("fssai", "fssai_licence"),
    ("batch number", "batch_number"),
    ("batch no", "batch_number"),
    ("lot no", "batch_number"),
    ("product name", "product_name"),
    ("brand name", "brand_name"),
    ("brand", "brand_name"),
]


def _parse_prose_fields(text: str) -> dict:
    """Last-resort reader for a model that answered in prose.

    llama-3.2-11b intermittently ignores the JSON instruction and returns a
    markdown list instead -- the same declarations, correctly read, in the
    wrong envelope:

        *   **MRP (Maximum Retail Price)**: Rs. 45.00
        *   **Net Quantity**: 200 g

    Throwing that away and reporting an extraction failure would be the wrong
    call: the reading is right, and a missing declaration is what the rules
    engine turns into a statutory finding. Recovering it here is not
    guesswork -- every value still comes verbatim from the model's own reading
    of the pixels, and the OCR verification stage checks it afterwards exactly
    as it checks a JSON answer.

    Confidence is capped below the auto-accept threshold. A response that
    arrived in an unrequested format is weaker evidence than one that followed
    instruction, and it should reach a human rather than issue on its own.
    """
    fields: list[dict] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Strip list bullets and markdown emphasis.
        line = re.sub(r"^[\*\-\u2022\s]+", "", line)
        line = line.replace("**", "").replace("__", "")
        if ":" not in line:
            continue

        label, _, value = line.partition(":")
        label_norm = re.sub(r"[^a-z ]+", " ", label.lower()).strip()
        value = value.strip().strip("*").strip()
        if not value or value.lower() in {"n/a", "na", "none", "not visible", "null", "-"}:
            continue

        for needle, field_name in _PROSE_LABELS:
            if needle in label_norm and field_name not in seen:
                seen.add(field_name)
                fields.append({
                    "field_name": field_name,
                    "value": value[:300],
                    "is_present": True,
                    # Below CONFIDENCE_ACCEPT_THRESHOLD by construction, so a
                    # recovered reading is reviewed rather than auto-issued.
                    "confidence": 0.55,
                    "notes": "recovered from an unstructured model response",
                })
                break

    if not fields:
        raise ValueError("no declarations found in prose response")
    return {"fields": fields}


def _as_field_payload(parsed: object) -> dict:
    """Normalise the several shapes models return into {"fields": [...]}.

    Asked for `{"fields":[...]}`, a small model will sometimes return the bare
    array, or wrap it under a differently-named key. The content is right and
    only the envelope differs, so it is reshaped rather than rejected.
    """
    if isinstance(parsed, list):
        return {"fields": parsed}
    if isinstance(parsed, dict):
        if "fields" in parsed:
            return parsed
        # A single lone field object, or an alternative wrapper key.
        if "field_name" in parsed:
            return {"fields": [parsed]}
        for value in parsed.values():
            if isinstance(value, list) and all(isinstance(v, dict) for v in value):
                return {"fields": value}
        return parsed
    raise ValueError(f"unexpected JSON root: {type(parsed).__name__}")

def _to_result(
    payload: dict,
    provider: str,
    model: str,
    surface: str,
    latency_ms: int,
    scale: float,
    image_size: tuple[int, int],
    raw: str | None = None,
    tokens: int | None = None,
) -> VisionExtractionResult:
    """Validate a provider payload into the canonical result shape."""
    fields: list[ExtractedFieldSchema] = []
    seen: set[str] = set()

    for item in payload.get("fields", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            bbox = BoundingBox.from_any(item.get("bbox"))
            # Boxes come back in the coordinates of the downscaled image that
            # was actually sent; rescale so they index the full-size original.
            if bbox is not None and scale != 1.0:
                bbox = bbox.scaled(1 / scale, 1 / scale)

            field = ExtractedFieldSchema(
                field_name=item.get("field_name") or item.get("field") or "",
                value=item.get("value"),
                bbox=bbox,
                confidence=float(item.get("confidence") or 0.0),
                surface=surface,
                is_present=bool(item.get("is_present", item.get("value") is not None)),
                notes=item.get("notes"),
            )
        except Exception as exc:
            logger.debug("Dropping malformed field %r: %s", item, exc)
            continue

        if not field.field_name or field.field_name in seen:
            continue
        # A field asserted present with no value is a contradiction; trust the value.
        if field.value is None:
            field.is_present = False
        seen.add(field.field_name)
        fields.append(field)

    return VisionExtractionResult(
        fields=fields,
        surface_type=surface,
        provider=provider,
        model=model,
        raw_response=raw,
        latency_ms=latency_ms,
        tokens_used=tokens,
        image_size=image_size,
    )


# ===========================================================================
# Provider interface
# ===========================================================================
class VisionProvider(ABC):
    name: str = "base"

    #: True when the provider's readings come from the OCR engine itself.
    #: Re-reading such a value with the same engine is not independent
    #: verification -- it agrees with itself by construction and manufactures
    #: confidence the system has not earned. The pipeline checks this rather
    #: than testing provider names, so a new OCR-backed provider cannot be
    #: added without answering the question.
    self_verifying: bool = False

    @abstractmethod
    def extract(self, image: np.ndarray, surface: str = "FRONT", **kwargs) -> VisionExtractionResult: ...

    @property
    def available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
class ClaudeVisionProvider(VisionProvider):
    """Anthropic Claude Vision -- the project's configured primary provider."""

    name = "claude"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.CLAUDE_VISION_MODEL
        self._client = None

    @property
    def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=self.api_key, timeout=settings.VISION_TIMEOUT_SECONDS
            )
        return self._client

    def extract(self, image: np.ndarray, surface: str = "FRONT", **kwargs) -> VisionExtractionResult:
        if not self.available:
            return VisionExtractionResult(
                provider=self.name, model=self.model, surface_type=surface,
                error="ANTHROPIC_API_KEY is not configured",
            )

        b64, sent_size, scale = _encode(image)
        prompt = EXTRACTION_USER_PROMPT.format(
            surface=surface, width=sent_size[0], height=sent_size[1]
        )

        last_error: str | None = None
        for attempt in range(settings.VISION_MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                response = self._get_client().messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=EXTRACTION_SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {
                                "type": "base64", "media_type": "image/jpeg", "data": b64,
                            }},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
                latency = int((time.perf_counter() - started) * 1000)
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )
                payload = _parse_json(text)
                tokens = None
                if getattr(response, "usage", None):
                    tokens = response.usage.input_tokens + response.usage.output_tokens
                return _to_result(
                    payload, self.name, self.model, surface, latency, scale,
                    sent_size, raw=text[:8000], tokens=tokens,
                )
            except Exception as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                logger.warning("Claude Vision attempt %d failed: %s", attempt + 1, last_error)
                if attempt < settings.VISION_MAX_RETRIES:
                    time.sleep(1.5 * (attempt + 1))   # linear backoff

        return VisionExtractionResult(
            provider=self.name, model=self.model, surface_type=surface,
            error=last_error or "extraction failed",
        )


# ---------------------------------------------------------------------------
class GeminiVisionProvider(VisionProvider):
    """Google Gemini Vision."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_VISION_MODEL
        self._client = None

    @property
    def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            from google import genai  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def extract(self, image: np.ndarray, surface: str = "FRONT", **kwargs) -> VisionExtractionResult:
        if not self.available:
            return VisionExtractionResult(
                provider=self.name, model=self.model, surface_type=surface,
                error="GEMINI_API_KEY is not configured",
            )

        b64, sent_size, scale = _encode(image)
        prompt = EXTRACTION_USER_PROMPT.format(
            surface=surface, width=sent_size[0], height=sent_size[1]
        )

        last_error: str | None = None
        for attempt in range(settings.VISION_MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                from google.genai import types

                response = self._get_client().models.generate_content(
                    model=self.model,
                    contents=[
                        types.Part.from_bytes(
                            data=base64.b64decode(b64), mime_type="image/jpeg"
                        ),
                        f"{EXTRACTION_SYSTEM_PROMPT}\n\n{prompt}",
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", temperature=0.0
                    ),
                )
                latency = int((time.perf_counter() - started) * 1000)
                text = response.text or ""
                payload = _parse_json(text)
                return _to_result(
                    payload, self.name, self.model, surface, latency, scale,
                    sent_size, raw=text[:8000],
                )
            except Exception as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                logger.warning("Gemini Vision attempt %d failed: %s", attempt + 1, last_error)
                if attempt < settings.VISION_MAX_RETRIES:
                    time.sleep(1.5 * (attempt + 1))

        return VisionExtractionResult(
            provider=self.name, model=self.model, surface_type=surface,
            error=last_error or "extraction failed",
        )


# A terse prompt for smaller open-weight models.
#
# Two findings, both measured against llama-3.2-11b on NIM, both the opposite of
# what the full prompt assumes:
#
# 1. LENGTH. The full EXTRACTION_SYSTEM_PROMPT + EXTRACTION_USER_PROMPT is
#    ~2.4 KB and Claude follows all of it. The 11B reads the label just as
#    accurately, then loses the output-format instruction somewhere in that
#    length and answers in prose markdown. Neither `response_format:
#    json_object` nor `nvext.guided_json` rescued it -- NIM accepts both
#    parameters for this model and then ignores them. Only brevity worked.
#
# 2. EXAMPLES. A realistic example value is copied into the answer. A version of
#    this prompt showing `"value":"Rs. 45.00"` produced "Rs. 45.00" for a label
#    that plainly read Rs. 10.00. In an enforcement tool that is not a cosmetic
#    bug: it is a fabricated declaration that the rules engine would then price
#    a penalty against. Placeholders only -- never a value that could be mistaken
#    for a reading.
#
# The bbox field is deliberately absent. Asking for it lengthened the prompt
# enough to bring the prose failure back, and a small model's coordinates were
# not trustworthy anyway. Evidence crops for this provider are located
# afterwards by deterministic OCR instead, which is a better division of labour:
# the model reads, and code decides where the pixels are.
EXTRACTION_COMPACT_PROMPT = """Output JSON only. No prose, no markdown, no explanation.

Read this {surface} package label. Transcribe values EXACTLY as printed.
Never guess or complete a value that is not visible: a reported absence is
correct, an invention is evidence of a violation that did not happen.

{{"fields":[{{"field_name":"<key>","value":"<text as printed, or null>","is_present":<true|false>,"confidence":<0..1>}}]}}

Keys: mrp, net_quantity, unit_price, mfg_date, expiry_date, manufacturer_name,
manufacturer_address, country_of_origin, customer_care, fssai_licence,
batch_number, product_name, brand_name. Include every key."""


# Countries that plausibly appear as an origin on an Indian retail pack. The
# list is short on purpose: its job is to reject the word "ORIGIN" lifted out of
# a brand logo, not to be a gazetteer.
_ORIGIN_COUNTRIES = frozenset({
    "india", "china", "usa", "u.s.a", "united states", "uk", "united kingdom",
    "england", "germany", "france", "italy", "spain", "japan", "korea",
    "thailand", "vietnam", "indonesia", "malaysia", "singapore", "bangladesh",
    "sri lanka", "nepal", "uae", "switzerland", "netherlands", "belgium",
    "poland", "turkey", "brazil", "australia", "canada", "taiwan",
})

# Words that mark a line as an ingredient list or a statutory caution rather
# than a name -- the two things most often mistaken for a product name.
_NOT_A_NAME = (
    "ingredient", "caution", "warning", "direction", "flammable", "alcohol",
    "myristate", "phthalate", "glycerin", "butane", "propane", "perfume,",
    "keep out of reach", "do not", "shake well",
)


def _plausible(field_name: str, text: str) -> bool:
    """Does this line actually look like the declaration it was assigned to?

    The classifier is a small model choosing among OCR lines, and it will pick
    a nearby line when the right one is absent -- the word "ORIGIN" out of a
    brand logo for country of origin, or a net quantity for a price on a panel
    that carries no price at all. Every one of those becomes a false statutory
    finding downstream.

    So the assignment is checked the same way every other claim in this system
    is checked: against deterministic parsers, not against the model's
    confidence in itself. A line that cannot be read as the thing it claims to
    be is dropped, and the declaration is reported absent -- which is a finding
    in its own right, and an honest one.
    """
    from rules.base import parse_currency, parse_date, parse_quantity

    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()

    if field_name in ("mrp", "unit_price"):
        # A price needs a currency amount, and `parse_currency` is deliberately
        # lenient -- it will read the 250 out of "250mle", which is a net
        # quantity being mistaken for a price. Require a currency marker or a
        # two-decimal amount, the two forms a printed price actually takes.
        has_marker = bool(re.search(r"(?i)(rs\.?|inr|mrp|₹)", raw))
        has_decimal = bool(re.search(r"\d+[.,]\d{2}", raw))
        if not (has_marker or has_decimal):
            return False
        # A marker or a two-decimal amount is the evidence; `parse_currency`
        # only has to confirm a figure is actually present.
        return parse_currency(raw) is not None or has_decimal

    if field_name == "net_quantity":
        return parse_quantity(raw) is not None

    if field_name in ("mfg_date", "expiry_date"):
        return parse_date(raw) is not None

    if field_name == "country_of_origin":
        return any(c in low for c in _ORIGIN_COUNTRIES)

    if field_name == "customer_care":
        # A phone number of plausible length, or an email, or a website.
        digits = re.sub(r"\D", "", raw)
        return len(digits) >= 8 or "@" in raw or "www." in low

    if field_name == "fssai_licence":
        # The FSSAI licence is a 14-digit number. A cosmetics manufacturing
        # licence such as COS-MH/105807 is a different instrument entirely and
        # must not be filed as one.
        return bool(re.search(r"\d{14}", re.sub(r"\s", "", raw)))

    if field_name == "batch_number":
        # Needs an actual code, not the caption "Batch No.".
        stripped = re.sub(r"(?i)batch\s*(no\.?|number)?\s*:?", "", raw).strip()
        return bool(re.search(r"[A-Za-z0-9]{3,}", stripped))

    if field_name == "manufacturer_address":
        # Comma-separated locality parts, or a PIN code.
        return raw.count(",") >= 1 or bool(re.search(r"\b\d{6}\b", raw))

    if field_name in ("product_name", "brand_name"):
        if any(w in low for w in _NOT_A_NAME):
            return False
        # A name is words, not a licence number or a bare code.
        letters = sum(ch.isalpha() for ch in raw)
        return letters >= 3 and letters >= len(raw) * 0.5

    if field_name == "manufacturer_name":
        return sum(ch.isalpha() for ch in raw) >= 4

    return True


# ---------------------------------------------------------------------------
class NvidiaVisionProvider(VisionProvider):
    """NVIDIA NIM (build.nvidia.com).

    Included because it is the credible option for a team without a paid
    Anthropic or Google account: NVIDIA issues free credits, and the endpoint
    speaks the OpenAI chat-completions dialect, so it needs no vendor SDK --
    httpx is already a dependency.

    Two things differ from the other providers and are handled here rather than
    left to surprise the caller. The image must be small enough to inline, and
    the smaller open-weight vision models are markedly less reliable at
    returning strict JSON, so the response is parsed leniently and a failure to
    parse is reported as an extraction error rather than raised.
    """

    name = "nvidia"
    # The declarations are read by OCR and only labelled by the model, so the
    # OCR re-read would be checking its own work.
    self_verifying = True

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.NVIDIA_API_KEY
        self.model = model or settings.NVIDIA_VISION_MODEL
        self.base_url = settings.NVIDIA_BASE_URL.rstrip("/")

    @property
    def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import httpx  # noqa: F401

            return True
        except ImportError:
            return False

    # Keys the classifier may assign, in the order they are offered to it.
    FIELD_KEYS = (
        "mrp", "net_quantity", "unit_price", "mfg_date", "expiry_date",
        "manufacturer_name", "manufacturer_address", "country_of_origin",
        "customer_care", "fssai_licence", "batch_number", "product_name",
        "brand_name",
    )

    CLASSIFY_PROMPT = """Output JSON only. No prose.

Numbered lines below were read off a {surface} package label by OCR.
Decide which line(s) carry each legal declaration. Do NOT retype the text and
do NOT correct it -- return only line numbers.

Choose the line holding the VALUE, not the caption. If "Batch No." sits on one
line and its number on the next, return the number's line. A value split over
two lines may return both.
Return "lines":[] when a declaration genuinely does not appear -- a wrong line
is worse than an honest absence, because absence is itself a finding.

LINES:
{lines}

{{"fields":[{{"field_name":"<key>","lines":[<numbers>]}}]}}

Keys: {keys}"""

    def extract(self, image: np.ndarray, surface: str = "FRONT", **kwargs) -> VisionExtractionResult:
        if not self.available:
            return VisionExtractionResult(
                provider=self.name, model=self.model, surface_type=surface,
                error="NVIDIA_API_KEY is not configured",
            )

        started = time.perf_counter()

        # ---- 1. Deterministic OCR reads the characters -------------------
        #
        # This inverts the usual arrangement, and the measurements are the
        # reason. Asked to read this label directly, llama-3.2-11b returned an
        # MRP of 339.00 where the pack plainly prints Rs. 399.00, took the
        # excise licence number for the batch number, and swapped brand with
        # product. RapidOCR on the same pixels returned "Rs.399.00", the right
        # expiry, the right address and the right care number -- it simply has
        # no idea which line is which.
        #
        # So each component does what it is good at: OCR reads, the model
        # classifies. A price the model never generates is a price it cannot
        # hallucinate, and because every value is now anchored to an OCR line
        # it arrives with a real bounding box -- which restores the evidence
        # crop and the independent re-read that the direct path had lost.
        try:
            from extraction.ocr_verify import get_verifier

            lines = get_verifier().read_lines(image)
        except Exception as exc:
            return VisionExtractionResult(
                provider=self.name, model=self.model, surface_type=surface,
                error=f"OCR stage failed: {exc.__class__.__name__}: {exc}",
            )

        usable = [(i, txt, box, conf) for i, (txt, box, conf) in enumerate(lines)
                  if txt and txt.strip() and (conf is None or conf >= 0.30)]
        if not usable:
            return VisionExtractionResult(
                provider=self.name, model=self.model, surface_type=surface,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error="No text could be read from this surface",
            )

        listing = "\n".join(f"{i}: {txt}" for i, txt, _, _ in usable)
        prompt = self.CLASSIFY_PROMPT.format(
            surface=surface, lines=listing, keys=", ".join(self.FIELD_KEYS),
        )

        # ---- 2. The model assigns lines to declarations ------------------
        import httpx

        payload = {
            "model": self.model,
            # Text only, deliberately. Attaching the photograph as well makes
            # the model switch into describing it -- measured: with the image
            # it answered in prose markdown every time, without it returned
            # clean JSON in 5 s. It does not need the pixels; OCR has already
            # read them, and the job here is only to label lines.
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1200,
            "temperature": 0.0,
            "top_p": 1.0,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        last_error: str | None = None
        assignment: dict | None = None

        for attempt in range(settings.VISION_MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=settings.VISION_TIMEOUT_SECONDS) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers,
                    )
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:400]}")

                text = (
                    response.json().get("choices", [{}])[0]
                    .get("message", {}).get("content", "") or ""
                )
                assignment = _parse_json(text)
                break
            except Exception as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                logger.warning("NVIDIA classify attempt %d failed: %s", attempt + 1, last_error)
                if attempt < settings.VISION_MAX_RETRIES:
                    time.sleep(1.5 * (attempt + 1))

        latency = int((time.perf_counter() - started) * 1000)

        if assignment is None:
            return VisionExtractionResult(
                provider=self.name, model=self.model, surface_type=surface,
                latency_ms=latency, error=last_error or "classification failed",
            )

        # ---- 3. Build fields from the OCR text at the chosen lines -------
        by_index = {i: (txt, box, conf) for i, txt, box, conf in usable}
        fields: list[ExtractedFieldSchema] = []
        claimed: set[str] = set()

        for entry in assignment.get("fields", []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("field_name")
            if name not in self.FIELD_KEYS or name in claimed:
                continue

            raw_lines = entry.get("lines") or entry.get("line")
            if isinstance(raw_lines, (int, str)):
                raw_lines = [raw_lines]
            if not isinstance(raw_lines, list):
                continue

            picked = []
            for candidate in raw_lines:
                try:
                    idx = int(candidate)
                except (TypeError, ValueError):
                    continue
                if idx in by_index:
                    picked.append(idx)
            if not picked:
                continue

            texts = [by_index[i][0].strip() for i in picked]
            joined = " ".join(texts).strip()

            # The model proposed this line; deterministic parsing decides
            # whether to accept it. A rejected assignment becomes an absence,
            # never a guess.
            if not _plausible(name, joined):
                logger.debug(
                    "Rejected %s assignment %r: not plausible for that declaration",
                    name, joined[:60],
                )
                continue

            claimed.add(name)
            boxes = [by_index[i][1] for i in picked]
            confs = [by_index[i][2] or 0.6 for i in picked]

            # Union of the chosen lines, so a two-line address gets one box.
            xs = [b[0] for b in boxes]
            ys = [b[1] for b in boxes]
            x2 = [b[0] + b[2] for b in boxes]
            y2 = [b[1] + b[3] for b in boxes]
            bbox = BoundingBox(
                x=min(xs), y=min(ys), width=max(x2) - min(xs), height=max(y2) - min(ys),
            )

            fields.append(ExtractedFieldSchema(
                field_name=name,
                value=joined[:300],
                bbox=bbox,
                # The reading is OCR's, so the confidence is OCR's. The model
                # contributed only the label, and a misfiled line is caught by
                # the rules engine rather than by a confidence number.
                confidence=round(min(0.97, max(0.35, sum(confs) / len(confs))), 3),
                surface=surface,
                is_present=True,
                notes="Read by OCR; classified by the vision model",
            ))

        for name in self.FIELD_KEYS:
            if name not in claimed:
                fields.append(ExtractedFieldSchema(
                    field_name=name, value=None, bbox=None, confidence=0.0,
                    surface=surface, is_present=False,
                    notes="Not found among the lines read from this surface",
                ))

        return VisionExtractionResult(
            provider=self.name, model=self.model, surface_type=surface,
            fields=fields, latency_ms=latency,
            raw_response=f"{len(usable)} OCR lines classified",
        )


# ---------------------------------------------------------------------------
class MockVisionProvider(VisionProvider):
    """Deterministic offline extraction.

    Not a stub that returns canned text: it genuinely reads the image, locating
    printed lines with OpenCV morphology and classifying them by keyword, then
    parsing the value out. That means it responds correctly to a pack whose
    declarations were actually omitted -- which is the whole point of a demo
    fixture, and what makes the rules engine testable without an API key or a
    network connection.
    """

    name = "mock"
    self_verifying = True

    # Matched against a whitespace- and punctuation-stripped form of the line,
    # so an OCR reading of "Lic.No." still matches the key "licno". Real OCR
    # output is never as tidy as the label was.
    KEYWORDS: dict[str, tuple[str, ...]] = {
        "mrp": ("mrp", "mrp", "retailprice", "retailsaleprice", "maximumretail"),
        "net_quantity": ("netqty", "netquantity", "netwt", "netweight", "netcontent"),
        "unit_price": ("unitsaleprice", "unitprice", "perg", "perkg", "perml", "perl"),
        "mfg_date": ("mfgdate", "mfgdt", "manufactured", "packedon", "dateofmfg", "mfdon"),
        "expiry_date": ("bestbefore", "useby", "expiry", "expdate", "expires", "bestbefor"),
        "manufacturer_name": ("mfdby", "manufacturedby", "marketedby", "packedby"),
        "country_of_origin": ("countryoforigin", "origin", "madein", "productof"),
        "customer_care": ("consumercare", "customercare", "helpline", "tollfree", "care@"),
        "fssai_licence": ("fssai", "fssa", "licno", "licenceno", "licenseno"),
        "batch_number": ("batchno", "batch", "lotno", "bno"),
    }

    # An address is recognised by shape, not vocabulary: comma-separated
    # locality parts ending in a postal code. Keyword lists ("road", "nagar",
    # "sector") miss most real addresses, which is how a perfectly printed
    # address ends up reported as an undeclared one.
    #
    # The digit run is allowed to be 4-7 long rather than exactly 6 because OCR
    # routinely drops or doubles a zero in a PIN. Locating the address is a
    # separate question from whether its PIN is valid -- that judgement belongs
    # to the rules engine, which can then cite the actual digits read.
    ADDRESS_RE = re.compile(r",[^,]{2,40},|\b\d{4,7}\b\s*$")

    def __init__(self) -> None:
        self._ocr = None

    def _read_lines(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int], float]]:
        """Locate and read text lines using the shared OCR verifier.

        Read at native resolution. Resampling the page first is tempting but
        counter-productive: the detector rescales its own input anyway, so
        upscaling only costs time and can push large headline text past what
        the model handles well.
        """
        from extraction.ocr_verify import get_verifier

        if self._ocr is None:
            self._ocr = get_verifier()
        return self._ocr.read_lines(image)

    def extract(self, image: np.ndarray, surface: str = "FRONT", **kwargs) -> VisionExtractionResult:
        started = time.perf_counter()
        h, w = image.shape[:2]

        try:
            lines = self._read_lines(image)
        except Exception as exc:
            logger.warning("Mock provider line reading failed: %s", exc)
            lines = []

        found: dict[str, ExtractedFieldSchema] = {}
        claimed_lines: set[int] = set()

        def record(idx: int, field_name: str, value: str, box, conf: float) -> None:
            bx, by, bw, bh = box
            found[field_name] = ExtractedFieldSchema(
                field_name=field_name,
                value=value,
                bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                confidence=round(min(0.97, max(0.62, conf)), 3),
                surface=surface,
                is_present=True,
                notes="Read offline by the deterministic mock provider",
            )
            claimed_lines.add(idx)

        for idx, (text, box, conf) in enumerate(lines):
            # Strip whitespace and punctuation so OCR spacing quirks
            # ("Lic.No." vs "Lic. No.") do not defeat the match.
            squashed = re.sub(r"[^a-z0-9@]+", "", text.lower())
            matched = False
            for field_name, keys in self.KEYWORDS.items():
                if field_name in found:
                    continue
                if any(k in squashed for k in keys):
                    value = self._parse_value(field_name, text)
                    if value is None:
                        continue
                    record(idx, field_name, value, box, conf)
                    matched = True
                    break

            # An unclaimed line carrying a PIN code is the postal address.
            if (
                not matched
                and "manufacturer_address" not in found
                and self.ADDRESS_RE.search(text)
                and len(text.strip()) > 12
            ):
                record(idx, "manufacturer_address", text.strip(), box, conf)

        # Brand and product are the largest UNCLAIMED text near the top -- but
        # only when they are genuinely dominant. Branding is usually set far
        # larger than body copy, so a line must clearly exceed the median line
        # height to qualify. Without that bar the heuristic cheerfully labels
        # "(Incl. of all taxes)" as the brand name simply because nothing else
        # was left unclaimed, which is a confident wrong answer -- worse than
        # reporting the field as not found.
        if lines:
            median_h = sorted(ln[1][3] for ln in lines)[len(lines) // 2]
            header = [
                (i, ln) for i, ln in enumerate(lines)
                if ln[1][1] < h * 0.30
                and i not in claimed_lines
                and len(ln[0].strip()) > 2
                and ln[1][3] >= median_h * 1.35
            ]
            header.sort(key=lambda item: item[1][1][3], reverse=True)

            for slot, key in enumerate(("brand_name", "product_name")):
                if key in found or slot >= len(header):
                    continue
                i, (t, (bx, by, bw, bh), c) = header[slot]
                found[key] = ExtractedFieldSchema(
                    field_name=key, value=t.strip(),
                    bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                    confidence=round(min(0.95 - slot * 0.03, max(0.5, c)), 3),
                    surface=surface, is_present=True,
                )
                claimed_lines.add(i)

        # Every field in the vocabulary must be accounted for -- an absent
        # declaration is a finding, not a gap in the record.
        fields = list(found.values())
        for name in FIELD_NAMES:
            if name not in found:
                fields.append(
                    ExtractedFieldSchema(
                        field_name=name, value=None, bbox=None, confidence=0.0,
                        surface=surface, is_present=False,
                        notes="Not located on this surface",
                    )
                )

        return VisionExtractionResult(
            fields=fields,
            surface_type=surface,
            provider=self.name,
            model="deterministic-cv",
            latency_ms=int((time.perf_counter() - started) * 1000),
            image_size=(w, h),
        )

    @staticmethod
    def _parse_value(field_name: str, text: str) -> str | None:
        """Pull the declared value out of a label line."""
        t = re.sub(r"\s+", " ", text).strip()

        if field_name == "mrp":
            m = re.search(r"(?:rs\.?|inr|₹)\s*([0-9]+(?:[.,][0-9]{1,2})?)", t, re.I)
            if m:
                return f"Rs. {m.group(1).replace(',', '.')}"
            m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", t)
            return f"Rs. {m.group(1)}" if m else None

        if field_name == "net_quantity":
            m = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|mg|l|ltr|ml|n|pcs|pieces|no\.?s?)\b",
                t, re.I,
            )
            return f"{m.group(1)} {m.group(2)}" if m else None

        if field_name == "unit_price":
            m = re.search(
                r"(?:rs\.?|₹)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:per|/)\s*([a-z]+)", t, re.I
            )
            return f"Rs. {m.group(1)} per {m.group(2)}" if m else None

        if field_name in ("mfg_date", "expiry_date"):
            m = re.search(r"(\d{1,2}[/-]\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[a-z]{3,9}\s+\d{4})",
                          t, re.I)
            return m.group(1) if m else None

        if field_name == "fssai_licence":
            m = re.search(r"\b(\d{14})\b", t)
            return m.group(1) if m else None

        if field_name == "country_of_origin":
            m = re.search(r"(?:origin|made in|product of)\s*:?\s*([A-Za-z ]{3,40})", t, re.I)
            return m.group(1).strip() if m else None

        if field_name == "manufacturer_name":
            m = re.search(r"(?:mfd by|manufactured by|marketed by|packed by)\s*:?\s*(.{3,80})",
                          t, re.I)
            return m.group(1).strip() if m else None

        if field_name == "customer_care":
            m = re.search(r"(?:consumer care|customer care|helpline)\s*:?\s*(.{3,80})", t, re.I)
            if m:
                return m.group(1).strip()
            m = re.search(r"([\w.+-]+@[\w-]+\.\w+|\d{4}[- ]?\d{3}[- ]?\d{4})", t)
            return m.group(1) if m else None

        if field_name == "batch_number":
            m = re.search(r"(?:batch|lot|b\.?no)\s*\.?\s*:?\s*([A-Z0-9-]{2,20})", t, re.I)
            return m.group(1) if m else None

        # manufacturer_address and anything else: the whole line is the value
        return t if len(t) > 5 else None


# ===========================================================================
# Selection
# ===========================================================================
_PROVIDERS: dict[str, type[VisionProvider]] = {
    "claude": ClaudeVisionProvider,
    "gemini": GeminiVisionProvider,
    "nvidia": NvidiaVisionProvider,
    "mock": MockVisionProvider,
}

_instance: VisionProvider | None = None


def get_provider(name: str | None = None) -> VisionProvider:
    """Return the configured provider, degrading to mock if it is unusable.

    Falling back rather than raising is deliberate: a missing API key or a
    network outage at a demo venue must not take the inspection pipeline down.
    The result records which provider actually ran, so the substitution is
    visible rather than silent.
    """
    global _instance
    requested = (name or settings.VISION_PROVIDER).lower()

    if _instance is not None and _instance.name == requested:
        return _instance

    cls = _PROVIDERS.get(requested, MockVisionProvider)
    provider = cls()
    if not provider.available:
        logger.warning(
            "Vision provider %r is unavailable (no API key or SDK); "
            "falling back to the deterministic mock provider",
            requested,
        )
        provider = MockVisionProvider()

    _instance = provider
    logger.info("Vision provider: %s", provider.name)
    return provider


def reset_provider() -> None:
    global _instance
    _instance = None
