import json
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import OcrError

client = TestClient(app)
application = {"brand_name": "Old Tom", "class_type": "Bourbon", "alcohol_content": "45%", "net_contents": "750 mL"}


def image_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (100, 100), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_rejects_unsupported_image():
    response = client.post("/analyze", data={"application": json.dumps(application)}, files={"image": ("test.txt", b"text", "text/plain")})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_image"


def test_ocr_failure_returns_friendly_error():
    with patch("app.main.ocr", side_effect=OcrError("No readable text was detected in this image.")):
        response = client.post("/analyze", data={"application": json.dumps(application)}, files={"image": ("label.png", image_bytes(), "image/png")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ocr_failed"


def test_successful_analysis_returns_field_results():
    text = (
        "Old Tom Bourbon 45% 750 mL GOVERNMENT WARNING: (1) According to the Surgeon General, "
        "women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, "
        "and may cause health problems."
    )
    with patch("app.main.ocr", return_value=(text, ["Old Tom", "Bourbon", "45%", "750 mL", text[text.index("GOVERNMENT"):]])):
        response = client.post("/analyze", data={"application": json.dumps(application)}, files={"image": ("label.png", image_bytes(), "image/png")})
    assert response.status_code == 200
    assert response.json()["overall_status"] == "match"


def test_batch_returns_an_outcome_per_file():
    text = "Old Tom Bourbon 45% 750 mL GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."
    files = [("images", ("one.png", image_bytes(), "image/png")), ("images", ("two.png", image_bytes(), "image/png"))]
    with patch("app.main.ocr", return_value=(text, ["Old Tom", "Bourbon", "45%", "750 mL", text[text.index("GOVERNMENT"):]])):
        response = client.post("/batch", data={"application": json.dumps(application)}, files=files)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
