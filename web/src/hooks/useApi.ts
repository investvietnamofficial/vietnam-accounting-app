import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { companiesApi, documentsApi, invoicesApi, reportsApi } from "@/lib/api";
import type {
  CompanySettings,
  Document,
  Invoice,
  InvoiceListParams,
  RetryDocumentResponse,
  UploadResponse,
} from "@/types";

// ============================================================
// Documents
// ============================================================

export const useDocuments = (params?: { status?: string; page?: number }) =>
  useQuery({
    queryKey: ["documents", params],
    queryFn: () => documentsApi.list(params),
  });

export const useDocument = (id: string) =>
  useQuery({
    queryKey: ["documents", id],
    queryFn: () => documentsApi.get(id),
    enabled: !!id,
    // Poll every 2s while status is pending/processing
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "processing" ? 2000 : false;
    },
  });

export const useUploadDocument = () => {
  const qc = useQueryClient();
  return useMutation<UploadResponse, Error, { file: File; docType?: string }>({
    mutationFn: ({ file, docType }) => documentsApi.upload(file, docType),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
};

// ============================================================
// Invoices
// ============================================================

export const useInvoices = (params?: { page?: number }) =>
  useQuery({
    queryKey: ["invoices", params],
    queryFn: () => invoicesApi.list(params),
  });

export const useInvoice = (id: string) =>
  useQuery({
    queryKey: ["invoices", id],
    queryFn: () => invoicesApi.get(id),
    enabled: !!id,
  });

export const useVerifyEInvoice = (invoiceId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => invoicesApi.verifyEInvoice(invoiceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invoices"] }),
  });
};

// ============================================================
// Reports
// ============================================================

export const useVATSummary = (
  year: number,
  period: number,
  periodType: string,
  params?: {
    previousVatCredit?: number;
    importPurchaseValue?: number;
    importPurchaseVat?: number;
    deductibleInputVatOverride?: number | null;
    adjustmentDecrease?: number;
    adjustmentIncrease?: number;
    transferredVatCredit?: number;
    investmentProjectOffsetVat?: number;
    refundRequestedVat?: number;
  }
) =>
  useQuery({
    queryKey: ["reports", "vat", year, period, periodType, params],
    queryFn: () => reportsApi.vatSummary(year, period, periodType, params),
    enabled: !!year && !!period,
  });

export const useExportVATDeclaration = () =>
  useMutation({
    mutationFn: ({
      year, period, periodType, format, params,
    }: {
      year: number;
      period: number;
      periodType: string;
      format: "xlsx" | "pdf";
      params?: {
        previousVatCredit?: number;
        importPurchaseValue?: number;
        importPurchaseVat?: number;
        deductibleInputVatOverride?: number | null;
        adjustmentDecrease?: number;
        adjustmentIncrease?: number;
        transferredVatCredit?: number;
        investmentProjectOffsetVat?: number;
        refundRequestedVat?: number;
      };
    }) =>
      reportsApi.exportVatDeclaration(year, period, periodType, format, params),
    onSuccess: (blob, { format }) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vat-declaration.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    },
  });

export const useCITProvisional = (
  year: number,
  quarter: number,
  params?: {
    nonDeductibleExpenses?: number;
    lossCarriedForward?: number;
    citPaidYtd?: number;
    annualCitEstimate?: number | null;
    citRate?: number;
  }
) =>
  useQuery({
    queryKey: ["reports", "cit", year, quarter, params],
    queryFn: () => reportsApi.citProvisional(year, quarter, params),
    enabled: !!year && !!quarter,
  });

// ============================================================
// Company Settings
// ============================================================

export const useCompanySettings = () =>
  useQuery<CompanySettings>({
    queryKey: ["company"],
    queryFn: () => companiesApi.getMe() as Promise<CompanySettings>,
  });

export const useUpdateCompanySettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => companiesApi.updateMe(payload),
    onSuccess: (data) => {
      qc.setQueryData(["company"], data);
      qc.invalidateQueries({ queryKey: ["company"] });
    },
  });
};

// ============================================================
// Document retry
// ============================================================

