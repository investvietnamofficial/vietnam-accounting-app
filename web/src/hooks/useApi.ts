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

export const useUnconfirmedDirectionInvoices = (page = 1, pageSize = 50) =>
  useQuery({
    queryKey: ["invoices", "unconfirmed-direction", page],
    queryFn: () => invoicesApi.unconfirmedDirection({ page, page_size: pageSize }),
  });

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
      const result = await reportsApi.exceptions(year, period, periodType);
      // Backend returns { issues: [{ type, message, invoices: [...], count }] }
      // Map to component's expected shape: invoice_ids + total_issues
      return {
        issues: (result.issues ?? []).map((issue: { type: string; message: string; invoices: string[]; count: number }) => ({
          type: issue.type,
          message: issue.message,
          invoice_ids: issue.invoices ?? [],
          count: issue.count,
        })),
        total_issues: (result.issues ?? []).reduce((sum: number, i: { count: number }) => sum + i.count, 0),
      };
    },
    enabled: !!year && !!period,
  });
