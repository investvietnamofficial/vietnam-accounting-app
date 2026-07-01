# Google Cloud Vision OCR Setup Guide

Production OCR for Vietnam Accounting App via Google Cloud Vision API.

---

## Overview

The app supports three OCR engines selected via `OCR_ENGINE`:

| Engine | Use Case | Speed | Cost |
|--------|----------|-------|------|
| `google` | **Production default** | ~1-3s/page | Pay-per-use (~$1.50/1000 pages) |
| `paddle` | Offline fallback | 60-120s/page (no GPU) | Free (local) |
| `mock` | Development / testing | Instant | Free |

This guide covers setting up Google Cloud Vision for production.

---

## Step 1: Create a GCP Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **Select a project** → **New Project**
3. Name it (e.g. `vn-accounting-ocr`)
4. Note your **Project ID** — you'll need it for `GOOGLE_CLOUD_PROJECT`

---

## Step 2: Enable the Vision API

1. In GCP Console, go to **APIs & Services** → **Library**
2. Search for **Cloud Vision API**
3. Click **Enable**

If you prefer the CLI:
```bash
gcloud services enable vision.googleapis.com --project=YOUR_PROJECT_ID
```

---

## Step 3: Create a Service Account

Google Cloud Vision requires a service account with the **Cloud Vision API User** role.

### Via Console:

1. Go to **IAM & Admin** → **Service Accounts** → **+ Create Service Account**
2. Name: `vn-accounting-ocr`
3. Grant role: **Cloud Vision API User** (`roles/vision.user`)
4. **Done** → click the service account → **Keys** tab → **Add Key** → **JSON**
5. Download the JSON file — **do not commit it to git**

### Via CLI:

```bash
gcloud iam service-accounts create vn-accounting-ocr \
  --display-name="Vietnam Accounting OCR" \
  --project=YOUR_PROJECT_ID

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:vn-accounting-ocr@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/vision.user"

gcloud iam service-accounts keys create key.json \
  --iam-account=vn-accounting-ocr@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

---

## Step 4: Choose Credential Method

### Option A: Paste JSON as Environment Variable (Recommended for Coolify)

This is the easiest method for Cloudify/Docker — just paste the full JSON into an env var.

1. Open the downloaded service account JSON
2. Copy the **entire contents**
3. Paste into the Coolify environment variable `GOOGLE_CLOUD_CREDENTIALS_JSON`

**Coolify steps:**
1. Open your app → **Environment Variables**
2. Add: `GOOGLE_CLOUD_CREDENTIALS_JSON` = paste the full JSON (single line or multiline)
3. Save and redeploy

**⚠️ Gotcha:** If the JSON spans multiple lines in the Coolify form, use `\n` for newlines, or paste into a file and use Option B instead.

### Option B: Mount Credentials File

Mount the JSON file into the container and point to it via env var.

1. Copy `key.json` to your server (e.g. `/app/secrets/google.json`)
2. Set environment variable: `GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/google.json`
3. Ensure the file is readable by the app user (chmod 600)

### Option C: Application Default Credentials (GCP-hosted)

If running on Cloud Run, GCE, GKE, or Cloud Functions, the service account is automatically used — no env vars needed.

```bash
gcloud auth activate-service-account \
  --key-file=key.json
```

---

## Step 5: Configure Environment Variables

Set these in Coolify (or your `.env` for local testing):

```env
# Required
OCR_ENGINE=google
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# Option A: paste JSON string (recommended for Coolify)
GOOGLE_CLOUD_CREDENTIALS_JSON={"type":"service_account","project_id":"your-gcp-project-id","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"...@....iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}

# Option B: path to file (if using Option A, leave blank)
GOOGLE_APPLICATION_CREDENTIALS=

# Optional tuning
OCR_TIMEOUT_SECONDS=60
```

---

## Step 6: Verify Setup

Test that credentials are accepted by running:

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test-invoice.pdf;type=application/pdf" \
  -F "doc_type=invoice"
```

Then check the document record:

```bash
curl http://localhost:8000/api/v1/documents/{document_id} \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool | grep -E "ocr_provider|ocr_page_count|ocr_duration_ms|ocr_warnings"
```

Expected output (after real credentials):
```json
"ocr_provider": "google",
"ocr_page_count": 1,
"ocr_duration_ms": 1340,
"ocr_warnings": null,
```

---

## Step 7: Monitor Usage & Costs

Google Cloud Vision pricing (as of 2024):

| Feature | Price |
|---------|-------|
| DOCUMENT_TEXT_DETECTION (per 1,000 pages) | ~$1.50 |
| First 1,000 pages/month | Free |

Set a billing alert in GCP to avoid surprises:
1. **Billing** → **Budgets & alerts** → **Create budget**
2. Set amount (e.g. $10/month)
3. Add email alert at 50%, 90%, 100%

---

## Troubleshooting

### "Google Cloud Vision credentials not found"

**Cause:** Neither `GOOGLE_CLOUD_CREDENTIALS_JSON` nor `GOOGLE_APPLICATION_CREDENTIALS` is set, and no ADC is found.

**Fix:**
```bash
# Check if ADC is configured
gcloud auth application-default print-access-token
```

If that fails, use `GOOGLE_CLOUD_CREDENTIALS_JSON` with the pasted JSON.

---

### "Permission 'vision.users' denied"

**Cause:** Service account lacks the Vision API User role.

**Fix:**
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:vn-accounting-ocr@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/vision.user"
```

---

### "REQUEST_LIMIT_EXCEEDED" or "Rate Limit Exceeded"

**Cause:** Too many concurrent OCR requests.

**Fix:** The app queues documents sequentially per worker. If you have multiple workers, add a rate-limit delay or contact GCP support to increase quota.

---

### Slow OCR processing (5+ seconds per page)

**Possible causes:**
1. Very large images (>20MB) — the app resizes to max 4096px, but very high-DPI scans can still be slow
2. PDF with 50+ pages — process in smaller batches
3. Network latency to GCP from your server

**Fix:** Compress images before upload (300 DPI is sufficient for OCR).

---

### OCR returns empty text

**Possible causes:**
1. Image is too dark, blurry, or has no text
2. Image is a screenshot of a UI (not a scanned document)
3. PDF is a vector/embedded file without embedded text

**Fix:** Ensure documents are:
- Scanned at ≥150 DPI
- Not heavily compressed (avoid JPEG quality < 70)
- Face-up, flat, and not folded

---

### "GOOGLE_CLOUD_CREDENTIALS_JSON is not valid JSON"

**Cause:** Newlines in the JSON broke the env var.

**Fix:** Replace actual newlines in the private key with `\n`:
```bash
# Before pasting into Coolify
cat key.json | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))"
```
Use the output as the value of `GOOGLE_CLOUD_CREDENTIALS_JSON`.

Or use `GOOGLE_APPLICATION_CREDENTIALS` with a mounted file instead.

---

## Switching OCR Engines

```env
# Production (Google Cloud Vision)
OCR_ENGINE=google

# Offline fallback (PaddleOCR — no internet needed, slow on CPU)
OCR_ENGINE=paddle

# Development (instant mock — no API calls)
OCR_ENGINE=mock
```

The switch is zero-downtime — just change the env var and redeploy.

---

## IAM Permissions Reference

| Role | Permissions |
|------|-------------|
| `roles/vision.user` | Full Vision API access — sufficient for production |
| `roles/vision.editor` | Includes Vision API management — too broad |
| `roles/viewer` | Read-only — insufficient for OCR |

Minimum required permissions:
- `vision.images.annotate`
- `vision.files.annotate` (for async batch operations)