export const useRetryDocument = () => {
  const qc = useQueryClient();
  return useMutation<RetryDocumentResponse, Error, string>({
    mutationFn: (id) => documentsApi.retry(id) as Promise<RetryDocumentResponse>,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
};

// ============================================================
// Filtered Invoice list
// ============================================================

export const useFilteredInvoices = (params?: InvoiceListParams) =>
  useQuery({
    queryKey: ["invoices", "filtered", params],
    queryFn: () => invoicesApi.list(params),
  });

// ============================================================
// Sales / Purchase Invoice Reports
// ============================================================

export const useSalesInvoicesReport = (year: number, period: number, periodType: string) =>
  useQuery({
    queryKey: ["reports", "sales-invoices", year, period, periodType],
    queryFn: () => reportsApi.salesInvoices(year, period, periodType),
    enabled: !!year && !!period,
  });

export const usePurchaseInvoicesReport = (year: number, period: number, periodType: string) =>
  useQuery({
    queryKey: ["reports", "purchase-invoices", year, period, periodType],
    queryFn: () => reportsApi.purchaseInvoices(year, period, periodType),
    enabled: !!year && !!period,
  });

// ============================================================
// Exceptions Report (derived from invoice-list data)
// ============================================================

export const useExceptionsReport = (year: number, period: number, periodType: string) =>
  useQuery({
    queryKey: ["reports", "exceptions", year, period, periodType],
    queryFn: async () => {
      const data = await invoicesApi.list({
        page: 1,
        page_size: 1000,
      });
      const allItems = (data.items ?? []) as Invoice[];
      const issues: {
        type: string;
        message: string;
        invoice_ids: string[];
        count: number;
      }[] = [];

      // Missing seller MST
      const missingSellerMst = allItems.filter(
        (inv) => !inv.seller_tax_code || inv.seller_tax_code.length < 10
      );
      if (missingSellerMst.length > 0) {
        issues.push({
          type: "missing_seller_mst",
          message: "Invoice is missing a valid seller MST (tax code)",
          invoice_ids: missingSellerMst.map((i) => i.id),
          count: missingSellerMst.length,
        });
      }

      // Duplicate invoices (by series + number)
      const seen = new Map<string, Invoice[]>();
      for (const inv of allItems) {
        if (inv.invoice_series && inv.invoice_number) {
          const key = `${inv.invoice_series}|${inv.invoice_number}`;
          if (!seen.has(key)) seen.set(key, []);
          seen.get(key)!.push(inv);
        }
      }
      const duplicates = Array.from(seen.values()).filter((g) => g.length > 1);
      if (duplicates.length > 0) {
        issues.push({
          type: "duplicate_invoice",
          message: "Duplicate invoice series and number detected",
          invoice_ids: duplicates.flatMap((g) => g.map((i) => i.id)),
          count: duplicates.length,
        });
      }

      // Low confidence extractions (confidence is stored on extracted_data in document, not invoice)
      // For invoice-level, we flag if vat_rate is "na" or amounts are 0
      const lowConfidence = allItems.filter(
        (inv) => inv.vat_rate === "na" || (inv.total_amount ?? 0) === 0
      );
      if (lowConfidence.length > 0) {
        issues.push({
          type: "low_confidence",
          message: "Invoice has suspicious extraction values (0 amount or N/A VAT)",
          invoice_ids: lowConfidence.map((i) => i.id),
          count: lowConfidence.length,
        });
      }

      // VAT mismatch — buyer MST present but not used
      const vatMismatch = allItems.filter(
        (inv) =>
          inv.buyer_tax_code &&
          inv.buyer_tax_code.length >= 10 &&
          inv.vat_rate !== "0" &&
          inv.vat_rate !== "na"
      );
      if (vatMismatch.length > 0) {
        issues.push({
          type: "vat_mismatch",
          message: "Buyer has a valid MST but VAT rate may be incorrect",
          invoice_ids: vatMismatch.map((i) => i.id),
          count: vatMismatch.length,
        });
      }

      return {
        year,
        period,
        period_type: periodType,
        issues,
        total_issues: issues.reduce((sum, i) => sum + i.count, 0),
      };
    },
    enabled: !!year && !!period,
  });
