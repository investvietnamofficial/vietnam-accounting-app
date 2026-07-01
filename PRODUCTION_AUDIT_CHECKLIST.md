# VN Accounting — Production Audit Checklist
**For:** Independent GLM Auditor | **Date:** 2026-07-01
**Repo:** `github.com/gilbertneo/vn-accounting` | **Branch:** `master`

> This checklist is designed to allow a complete independent audit without requiring access to production infrastructure. All verification steps can be performed from a local clone of the repository.

---

## How to Use This Checklist

1. Clone the repository: `git clone https://github.com/gilbertneo/vn-accounting`
2. Follow the **Local Setup** steps in Section 1
3. Work through each section below, checking off items
4. Record findings in the `Auditor Notes` column
5. Reference HANDOFF.md for architecture context

---

## Section 1: Local Environment Setup

**Objective:** Verify the auditor can reproduce the full environment locally.

- [ ] **1.1** Clone repo and checkout `master` branch
- [ ] **1.2** Python 3.11 available: `python3.11 --version`
- [ ] **1.3** PostgreSQL 15 running on port 5432
- [ ] **1.4** Database `vn_accounting` exists; user `vn_accounting` has access
- [ ] **1.5** Redis 7 running on port 6379 (optional for local dev)
- [ ] **1.6** Node.js 20+ available: `node --version`
- [ ] **1.7** Backend venv created and dependencies installed: `pip install -r backend/requirements.txt`
- [ ] **1.8** Alembic migrations applied: `PYTHONPATH=backend alembic -c backend/alembic.ini upgrade head`
- [ ] **1.9** `backend/.env` configured with test API keys (see Section 7 of HANDOFF.md)
- [ ] **1.10** Backend starts without errors: `uvicorn app.main:app --port 8000`
- [ ] **1.11** Health check passes: `curl http://localhost:8000/health`
- [ ] **1.12** Web starts without errors: `npm run dev` (in `web/` directory)
- [ ] **1.13** Web accessible at `http://localhost:3001`

**Auditor notes:**
```
1.1  Git commit verified: __________________________
1.11 Response: __________________________________
1.12 Build output: _______________________________
```

---

## Section 2: Authentication & Authorization

**Objective:** Verify JWT auth, role enforcement, and token security.

- [ ] **2.1** Registration works: `POST /api/v1/auth/register` with valid payload returns JWT
- [ ] **2.2** Login works: `POST /api/v1/auth/token` with valid credentials returns JWT
- [ ] **2.3** Invalid credentials return 401, not 500
- [ ] **2.4** Protected endpoint without token returns 401
- [ ] **2.5** Protected endpoint with valid token succeeds
- [ ] **2.6** Token expiry is enforced (wait or check `exp` claim)
- [ ] **2.7** Refresh token flow works: `POST /api/v1/auth/refresh`
- [ ] **2.8** User cannot access another company's documents (company_id gating)
- [ ] **2.9** Admin role can perform admin actions (if applicable)
- [ ] **2.10** `JWT_SECRET_KEY` is not hardcoded as `dev-jwt-secret` in production config
- [ ] **2.11** Password hashing uses bcrypt/argon2 (not plain text or MD5)
- [ ] **2.12** `bcrypt.checkpw()` verified in `app/core/security.py`

**Run these:**
```bash
# 2.1–2.3
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"audit@test.com","password":"AuditPass123!","full_name":"Auditor","company_name":"AuditCo","company_tax_code":"0000000001"}'

curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=audit%40test.com&password=AuditPass123%21"

curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=audit%40test.com&password=WRONGPASSWORD"
```

**Auditor notes:**
```
2.1  Register response: _______________________________
2.2  Login response (truncated): _____________________
2.4  No-token response: _______________________________
2.11 Hash check: ______________________________________
```

---

## Section 3: Document Upload Pipeline

**Objective:** Verify upload → OCR → extraction end-to-end with real data.

**Prerequisites:** Obtain a test PDF or image file. Use `/tmp/v2-test-invoice.pdf` if available locally.

- [ ] **3.1** Authenticate and obtain JWT token
- [ ] **3.2** Upload a valid PDF: `POST /api/v1/documents/upload`
- [ ] **3.3** Upload response includes `document_id` and `job_id`
- [ ] **3.4** Upload with unsupported MIME type returns 415
- [ ] **3.5** Upload exceeding 20MB returns 413
- [ ] **3.6** Poll `GET /api/v1/documents/{id}` and confirm status transitions: `pending` → `processing` → `extracted` (or `failed`)
- [ ] **3.7** Document reaches `extracted` status within 30 seconds
- [ ] **3.8** `extracted` document has `ocr_raw_text` populated
- [ ] **3.9** `extracted` document has `extracted_data` populated (JSON)
- [ ] **3.10** `extracted_data` contains all required fields: invoice_series, invoice_number, seller_name, total_amount, vat_rate, vat_amount
- [ ] **3.11** `ocr_confidence` is between 0.0 and 1.0
- [ ] **3.12** `extraction_confidence` is between 0.0 and 1.0
- [ ] **3.13** Duplicate upload is detected (same checksum) and returns `duplicate: true`
- [ ] **3.14** Invoice record auto-created in `invoices` table after extraction
- [ ] **3.15** All monetary values stored as integers (VND), not floats

