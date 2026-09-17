# Alcohol label verifier

A standalone prototype that compares a distilled-spirit label image to application data. The browser sends the image and metadata to FastAPI. The API preprocesses the image, runs local Tesseract OCR, extracts fields, and returns explainable deterministic checks.

## Run locally

Start the API:

```bash
cd label-verifier-api
uv sync --dev
uv run uvicorn app.main:app --reload
```

Start the web application in another terminal:

```bash
cd label-verifier-web
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Install Tesseract with English language data before running the API. On macOS, `brew install tesseract` installs it. Run backend tests with `uv run pytest` and build the web application with `npm run build`.

Create synthetic manual-test labels with:

```bash
cd label-verifier-api
uv run python scripts/generate_sample_labels.py
```

Upload `samples/01-perfect-match.png` with the default application form. The remaining images intentionally contain an ABV mismatch, volume mismatch, title-case warning heading, or slight rotation.

## Deployment

Deploy `label-verifier-web` to Vercel and set `NEXT_PUBLIC_API_URL` to the Railway API URL at build time. Deploy `label-verifier-api` as a Railway Docker service, using its `Dockerfile`, service root, and `/health` as the healthcheck. Add the Vercel URL to the backend CORS allowlist before deployment.

## Limits

This prototype has no COLA integration, accounts, persistent storage, audit log, producer/address checks, or beverage-specific rules. It supports one JPEG or PNG up to 5 MiB. OCR quality falls with glare, perspective distortion, decorative fonts, or very small text. The warning check validates wording and uppercase heading only. Agents must inspect boldness, type size, placement, and whether a label has all required panels. A production federal deployment would need authorized infrastructure, retention controls, access controls, and audit requirements.
