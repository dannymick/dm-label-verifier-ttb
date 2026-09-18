from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher
from io import BytesIO

from PIL import Image, ImageOps
import pytesseract

from app.models import FieldResult, FieldStatus

GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate "
    "machinery, and may cause health problems."
)


class OcrError(Exception):
    pass


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalize_brand(value: str) -> str:
    return re.sub(r"[^\w]", "", normalize_text(value))


def normalize_country(value: str) -> str:
    normalized = normalize_text(value).replace(".", "")
    return "united states" if normalized in {"united states", "usa", "us"} else normalized


def parse_abv(value: str) -> Decimal | None:
    percent = re.search(r"(\d+(?:\.\d+)?)\s*%", value, re.I)
    if percent:
        return Decimal(percent.group(1))
    proof = re.search(r"(\d+(?:\.\d+)?)\s*proof", value, re.I)
    return Decimal(proof.group(1)) / Decimal("2") if proof else None


def parse_volume(value: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ml|mL|l|L)\b", value)
    if not match:
        return None
    amount, unit = Decimal(match.group(1)), match.group(2).casefold()
    return amount * Decimal("1000") if unit == "l" else amount


def preprocess(data: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
            if image.width * image.height > 20_000_000:
                raise ValueError("Image dimensions exceed 20 megapixels.")
            longest = max(image.size)
            if longest > 2400:
                scale = 2400 / longest
                image = image.resize((round(image.width * scale), round(image.height * scale)))
            background = Image.new("RGBA", image.size, "white")
            background.alpha_composite(image)
            return ImageOps.autocontrast(background.convert("L"))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable image.") from exc


def ocr(image: Image.Image) -> tuple[str, list[str]]:
    try:
        data = pytesseract.image_to_data(
            image, config="--oem 1 --psm 11", lang="eng", timeout=7, output_type=pytesseract.Output.DICT
        )
    except (RuntimeError, pytesseract.TesseractNotFoundError) as exc:
        raise OcrError("OCR timed out or failed.") from exc
    line_words: dict[tuple[int, int, int], list[str]] = {}
    words: list[str] = []
    for index, word in enumerate(data["text"]):
        cleaned = word.strip()
        if cleaned:
            words.append(cleaned)
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            line_words.setdefault(key, []).append(cleaned)
    text = " ".join(words)
    if not text:
        raise OcrError("No readable text was detected in this image.")
    lines = [" ".join(words) for words in line_words.values()]
    return text, lines


def candidate(lines: list[str], expected: str) -> tuple[str | None, float]:
    groups = lines + [" ".join(lines[index : index + 2]) for index in range(len(lines) - 1)]
    if not groups:
        return None, 0.0
    best = max(groups, key=lambda line: SequenceMatcher(None, normalize_text(expected), normalize_text(line)).ratio())
    return best, SequenceMatcher(None, normalize_text(expected), normalize_text(best)).ratio()


def text_result(field: str, expected: str, lines: list[str], brand: bool = False) -> FieldResult:
    observed, score = candidate(lines, expected)
    if not observed:
        return FieldResult(field=field, expected=expected, observed=None, status=FieldStatus.MISSING, reason="No readable label text was found.")
    if brand:
        equal = normalize_brand(observed) == normalize_brand(expected)
    elif field == "country_of_origin":
        expected_country = normalize_country(expected)
        equal = expected_country == normalize_country(observed) or expected_country in normalize_text(observed)
    else:
        equal = normalize_text(observed) == normalize_text(expected)
    if equal:
        return FieldResult(field=field, expected=expected, observed=observed, status=FieldStatus.MATCH, reason="Matched after normalization.", evidence=[observed], similarity=round(score, 2))
    status = FieldStatus.REVIEW if score >= 0.85 else FieldStatus.MISMATCH
    reason = "Similar text needs an agent review." if status == FieldStatus.REVIEW else "Readable label text does not match the application."
    return FieldResult(field=field, expected=expected, observed=observed, status=status, reason=reason, evidence=[observed], similarity=round(score, 2))


def numeric_result(field: str, expected: str, text: str, parser) -> FieldResult:
    expected_value = parser(expected)
    numeric_pattern = r"\d+(?:\.\d+)?\s*(?:%|proof\b|ml\b|l\b)"
    values = [parser(match.group(0)) for match in re.finditer(numeric_pattern, text, re.I)]
    values = [value for value in values if value is not None]
    if expected_value is None:
        return FieldResult(field=field, expected=expected, observed=None, status=FieldStatus.REVIEW, reason="The application value could not be parsed.")
    if not values:
        return FieldResult(field=field, expected=expected, observed=None, status=FieldStatus.MISSING, reason="No readable value was found on the label.")
    if expected_value in values:
        if any(value != expected_value for value in values):
            return FieldResult(field=field, expected=expected, observed=str(expected_value), status=FieldStatus.REVIEW, reason="Conflicting numeric values on the label need an agent review.")
        return FieldResult(field=field, expected=expected, observed=next(match.group(0) for match in re.finditer(numeric_pattern, text, re.I) if parser(match.group(0)) == expected_value), status=FieldStatus.MATCH, reason="Numeric value matches.")
    return FieldResult(field=field, expected=expected, observed=str(values[0]), status=FieldStatus.MISMATCH, reason="Numeric value does not match the application.")


def warning_result(text: str) -> FieldResult:
    heading = re.search(r"GOVERNMENT\s+WARNING\s*:", text, re.I)
    if not heading:
        return FieldResult(field="government_warning", expected=GOVERNMENT_WARNING, observed=None, status=FieldStatus.MISSING, reason="The GOVERNMENT WARNING heading was not found.")
    observed = text[heading.start() :]
    body_expected = normalize_text(GOVERNMENT_WARNING.split(":", 1)[1])
    body_observed = normalize_text(observed.split(":", 1)[1] if ":" in observed else "")
    if heading.group(0) != "GOVERNMENT WARNING:":
        return FieldResult(field="government_warning", expected=GOVERNMENT_WARNING, observed=observed, status=FieldStatus.MISMATCH, reason="The heading must be uppercase: GOVERNMENT WARNING:.", evidence=[observed])
    if body_expected in body_observed:
        return FieldResult(field="government_warning", expected=GOVERNMENT_WARNING, observed=observed, status=FieldStatus.MATCH, reason="Required warning wording and heading match.", evidence=[observed])
    return FieldResult(field="government_warning", expected=GOVERNMENT_WARNING, observed=observed, status=FieldStatus.MISMATCH, reason="The warning wording does not exactly match the required statement.", evidence=[observed])


def compare(application, text: str, lines: list[str]) -> list[FieldResult]:
    results = [
        text_result("brand_name", application.brand_name, lines, brand=True),
        text_result("class_type", application.class_type, lines),
        numeric_result("alcohol_content", application.alcohol_content, text, parse_abv),
        numeric_result("net_contents", application.net_contents, text, parse_volume),
    ]
    if application.country_of_origin:
        results.append(text_result("country_of_origin", application.country_of_origin, lines))
    results.append(warning_result(text))
    return results