**Run these:**
```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=audit%40test.com&password=AuditPass123%21" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3.2 Upload
RESULT=$(curl -s -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/v2-test-invoice.pdf;type=application/pdf" \
  -F "doc_type=invoice")
echo "$RESULT"

DOC_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")
sleep 20

# 3.6 Poll status
curl -s "http://localhost:8000/api/v1/documents/$DOC_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Auditor notes:**
```
3.2  Upload response: ________________________________
3.6  Final status: __________________________________
3.9  extracted_data keys: ___________________________
3.12 ocr_confidence: _________ extraction_confidence: _______
3.14 Invoice record found in DB: Yes/No
```

---

## Section 4: OCR Provider Verification

**Objective:** Confirm both OCR providers work correctly.

### 4A: PaddleOCR (Default)
- [ ] **4A.1** With `OCR_PROVIDER=paddle` (or unset), upload a document
- [ ] **4A.2** Document reaches `extracted` status
- [ ] **4A.3** `ocr_provider` field in response is `paddle` or unset
- [ ] **4A.4** `ocr_raw_text` contains extracted text from the document

### 4B: Google Vision
- [ ] **4B.1** Configure `GOOGLE_APPLICATION_CREDENTIALS_JSON` with valid service account JSON
- [ ] **4B.2** Set `OCR_PROVIDER=google`
- [ ] **4B.3** Restart backend
- [ ] **4B.4** Upload the same document
- [ ] **4B.5** Document reaches `extracted` status
- [ ] **4B.6** `ocr_provider` field is `google`
- [ ] **4B.7** `ocr_engine_version` contains `google-cloud-vision`
- [ ] **4B.8** `ocr_raw_text` contains extracted text
- [ ] **4B.9** Verify `s.text` fix in `google_vision.py` line ~383 — `s.symbol.text` must NOT appear

**Auditor notes:**
```
4A.2 PaddleOCR final status: _________________________
4B.6 Google Vision provider: _________________________
4B.7 OCR engine version: ____________________________
4B.9 s.symbol.text grep result: _____________________
```

---

## Section 5: LLM Extraction Provider Verification

**Objective:** Confirm all three extraction paths work.

### 5A: DeepSeek (Production)
- [ ] **5A.1** Configure `LLM_PROVIDER=deepseek` and `DEEPSEEK_API_KEY=sk-...`
- [ ] **5A.2** Upload a document and wait for extraction
- [ ] **5A.3** Document reaches `extracted` status
- [ ] **5A.4** `extracted_data` contains structured fields (not empty)
- [ ] **5A.5** No error in backend logs about DeepSeek API
- [ ] **5A.6** Backend logs show `deepseek` as the active provider

### 5B: Anthropic Claude (Fallback)
- [ ] **5B.1** Configure `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=sk-ant-...`
- [ ] **5B.2** Restart backend and repeat upload
- [ ] **5B.3** Document reaches `extracted` status with Claude extraction

### 5C: Regex Fallback (Offline/Dev)
- [ ] **5C.1** Set `LLM_PROVIDER=` (empty) and remove API keys
- [ ] **5C.2** Restart backend and repeat upload
- [ ] **5C.3** Document reaches `extracted` status using `RegexFallbackExtractor`
- [ ] **5C.4** Backend logs show regex extraction was used

**Auditor notes:**
```
5A.4 DeepSeek extracted_data: _______________________
5B.3 Claude extracted_data: ________________________
5C.3 Regex extracted_data: _________________________
```

---

## Section 6: VAT Reporting

**Objective:** Verify VAT declaration and XLSX export work.

- [ ] **6.1** At least one extracted invoice exists in the database
- [ ] **6.2** `POST /api/v1/reports/vat-declaration` returns a VAT declaration object
- [ ] **6.3** Declaration includes: total sales, taxable sales by rate, VAT payable
- [ ] **6.4** All monetary values match the invoice data
- [ ] **6.5** `GET /api/v1/reports/vat-declaration/xlsx` returns a downloadable XLSX file
- [ ] **6.6** XLSX file is valid (opens in Excel or LibreOffice)
- [ ] **6.7** XLSX contains multiple sheets: declaration + annexes
- [ ] **6.8** `GET /api/v1/reports/invoices` returns invoice list
- [ ] **6.9** Invoice records match the extracted documents

**Run these:**
```bash
# 6.2
curl -s "http://localhost:8000/api/v1/reports/vat-declaration" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 6.5
curl -s -o /tmp/vat-declaration.xlsx \
  "http://localhost:8000/api/v1/reports/vat-declaration/xlsx" \
  -H "Authorization: Bearer $TOKEN"
