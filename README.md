# Alcohol Label Verifier

A standalone proof of concept for helping TTB compliance agents compare a distilled-spirit label image against submitted application details. It does not approve labels. It identifies automated matches, mismatches, missing values, and cases that need an agent's review.

## What it does

1. An agent enters application details and uploads a JPEG or PNG label image.
2. The API preprocesses the image and uses local Tesseract OCR to read label text.
3. Deterministic comparison rules check the extracted data against the application.
4. The interface shows expected and observed values, a plain-English reason, and the raw OCR text.

The optional batch flow checks up to 20 images against one set of application details. It reports an end-to-end elapsed time and lets agents expand mismatched files to inspect the affected fields.

## Architecture and tools

```text
Next.js frontend → FastAPI → Pillow preprocessing → Tesseract OCR → extraction and comparison rules
```

- **Frontend:** Next.js, TypeScript, Tailwind CSS, deployed to Vercel.
- **API:** Python 3.13, FastAPI, Pydantic, Pillow, and `pytesseract==0.3.13`, deployed to Railway with Docker.
- **OCR:** Tesseract 5 with English language data. OCR runs locally in the API container, with no external machine-learning service.
- **Storage:** none. Images and application data are processed in memory and are not persisted.

Deterministic rules are used where compliance checks need predictable behavior. Brand names use normalization and similarity-based review. ABV, proof, and volume use numeric conversion. The government warning check requires the specified wording and an uppercase `GOVERNMENT WARNING:` heading.

## Local setup

### Prerequisites

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js 20 or later
- Tesseract with English language data

On macOS:

```bash
brew install tesseract
```

Start the API:

```bash
cd label-verifier-api
uv sync --dev
uv run uvicorn app.main:app --reload
```

Start the frontend in another terminal:

```bash
cd label-verifier-web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000.

## Testing

Run API tests:

```bash
cd label-verifier-api
uv run pytest
```

Run frontend checks:

```bash
cd label-verifier-web
npm run lint
npx next build --webpack
```

Generate five synthetic labels for manual verification:

```bash
cd label-verifier-api
uv run python scripts/generate_sample_labels.py
```

`01-perfect-match.png` should match the default form values. The remaining fixtures demonstrate an incorrect ABV, incorrect volume, title-case warning heading, and a rotated image that shows OCR limits.

## Deployment

Deploy `label-verifier-web` to Vercel with this normal environment variable, scoped to Production and Preview:

```text
NEXT_PUBLIC_API_URL=https://<railway-api-domain>
```

Deploy `label-verifier-api` as a Railway Docker service.

- Set Railway **Root Directory** to `/label-verifier-api`.
- Set the healthcheck path to `/health`.
- Set `ALLOWED_ORIGINS` to the exact Vercel deployment origin, without a trailing slash:

```text
ALLOWED_ORIGINS=https://<vercel-app-domain>
```

Set the Railway watch path to `/label-verifier-api/**` to avoid redeploying the API when only frontend files change.

## Assumptions and limitations

- This prototype uses distilled spirits as its baseline. It does not implement every beer, wine, or beverage-specific label rule.
- Batch files share one application record. A production workflow would obtain per-label metadata from COLAs Online or a structured import.
- The prototype checks warning wording and capitalization. It cannot reliably verify boldness, physical type size, placement, contrast, or whether all label panels are present.
- OCR quality may degrade with glare, severe perspective distortion, decorative fonts, and very small text. Ambiguous values are shown for agent review rather than silently accepted.
- The prototype intentionally has no COLAs Online integration, authentication, persistent storage, audit log, or producer/address validation.
- A production federal implementation would require FedRAMP-authorized infrastructure, retention controls, access controls, and audit requirements.
