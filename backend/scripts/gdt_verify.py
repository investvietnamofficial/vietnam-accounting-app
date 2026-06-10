#!/usr/bin/env python3
"""CLI helper to run one-off GDT invoice verification."""

import argparse
import asyncio
import json

from app.services.einvoice import GDTInvoiceVerificationService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Vietnamese e-invoice against GDT")
    parser.add_argument("--series", required=True, help="Invoice series (ky hieu), e.g. AA/23E")
    parser.add_argument("--number", required=True, help="Invoice number (so hoa don)")
    parser.add_argument("--tax-code", default=None, help="Tax code (MST) of seller or buyer")
    parser.add_argument("--json", action="store_true", help="Output raw JSON only")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    service = GDTInvoiceVerificationService()
    result = await service.verify_invoice(
        invoice_series=args.series,
        invoice_number=args.number,
        tax_code=args.tax_code,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("verified:", result.get("verified"))
    print("status:", result.get("status"))
    print("status_code:", result.get("status_code"))
    print("message:", result.get("gdt_message"))
    print("tax_code:", result.get("tax_code"))
    if result.get("raw") is not None:
        print("raw:", json.dumps(result["raw"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
