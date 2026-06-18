// ============================================================
// Core domain types — mirrors backend Pydantic schemas
// ============================================================

export type UserRole = "admin" | "accountant" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  company_id: string | null;
  created_at: string;
}

export interface Company {
  id: string;
  name: string;
  name_en: string | null;
  tax_code: string; // MST
  address: string | null;
  accounting_standard: "TT200" | "TT133";
  vat_declaration_period: "monthly" | "quarterly";
  fiscal_year_start_month: number;
}

// ============================================================
// Documents
// ============================================================

export type DocumentStatus =
  | "uploaded"
  | "pending"
  | "processing"
  | "extracted"
  | "verified"
  | "failed";

export type DocumentType =
  | "invoice_vat"
  | "invoice_sale"
  | "receipt"
  | "contract"
  | "bank_statement"
  | "other";

export interface Document {
  id: string;
  company_id: string;
  file_name: string;
  file_url: string;
  file_size_bytes: number;
  mime_type: string;
  doc_type: DocumentType;
  status: DocumentStatus;
  ocr_confidence: number | null;
  extraction_confidence: number | null;
  extracted_data: ExtractedInvoiceData | null;
  processing_error: string | null;
  processing_attempts: number | null;
  processed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  document_id: string;
  job_id: string;
  status: "pending";
  message: string;
}

// ============================================================
// Invoices
// ============================================================

export type VATRate = "0" | "5" | "8" | "10" | "exempt" | "na";

export interface LineItem {
  name: string;
  unit: string | null;
  quantity: number | null;
  unit_price: number | null; // VND
  amount: number; // VND
  vat_rate?: VATRate;
}

export interface ExtractedInvoiceData {
  invoice_series: string | null;
  invoice_number: string | null;
  invoice_date: string | null; // ISO date
  invoice_type: DocumentType;
  seller_name: string | null;
  seller_tax_code: string | null;
  seller_address: string | null;
  buyer_name: string | null;
  buyer_tax_code: string | null;
  buyer_address: string | null;
  subtotal_amount: number | null; // VND
  vat_rate: VATRate;
  vat_amount: number | null; // VND
  total_amount: number | null; // VND
  line_items: LineItem[];
  einvoice_code: string | null;
  notes: string | null;
  confidence: number; // 0-1
}

