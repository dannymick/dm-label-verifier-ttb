from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models import AnalysisResult, ApplicationData, FieldStatus
from app.services import OcrError, compare, ocr, preprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title="Alcohol Label Verifier")
allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST"], allow_headers=["*"], max_age=600)
lock = asyncio.Lock()


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers={"Cache-Control": "no-store"})


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, __: RequestValidationError):
    return error(422, "invalid_request", "Check the required fields and try again.")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalysisResult)
async def analyze(image: UploadFile = File(...), application: str = Form(...)):
    if lock.locked():
        return error(503, "service_busy", "Another label is being analyzed. Please try again in a moment.")
    if image.content_type not in {"image/jpeg", "image/png"}:
        return error(415, "unsupported_image", "Upload a JPEG or PNG image under 5 MiB.")
    try:
        metadata = ApplicationData.model_validate(json.loads(application))
    except (json.JSONDecodeError, ValidationError):
        return error(422, "invalid_application", "Check the application details and try again.")
    upload = await image.read()
    if len(upload) > 5 * 1024 * 1024:
        return error(413, "file_too_large", "Upload an image smaller than 5 MiB.")
    started = time.perf_counter()
    async with lock:
        try:
            image_data = await asyncio.to_thread(preprocess, upload)
            text, lines = await asyncio.to_thread(ocr, image_data)
            fields = compare(metadata, text, lines)
        except ValueError as exc:
            return error(422, "invalid_image", str(exc))
        except OcrError as exc:
            return error(422, "ocr_failed", str(exc))
        finally:
            await image.close()
    elapsed = round((time.perf_counter() - started) * 1000)
    logger.info("analysis_complete processing_ms=%s image=%sx%s", elapsed, image_data.width, image_data.height)
    statuses = {field.status for field in fields}
    overall = FieldStatus.MISMATCH if FieldStatus.MISMATCH in statuses else FieldStatus.REVIEW if statuses & {FieldStatus.REVIEW, FieldStatus.MISSING} else FieldStatus.MATCH
    return JSONResponse(content=AnalysisResult(overall_status=overall, processing_ms=elapsed, ocr_text=text, fields=fields, limitations=["OCR cannot verify warning boldness, type size, placement, or label completeness.", "Decorative fonts, glare, and perspective distortion may reduce OCR quality."]).model_dump(mode="json"), headers={"Cache-Control": "no-store"})
