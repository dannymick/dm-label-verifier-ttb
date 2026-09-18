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

from app.models import AnalysisResult, ApplicationData, BatchItem, BatchResult, FieldStatus
from app.services import OcrError, compare, ocr, preprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title="Alcohol Label Verifier")
allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST"], allow_headers=["*"], max_age=600)
lock = asyncio.Lock()
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_BATCH_BYTES = 20 * 1024 * 1024
MAX_BATCH_FILES = 20


class UploadError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers={"Cache-Control": "no-store"})


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, __: RequestValidationError):
    return error(422, "invalid_request", "Check the required fields and try again.")


@app.get("/health")
async def health():
    return {"status": "ok"}


def parse_application(application: str) -> ApplicationData | None:
    try:
        return ApplicationData.model_validate(json.loads(application))
    except (json.JSONDecodeError, ValidationError):
        return None


async def read_image(image: UploadFile) -> bytes:
    if image.content_type not in {"image/jpeg", "image/png"}:
        raise UploadError(415, "unsupported_image", "Upload a JPEG or PNG image under 5 MiB.")
    upload = await image.read()
    if len(upload) > MAX_FILE_BYTES:
        raise UploadError(413, "file_too_large", "Upload an image smaller than 5 MiB.")
    return upload


async def analyze_upload(upload: bytes, metadata: ApplicationData) -> AnalysisResult:
    started = time.perf_counter()
    image_data = await asyncio.to_thread(preprocess, upload)
    text, lines = await asyncio.to_thread(ocr, image_data)
    fields = compare(metadata, text, lines)
    elapsed = round((time.perf_counter() - started) * 1000)
    logger.info("analysis_complete processing_ms=%s image=%sx%s", elapsed, image_data.width, image_data.height)
    statuses = {field.status for field in fields}
    overall = FieldStatus.MISMATCH if FieldStatus.MISMATCH in statuses else FieldStatus.REVIEW if statuses & {FieldStatus.REVIEW, FieldStatus.MISSING} else FieldStatus.MATCH
    return AnalysisResult(overall_status=overall, processing_ms=elapsed, ocr_text=text, fields=fields, limitations=["OCR cannot verify warning boldness, type size, placement, or label completeness.", "Decorative fonts, glare, and perspective distortion may reduce OCR quality."])


@app.post("/analyze", response_model=AnalysisResult)
async def analyze(image: UploadFile = File(...), application: str = Form(...)):
    if lock.locked():
        return error(503, "service_busy", "Another label is being analyzed. Please try again in a moment.")
    await lock.acquire()
    try:
        metadata = parse_application(application)
        if metadata is None:
            return error(422, "invalid_application", "Check the application details and try again.")
        try:
            upload = await read_image(image)
        except UploadError as exc:
            return error(exc.status, exc.code, str(exc))
        result = await analyze_upload(upload, metadata)
        return JSONResponse(content=result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return error(422, "invalid_image", str(exc))
    except OcrError as exc:
        return error(422, "ocr_failed", str(exc))
    finally:
        await image.close()
        lock.release()


@app.post("/batch", response_model=BatchResult)
async def batch(images: list[UploadFile] = File(...), application: str = Form(...)):
    if lock.locked():
        return error(503, "service_busy", "Another label is being analyzed. Please try again in a moment.")
    await lock.acquire()
    try:
        if not 1 <= len(images) <= MAX_BATCH_FILES:
            return error(422, "invalid_batch", "Upload between one and 20 label images.")
        metadata = parse_application(application)
        if metadata is None:
            return error(422, "invalid_application", "Check the application details and try again.")
        payloads: list[tuple[str, bytes | None, str | None]] = []
        total_bytes = 0
        batch_too_large = False
        for image in images:
            try:
                if batch_too_large:
                    continue
                upload = await read_image(image)
                total_bytes += len(upload)
                if total_bytes > MAX_BATCH_BYTES:
                    batch_too_large = True
                    continue
                payloads.append((image.filename or "label", upload, None))
            except ValueError as exc:
                payloads.append((image.filename or "label", None, str(exc)))
            finally:
                await image.close()
        if batch_too_large:
            return error(413, "batch_too_large", "Keep total batch uploads under 20 MiB.")
        items: list[BatchItem] = []
        for filename, upload, upload_error in payloads:
            if upload_error:
                items.append(BatchItem(filename=filename, error=upload_error))
                continue
            try:
                items.append(BatchItem(filename=filename, result=await analyze_upload(upload or b"", metadata)))
            except (ValueError, OcrError) as exc:
                items.append(BatchItem(filename=filename, error=str(exc)))
        return JSONResponse(content=BatchResult(items=items).model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    finally:
        lock.release()