file /tmp/vat-declaration.xlsx
```

**Auditor notes:**
```
6.3  VAT payable: __________________________________
6.5  XLSX file size: ________________________________
6.6  File type verification: ________________________
```

---

## Section 7: GDT E-Invoice Verification

**Objective:** Verify graceful degradation when GDT is not configured.

- [ ] **7.1** `einvoice_status` defaults to `not_registered` for new invoices
- [ ] **7.2** Calling GDT verification without credentials does NOT crash the server
- [ ] **7.3** Backend logs show a clear "GDT not configured" message
- [ ] **7.4** Invoice record is not corrupted after failed GDT verification

**Auditor notes:**
```
7.1  Default einvoice_status: _______________________
7.3  Log message: _________________________________
```

---

## Section 8: Database Integrity

**Objective:** Verify schema correctness and data integrity.

- [ ] **8.1** All tables have proper primary keys (UUID)
- [ ] **8.2** Foreign key constraints are enforced (documents → companies, users → companies)
- [ ] **8.3** `documentstatus` enum only allows valid values: pending, processing, extracted, failed, rejected
- [ ] **8.4** `documenttype` enum only allows: invoice, receipt, contract, other
- [ ] **8.5** Monetary columns (subtotal_amount, vat_amount, total_amount) are BIGINT, not FLOAT/DECIMAL
- [ ] **8.6** `file_checksum` is VARCHAR(64) to hold SHA-256 hex
- [ ] **8.7** No NULL values in required columns for extracted documents
- [ ] **8.8** `documents.ocr_pages` is valid JSONB
- [ ] **8.9** `documents.extracted_data` is valid JSONB
- [ ] **8.10** Alembic migration history is linear (no branching)

**Run these:**
```bash
# 8.1–8.10
psql -U vn_accounting -d vn_accounting -c "\d companies"
psql -U vn_accounting -d vn_accounting -c "\d users"
psql -U vn_accounting -d vn_accounting -c "\d documents"
psql -U vn_accounting -d vn_accounting -c "\d invoices"
psql -U vn_accounting -d vn_accounting -c "\d alembic_version"
```

**Auditor notes:**
```
8.5  Column types: _________________________________
8.8  ocr_pages sample (first 200 chars): ____________
8.9  extracted_data sample (first 200 chars): ________
```

---

## Section 9: Security Audit

**Objective:** Identify security issues before production.

- [ ] **9.1** No credentials hardcoded in source files (search for `password`, `secret`, `api_key` in `.py` files excluding `*_test.py` and `.env`)
- [ ] **9.2** `.env` is listed in `.gitignore`
- [ ] **9.3** `JWT_SECRET_KEY` is not the literal string `dev-jwt-secret` in production config
- [ ] **9.4** SQL injection: try injecting SQL in `GET /api/v1/documents?status_filter='; DROP TABLE documents;--` — should not execute
- [ ] **9.5** Auth bypass: user A cannot access user B's company data by manipulating document_id
- [ ] **9.6** No `eval()`, `exec()`, or `ast.literal_eval` with user input in the codebase
- [ ] **9.7** File upload does not allow path traversal (no `../` in filename)
- [ ] **9.8** No sensitive data logged (passwords, API keys in logs)
- [ ] **9.9** CORS is restricted to known origins, not `*`
- [ ] **9.10** JWT tokens have reasonable expiry (≤ 60 minutes for access tokens)

**Run these:**
```bash
# 9.1
grep -rn "password\s*=" --include="*.py" backend/app/ | grep -v "_test.py" | grep -v "\.env\|#\|password123\|TestPass"

# 9.2
grep "\.env" .gitignore

# 9.4
curl -s "http://localhost:8000/api/v1/documents?status_filter=pending';DROP TABLE documents;--" \
  -H "Authorization: Bearer $TOKEN"

# 9.7
grep -rn "Path\|open(" --include="*.py" backend/app/api/ | grep -v "_test.py"
```

**Auditor notes:**
```
9.1  Credential leaks found: _________________________
9.4  SQL injection test result: _____________________
9.7  File path handling: ____________________________
```

