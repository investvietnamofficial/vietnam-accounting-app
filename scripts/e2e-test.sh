#!/bin/bash
# VN Accounting E2E Smoke Test
# Usage: bash scripts/e2e-test.sh [BASE_URL]
# Default BASE_URL: http://localhost:8000

BASE_URL=${1:-http://localhost:8000}
TIMESTAMP=$(date +%s)
PASS=0
FAIL=0

echo "=== VN Accounting E2E Smoke Test ==="
echo "Testing: $BASE_URL"
echo "Timestamp: $TIMESTAMP"
echo ""

# Helper - returns 0 on pass, 1 on fail (never exits)
check() {
    local name="$1"
    local cmd="$2"
    echo -n "  $name... "
    if eval "$cmd" > /dev/null 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
        return 0
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
        return 1
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
PASSWORD="Test12345678!"
TAX_CODE="012345678${TIMESTAMP: -4}"

REG_PAYLOAD=$(cat <<EOF
{
  "email": "$EMAIL",
  "password": "$PASSWORD",
  "full_name": "E2E Test User",
  "company_name": "E2E Corp",
  "company_tax_code": "$TAX_CODE"
}
EOF
)

REG_RESP=$(curl -sf -X POST "$BASE_URL/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "$REG_PAYLOAD" 2>&1) || REG_RESP=""

check "Register returns access_token" \
    "echo '$REG_RESP' | grep -q 'access_token'"

TOKEN=$(echo "$REG_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || echo "")

if [ -z "$TOKEN" ]; then
    echo "  WARNING: No token — subsequent auth tests will be SKIPPED"
fi
echo ""

# ── 3. Login ──────────────────────────────────────────────────────────────────
echo "3. Login..."
if [ -n "$TOKEN" ]; then
    check "Login with registered account" \
        "curl -sf -X POST '$BASE_URL/api/v1/auth/token' \
        -d 'username=$EMAIL&password=$PASSWORD' | grep -q 'access_token'"
else
    echo "  SKIP (no token)"
    FAIL=$((FAIL + 1))
fi
echo ""

# ── 4. Company profile ───────────────────────────────────────────────────────
echo "4. Company profile..."
if [ -n "$TOKEN" ]; then
    check "GET /companies/me returns company" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/companies/me' | grep -q '\"name\"'"
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
    check "PATCH /companies/me updates company" \
        "echo '$UPDATE_RESP' | grep -q 'E2E Corp Updated'"
    check "PATCH rejects unknown fields (extra=forbid)" \
        "curl -s -X PATCH '$BASE_URL/api/v1/companies/me' \
        -H 'Authorization: Bearer $TOKEN' \
        -H 'Content-Type: application/json' \
        -d '{\"unknown_field\":true}' | grep -q 'extra_forbidden'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 6. Invoice list ────────────────────────────────────────────────────────────
echo "6. Invoice list..."
if [ -n "$TOKEN" ]; then
    check "GET /invoices returns items" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/invoices/' | grep -q '\"items\"'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 7. Invoice filters ────────────────────────────────────────────────────────
echo "7. Invoice filters..."
if [ -n "$TOKEN" ]; then
    check "Date filter works" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/invoices/?date_from=2024-01-01&date_to=2024-12-31' | grep -q '\"items\"'"
    check "Verification status filter works" \
        "curl -sf -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/invoices/?verification_status=pending' | grep -q '\"items\"'"
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
    check "VAT summary monthly works" \
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
        | grep -q '\"items\"'"
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
        | grep -q '\"items\"'"
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
        | grep -q '\"issues\"'"
    # Issue types only appear when there are actual issues - skip this sub-check
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 12. Excel export ─────────────────────────────────────────────────────────
echo "12. Excel export..."
if [ -n "$TOKEN" ]; then
    # Check Content-Type header (must use GET, not HEAD, as endpoint only supports GET)
    check "VAT summary Excel (Content-Type)" \
        "curl -si -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/vat-summary?year=2024&period=1&period_type=quarterly&format=excel' \
        | head -20 | grep -ai 'content-type' | grep -qi 'spreadsheet\\|openxmlformats\\|octet-stream'"
    check "Sales invoices Excel (Content-Type)" \
        "curl -si -H 'Authorization: Bearer $TOKEN' \
        '$BASE_URL/api/v1/reports/sales-invoices?year=2024&period=1&period_type=quarterly&format=excel' \
        | head -20 | grep -ai 'content-type' | grep -qi 'spreadsheet\\|openxmlformats\\|octet-stream'"
else
    echo "  SKIP (no token)"
fi
echo ""

# ── 13. Auth security ──────────────────────────────────────────────────────────
echo "13. Auth security..."
# Note: password reset no longer returns token in response (Phase 2 fix)
# Check that the endpoint responds (email sending not testable without real SMTP)
check "Forgot password endpoint responds" \
    "curl -s -X POST '$BASE_URL/api/v1/auth/password/forgot' \
    -H 'Content-Type: application/json' \
    -d '{\"email\":\"$EMAIL\"}' | grep -qE 'detail|message|status'"
echo ""

# ── 14. Unauthorized access ───────────────────────────────────────────────────
echo "14. Unauthorized access..."
check "No token returns error on /companies/me" \
    "curl -s '$BASE_URL/api/v1/companies/me' | grep -q 'detail'"
check "Bad token returns error on /invoices/" \
    "curl -s -H 'Authorization: Bearer invalid-token-xyz' \
    '$BASE_URL/api/v1/invoices/' | grep -q 'detail'"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "=== E2E Summary ==="
TOTAL=$((PASS + FAIL))
echo "Passed: $PASS / $TOTAL"
echo "Failed: $FAIL / $TOTAL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "SOME TESTS FAILED — review above"
    exit 1
fi
