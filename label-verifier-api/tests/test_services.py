from app.models import ApplicationData, FieldStatus
from app.services import GOVERNMENT_WARNING, parse_abv, parse_volume, text_result, warning_result


def test_brand_normalization_matches():
    result = text_result("brand_name", "STONE'S THROW", ["Stone's Throw"], brand=True)
    assert result.status == FieldStatus.MATCH


def test_similar_brand_needs_review():
    result = text_result("brand_name", "STONE'S THROW", ["Stone Throw"], brand=True)
    assert result.status == FieldStatus.REVIEW


def test_abv_and_volume_parsing():
    assert parse_abv("90 Proof") == 45
    assert parse_abv("45.0% Alc./Vol.") == 45
    assert parse_volume("750 mL") == parse_volume("0.75 L") == 750


def test_country_alias_matches():
    result = text_result("country_of_origin", "United States", ["USA"])
    assert result.status == FieldStatus.MATCH


def test_warning_is_strict_about_heading_and_wording():
    assert warning_result(GOVERNMENT_WARNING).status == FieldStatus.MATCH
    assert warning_result(GOVERNMENT_WARNING.replace("GOVERNMENT", "Government")).status == FieldStatus.MISMATCH
    assert warning_result(GOVERNMENT_WARNING.replace("health problems", "health concerns")).status == FieldStatus.MISMATCH
