import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { documentsApi, invoicesApi, reportsApi } from "@/lib/api";
import type { Document, Invoice, UploadResponse } from "@/types";

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