---

## Section 10: Code Quality

**Objective:** Verify code is production-grade, not prototype code.

- [ ] **10.1** No `print()` statements in production code (use `logging` instead)
- [ ] **10.2** No `# TODO` comments with unresolved items
- [ ] **10.3** No commented-out code blocks in the codebase
- [ ] **10.4** All exceptions are handled, not silently swallowed
- [ ] **10.5** Background tasks have timeout handling
- [ ] **10.6** Document processing has retry logic (or is idempotent)
- [ ] **10.7** API responses use consistent error format (`{"detail": "..."}`)
- [ ] **10.8** Input validation on all user-facing endpoints
- [ ] **10.9** No hardcoded magic numbers without constants
- [ ] **10.10** Functions and classes have docstrings (especially public API methods)

**Run these:**
```bash
# 10.1
grep -rn "print(" --include="*.py" backend/app/ | grep -v "_test.py\|test_\|# print\|logger\|debug\|logging"

# 10.2
grep -rn "TODO\|FIXME\|XXX\|HACK" --include="*.py" backend/app/ | grep -v "_test.py"

# 10.3
grep -rn "^[[:space:]]*# " --include="*.py" backend/app/ | wc -l
```

**Auditor notes:**
```
10.1 print() statements found: _____________________
10.2 TODO/FIXME items: ____________________________
```

---

## Section 11: Duplicate Upload Retry Logic

**Objective:** Verify the fix applied in this audit cycle.

- [ ] **11.1** Upload the same file twice
- [ ] **11.2** First upload: `status=pending`, `duplicate=false`
- [ ] **11.3** Second upload with same checksum: `status=pending`, `duplicate=true`, `message` contains "re-queued"
- [ ] **11.4** Second document eventually reaches `extracted` (not stuck at `pending`)
- [ ] **11.5** If first document was `failed`, second upload also re-queues it
- [ ] **11.6** If first document was `extracted`, second upload returns the existing `document_id` without re-processing

**Run these:**
```bash
# Upload twice
curl -s -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/v2-test-invoice.pdf;type=application/pdf" \
  -F "doc_type=invoice"

sleep 20

# Check both docs
curl -s "http://localhost:8000/api/v1/documents" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; [print(d['id'], d['status'], d.get('duplicate', False)) for d in json.load(sys.stdin)['documents']]"
```

**Auditor notes:**
```
11.2 First upload response: __________________________
11.3 Second upload response: ________________________
11.4 Final status of re-queued doc: _________________
```

---

## Section 12: Docker & Deployment Readiness

- [ ] **12.1** `docker compose up --build` succeeds without errors
- [ ] **12.2** All three services (backend, web, postgres) start
- [ ] **12.3** `docker compose ps` shows all services as `running`
- [ ] **12.4** Backend health check passes inside Docker network
- [ ] **12.5** `DATABASE_URL_SYNC` has `?sslmode=disable` (PostgreSQL inside Docker)
- [ ] **12.6** No `npm ci` in production Dockerfile (should use `npm install`)
- [ ] **12.7** `web/Dockerfile` builds successfully
- [ ] **12.8** Docker volumes are defined for persistent storage

**Auditor notes:**
```
12.3 Service status: _________________________________
12.5 DATABASE_URL_SYNC check: _______________________
```

---

## Section 13: Summary Findings

Complete this section after finishing all checks.

### Passed Items
```
(total: ___ / 13 sections completed)
```

### Failed Items
```
List any items that FAILED with severity (CRITICAL/HIGH/MEDIUM/LOW)
```

### Severity Definitions
- **CRITICAL:** Data loss risk, security breach, or complete functional failure
- **HIGH:** Major feature broken or significant security concern
- **MEDIUM:** Feature impaired or moderate security concern
- **LOW:** Minor issue, cosmetic, or best practice

### CRITICAL Issues Found
```
1.
2.
3.
```

### HIGH Issues Found
```
1.
2.
3.
```

### MEDIUM Issues Found
```
1.
2.
```

### LOW Issues Found
```
1.
2.
```

---

## Auditor Sign-Off

| Field | Value |
|-------|-------|
| Auditor name | |
| Date of audit | |
| Commit audited | |
| Environment | Local / Docker / Other |
| Overall verdict | ✅ PASS / ⚠️ CONDITIONAL PASS / ❌ FAIL |

**Verdict criteria:**
- ✅ PASS: No CRITICAL issues; ≤ 2 HIGH issues
- ⚠️ CONDITIONAL PASS: ≤ 2 CRITICAL issues; HIGH issues acknowledged
- ❌ FAIL: > 2 CRITICAL issues or unresolved security vulnerabilities
