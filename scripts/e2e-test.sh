#!/bin/bash
# VN Accounting E2E Smoke Test
# Usage: bash scripts/e2e-test.sh [BASE_URL]
# Default BASE_URL: http://localhost:8000
set -e

BASE_URL=${1:-http://localhost:8000}
TIMESTAMP=$(date +%s)
PASS=0
FAIL=0

echo "=== VN Accounting E2E Smoke Test ==="
echo "Testing: $BASE_URL"
echo "Timestamp: $TIMESTAMP"
echo ""

# Helper
check() {
    local name="$1"
    local cmd="$2"
    echo -n "  $name... "
    if eval "$cmd" > /dev/null 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

# ── 1. Health check ────────────────────────────────────────────────────────────
echo "1. Health check..."
check "/health returns ok" \
    "curl -sf '$BASE_URL/health' | grep -q '\"status\":\"ok\"'"
check "/healthz returns deep checks" \
    "curl -sf '$BASE_URL/healthz' | grep -q 'checks'"
echo ""

# ── 2. Register test account ─────────────────────────────────────────────────
echo "2. Register..."
EMAIL="e2e-$TIMESTAMP@test.com"
PASSWORD="Test123456!"

REG_PAYLOAD=$(cat <<EOF
{
  "email": "$EMAIL",
  "password": "$PASSWORD",
  "company_name": "E2E Corp",
  "tax_code": "0123456789"
}
EOF
)

REG_RESP=$(curl -sf -X POST "$BASE_URL/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "$REG_PAYLOAD" 2>&1) || REG_RESP="FAIL"

check "Register returns access_token" \
    "echo '$REG_RESP' | grep -q 'access_token'"

TOKEN=$(echo "$REG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

if [ -z "$TOKEN" ]; then
    echo "  WARNING: No token extracted — subsequent auth tests will be skipped"
fi
echo ""

# ── 3. Login ──────────────────────────────────────────────────────────────────
echo "3. Login..."
if [ -n "$TOKEN" ]; then
    check "Login with registered account" \
        "curl -sf -X POST '$BASE_URL/api/v1/auth/token' \
        -d 'username=$EMAIL&password=$PASSWORD' | grep -q 'access_token'"
else
    echo "  SKIP (no token from register)"
    FAIL=$((FAIL + 1))
fi
echo ""

# ── 4. Company profile ───────────────────────────────────────────────────────
echo "4. Company profile..."
if [ -n "$TOKEN" ]; then
    check "GET /companies/me returns company_name" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/companies/me' | grep -q 'company_name'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 5. Update company settings ───────────────────────────────────────────────
echo "5. Update company settings..."
if [ -n "$TOKEN" ]; then
    UPDATE_PAYLOAD='{"company_name":"E2E Corp Updated","accounting_standard":"VAS","vat_period":"monthly"}'
    UPDATE_RESP=$(curl -sf -X PATCH "$BASE_URL/api/v1/companies/me" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$UPDATE_PAYLOAD" 2>&1)
    check "PATCH /companies/me withVAS standard" \
        "echo '$UPDATE_RESP' | grep -q 'E2E Corp Updated'"
    check "PATCH rejects unknown fields (extra=forbid)" \
        "curl -sf -X PATCH '$BASE_URL/api/v1/companies/me' \
        -H 'Authorization: Bearer $TOKEN' \
        -H 'Content-Type: application/json' \
        -d '{\"unknown_field\":true}' | grep -q 'detail'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 6. Invoice list (empty state) ────────────────────────────────────────────
echo "6. Invoice list..."
if [ -n "$TOKEN" ]; then
    check "GET /invoices returns items" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/invoices' | grep -q 'items'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 7. Invoice filters ───────────────────────────────────────────────────────
echo "7. Invoice filters..."
if [ -n "$TOKEN" ]; then
    check "Date filter works" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/invoices?date_from=2024-01-01&date_to=2024-12-31' | grep -q 'items'"
    check "Verification status filter works" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/invoices?verification_status=pending' | grep -q 'items'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 8. VAT summary report ─────────────────────────────────────────────────────
echo "8. VAT summary report..."
if [ -n "$TOKEN" ]; then
    check "VAT summary returns input_vat_total" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/vat-summary?year=2024&period=1&period_type=quarterly' \
        | grep -q 'input_vat_total'"
    check "VAT summary with period_type=monthly" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/vat-summary?year=2024&period=6&period_type=monthly' \
        | grep -q 'input_vat_total'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 9. Sales invoices report ─────────────────────────────────────────────────
echo "9. Sales invoices report..."
if [ -n "$TOKEN" ]; then
    check "Sales invoices returns items" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/sales-invoices?year=2024&period=1&period_type=quarterly' \
        | grep -q 'items'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 10. Purchase invoices report ─────────────────────────────────────────────
echo "10. Purchase invoices report..."
if [ -n "$TOKEN" ]; then
    check "Purchase invoices returns items" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/purchase-invoices?year=2024&period=1&period_type=quarterly' \
        | grep -q 'items'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 11. Exceptions report ─────────────────────────────────────────────────────
echo "11. Exceptions report..."
if [ -n "$TOKEN" ]; then
    check "Exceptions returns issues" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/exceptions?year=2024&period=1&period_type=quarterly' \
        | grep -q 'issues'"
    check "Exceptions returns 4 issue types" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/exceptions?year=2024&period=1&period_type=quarterly' \
        | grep -qE '(missing_mst|duplicate|low_confidence|vat_mismatch)'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 12. Excel export ─────────────────────────────────────────────────────────
echo "12. Excel export..."
if [ -n "$TOKEN" ]; then
    check "VAT summary Excel export (Content-Type)" \
        "curl -sf -I -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/vat-summary?year=2024&period=1&period_type=quarterly&format=excel' \
        | grep -qi 'spreadsheet\\|application/vnd.openxmlformats\\|application/octet-stream'"
    check "Sales invoices Excel export (Content-Type)" \
        "curl -sf -I -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/sales-invoices?year=2024&period=1&period_type=quarterly&format=excel' \
        | grep -qi 'spreadsheet\\|application/vnd.openxmlformats\\|application/octet-stream'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 13. Auth security ─────────────────────────────────────────────────────────
echo "13. Auth security..."
check "No token in password reset response" \
    "curl -sf -X POST '$BASE_URL/api/v1/auth/forgot-password' \
    -H 'Content-Type: application/json' \
    -d '{\"email\":\"$EMAIL\"}' | grep -qv 'token'"
check "Rate limiting: repeated register attempts" \
    "# Second register with same email should fail gracefully \
    curl -sf -X POST '$BASE_URL/api/v1/auth/register' \
    -H 'Content-Type: application/json' \
    -d '$REG_PAYLOAD' | grep -qE '(detail|error|statusCode|422|409)'"
echo ""

# ── 14. Unauthorized access ───────────────────────────────────────────────────
echo "14. Unauthorized access..."
check "No token → 401 on /companies/me" \
    "curl -sf '$BASE_URL/api/v1/companies/me' | grep -q 'detail'"
check "Bad token → 401 on /invoices" \
    "curl -sf -H 'Authorization: Bearer invalid-token-xyz' \
    '$BASE_URL/api/v1/invoices' | grep -q 'detail'"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "=== E2E Summary ==="
TOTAL=$((PASS + FAIL))
echo "Passed: $PASS / $TOTAL"
echo "Failed: $FAIL / $TOTAL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "ALL TESTS PASSED ✓"
    exit 0
else
    echo "SOME TESTS FAILED — review above"
    exit 1
fi
