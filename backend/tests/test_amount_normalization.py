"""M-9: Amount normalization — Vietnamese, US, European, OCR edge cases."""
import pytest
import sys

sys.path.insert(0, "/Users/gilbertneo/Desktop/My Apps/Vietnam Accounting App/vn-accounting/backend")

from app.services.extraction.claude_extractor import ExtractionService


@pytest.fixture
def extractor():
    return ExtractionService()


def norm(extractor, v):
    return extractor._normalize_amount_string(v)


class TestVietnamese:
    def test_dot_thousand_separator(self, extractor):
        assert norm(extractor, "1.500.000") == 1_500_000

    def test_dot_with_decimal_comma(self, extractor):
        assert norm(extractor, "1.500.000,50") == 1_500_000

    def test_short_dot_format(self, extractor):
        assert norm(extractor, "1.500") == 1_500


class TestEuropean:
    def test_comma_decimal_dot_thousand(self, extractor):
        assert norm(extractor, "1,500.50") == 1_500

    def test_large_european(self, extractor):
        assert norm(extractor, "1,000,000.99") == 1_000_000


class TestUS:
    def test_comma_thousand_dot_decimal(self, extractor):
        assert norm(extractor, "1,500.00") == 1_500

    def test_large_us(self, extractor):
        assert norm(extractor, "2,500,000") == 2_500_000


class TestOcrSpaces:
    def test_nbsp_thin_space(self, extractor):
        assert norm(extractor, "1 500 000") == 1_500_000

    def test_space_with_decimal(self, extractor):
        assert norm(extractor, "1 500.50") == 1_500


class TestCurrencySymbols:
    def test_vnd_symbol(self, extractor):
        assert norm(extractor, "1.500.000 \u20ab") == 1_500_000

    def test_dollar_symbol(self, extractor):
        assert norm(extractor, "$2,500.00") == 2_500


class TestNegative:
    def test_negative_vietnamese(self, extractor):
        assert norm(extractor, "-1.500.000") == -1_500_000


class TestPlain:
    def test_plain_integer(self, extractor):
        assert norm(extractor, "1500000") == 1_500_000


class TestInvalid:
    def test_empty_string(self, extractor):
        assert norm(extractor, "") is None

    def test_non_numeric(self, extractor):
        assert norm(extractor, "ABC") is None

    def test_whitespace_only(self, extractor):
        assert norm(extractor, "   ") is None