export interface Invoice extends ExtractedInvoiceData {
  id: string;
  company_id: string;
  document_id: string;
  einvoice_verified: boolean;
  einvoice_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Journal Entries
// ============================================================

export type JournalEntryStatus = "draft" | "posted" | "reversed";

export interface JournalEntryLine {
  id: string;
  debit_account_code: string | null;
  credit_account_code: string | null;
  amount: number; // VND
  description: string | null;
}

export interface JournalEntry {
  id: string;
  company_id: string;
  invoice_id: string | null;
  entry_date: string;
  reference: string | null;
  description: string;
  status: JournalEntryStatus;
  total_amount: number; // VND
  lines: JournalEntryLine[];
  created_at: string;
}

// ============================================================
// Reports
// ============================================================

export interface VATSummary {
  year: number;
  period: number;
  period_type: "monthly" | "quarterly";
  input_vat_total: number; // VND — deductible input VAT
  output_vat_total: number; // VND — output VAT payable
  net_vat: number; // VND — positive = payable, negative = refundable
  payable_vat: number;
  carry_forward_vat: number;
  refund_requested_vat: number;
  by_rate: {
    rate: VATRate;
    input_amount: number;
    output_amount: number;
    input_vat: number;
    output_vat: number;
  }[];
  declaration_deadline: string; // ISO date
  filing_fields: Record<string, number | string | boolean>;
  inputs: {
    previous_vat_credit: number;
    import_purchase_value: number;
    import_purchase_vat: number;
    deductible_input_vat_override: number | null;
    adjustment_decrease: number;
    adjustment_increase: number;
    transferred_vat_credit: number;
    investment_project_offset_vat: number;
    refund_requested_vat: number;
  };
  purchase_annex: VATAnnex;
  sales_annex: VATAnnex;
  validation_issues: string[];
}

export interface CITSummary {
  year: number;
  quarter: number;
  revenue: number;
  deductible_expenses: number;
  other_income: number;
  other_expenses: number;
  accounting_profit: number;
  non_deductible_expenses: number;
  loss_carried_forward: number;
  taxable_income: number;
  cit_rate: number; // 0.20 etc.
  cit_amount: number;
  already_paid: number;
  amount_due: number;
  annual_cit_estimate: number | null;
  minimum_cumulative_payment: number | null;
  due_date: string;
}

export interface VATAnnexRow {
  stt: number;
  id: string;
  direction: "purchase" | "sale";
  invoice_date: string | null;
  invoice_series: string | null;
  invoice_number: string | null;
  counterparty_name: string | null;
  counterparty_tax_code: string | null;
  seller_name: string | null;
  seller_tax_code: string | null;
  buyer_name: string | null;
  buyer_tax_code: string | null;
  subtotal_amount: number;
  vat_rate: VATRate;
  vat_amount: number;
  total_amount: number;
  einvoice_verified: boolean;
}

export interface VATAnnex {
  code: string;
  title: string;
  items: VATAnnexRow[];
  totals: {
    count: number;
    taxable_value: number;
    vat_amount: number;
    total_amount: number;
  };
}

// ============================================================
// API response wrappers
// ============================================================

export interface PaginatedResponse<T> {
  page: number;
  page_size: number;
  total: number;
  items: T[];
}

export interface APIError {
  detail: string;
  status_code?: number;
}

export interface AuthSession {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  fullName: string;
  companyName: string;
  companyTaxCode: string;
  email: string;
  password: string;
}

export interface ForgotPasswordResponse {
  message: string;
  reset_token?: string | null;
}

// ============================================================
// Company Settings
// ============================================================

export interface CompanySettings {
  id: string;
  name: string;
  tax_code: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  accounting_standard: "TT200" | "TT133";
  vat_declaration_period: "monthly" | "quarterly";
  fiscal_year_start_month: number;
}

// ============================================================
// Invoice List (with filters)
// ============================================================

export interface InvoiceListParams {
  page?: number;
  page_size?: number;
  date_from?: string;
  date_to?: string;
  vat_rate?: string;
  seller?: string;
  status?: string;
}

export interface InvoiceListResponse {
  page: number;
  page_size: number;
  total: number;
  items: Invoice[];
}

// ============================================================
// Report Types
// ============================================================

export interface ReportWarning {
  type: string;
  message: string;
  invoice_ids: string[];
}

export interface VatSummaryReport {
  year: number;
  period: number;
  period_type: "monthly" | "quarterly";
  input_vat_total: number;
  output_vat_total: number;
  net_vat: number;
  payable_vat: number;
  carry_forward_vat: number;
  refund_requested_vat: number;
  by_rate: {
    rate: VATRate;
    input_amount: number;
    output_amount: number;
    input_vat: number;
    output_vat: number;
  }[];
  declaration_deadline: string;
  filing_fields: Record<string, number | string | boolean>;
  inputs: {
    previous_vat_credit: number;
    import_purchase_value: number;
    import_purchase_vat: number;
    deductible_input_vat_override: number | null;
    adjustment_decrease: number;
    adjustment_increase: number;
    transferred_vat_credit: number;
    investment_project_offset_vat: number;
    refund_requested_vat: number;
  };
  purchase_annex: VATAnnex;
  sales_annex: VATAnnex;
  validation_issues: string[];
}

export interface InvoiceReportRow {
  stt: number;
  id: string;
  direction: "purchase" | "sale";
  invoice_date: string | null;
  invoice_series: string | null;
  invoice_number: string | null;
  counterparty_name: string | null;
  counterparty_tax_code: string | null;
  seller_name: string | null;
  seller_tax_code: string | null;
  buyer_name: string | null;
  buyer_tax_code: string | null;
  subtotal_amount: number;
  vat_rate: VATRate;
  vat_amount: number;
  total_amount: number;
  einvoice_verified: boolean;
  confidence?: number | null;
}

export interface SalesInvoicesReport {
  year: number;
  period: number;
  period_type: "monthly" | "quarterly";
  items: InvoiceReportRow[];
  total: number;
  period_label: string;
}

export interface PurchaseInvoicesReport {
  year: number;
  period: number;
  period_type: "monthly" | "quarterly";
  items: InvoiceReportRow[];
  total: number;
  period_label: string;
}

export interface ExceptionIssue {
  type: string;
  message: string;
  invoice_ids: string[];
  count: number;
}

export interface ExceptionsReport {
  year: number;
  period: number;
  period_type: "monthly" | "quarterly";
  issues: ExceptionIssue[];
  total_issues: number;
}

// ============================================================
// Document retry
// ============================================================

export interface RetryDocumentResponse {
  document_id: string;
  job_id: string;
  status: DocumentStatus;
  message: string;
}
