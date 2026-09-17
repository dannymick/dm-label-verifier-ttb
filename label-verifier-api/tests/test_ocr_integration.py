from pathlib import Path

from PIL import Image

from app.models import ApplicationData, FieldStatus
from app.services import compare, ocr
from scripts import generate_sample_labels


def test_tesseract_reads_a_clean_synthetic_label(tmp_path, monkeypatch):
    monkeypatch.setattr(generate_sample_labels, "OUTPUT", Path(tmp_path))
    generate_sample_labels.label("perfect.png")
    text, lines = ocr(Image.open(tmp_path / "perfect.png"))
    application = ApplicationData(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45%",
        net_contents="750 mL",
        country_of_origin="United States",
    )
    assert {field.status for field in compare(application, text, lines)} == {FieldStatus.MATCH}
