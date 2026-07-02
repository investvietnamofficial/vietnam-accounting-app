import axios, { AxiosError } from "axios";
import type { AuthSession, ForgotPasswordResponse, LoginPayload, RegisterPayload } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

export function getStoredAccessToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredRefreshToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setStoredTokens(session: AuthSession) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_TOKEN_KEY, session.access_token);
  if (session.refresh_token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, session.refresh_token);
  }
}

export function clearStoredTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// Attach JWT token to every request
apiClient.interceptors.request.use(async (config) => {
  const token = getStoredAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-refresh on 401
apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as any;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = getStoredRefreshToken();
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE}/api/v1/auth/token/refresh`, { refresh_token: refresh });
          setStoredTokens(data);
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return apiClient(original);
        } catch {
          clearStoredTokens();
          window.location.href = "/auth/login";
        }
      }
    }
    return Promise.reject(error);
  }
);

// ---------------------------------------------------------------------------
// Auth functions
// ---------------------------------------------------------------------------

export const authApi = {
  login: async ({ email, password }: LoginPayload): Promise<AuthSession> => {
    const form = new URLSearchParams();
    form.set("username", email.trim().toLowerCase());
    form.set("password", password);
    const { data } = await axios.post(`${API_BASE}/api/v1/auth/token`, form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return data;
  },
  register: async (payload: RegisterPayload): Promise<AuthSession> => {
    const { data } = await axios.post(`${API_BASE}/api/v1/auth/register`, {
      email: payload.email.trim().toLowerCase(),
      password: payload.password,
      full_name: payload.fullName,
      company_name: payload.companyName,
      company_tax_code: payload.companyTaxCode,
    });
    return data;
  },
  refresh: async (refreshToken: string): Promise<AuthSession> => {
    const { data } = await axios.post(`${API_BASE}/api/v1/auth/token/refresh`, { refresh_token: refreshToken });
    return data;
  },
  me: async () => {
    const { data } = await apiClient.get("/auth/me");
    return { user: data };
  },
  forgotPassword: async (email: string): Promise<ForgotPasswordResponse> => {
    const { data } = await axios.post(`${API_BASE}/api/v1/auth/password/forgot`, { email: email.trim().toLowerCase() });
    return data;
  },
  resetPassword: async ({ resetToken, newPassword }: { resetToken: string; newPassword: string }): Promise<AuthSession> => {
    const { data } = await axios.post(`${API_BASE}/api/v1/auth/password/reset`, {
      reset_token: resetToken,
      new_password: newPassword,
    });
    return data;
  },
};

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const documentsApi = {
  upload: async (file: File, docType: string = "other") => {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);
    const { data } = await apiClient.post("/documents/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
  get: async (id: string) => {
    const { data } = await apiClient.get(`/documents/${id}`);
    return data;
  },
  list: async (params?: { status?: string; page?: number; page_size?: number }) => {
    const { data } = await apiClient.get("/documents/", { params });
    return data;
  },
  retry: async (id: string) => {
    const { data } = await apiClient.post(`/documents/${id}/retry`);
    return data;
  },
};

export const companiesApi = {
  getMe: async () => {
    const { data } = await apiClient.get("/companies/me");
    return data;
  },
  updateMe: async (payload: Record<string, unknown>) => {
    const { data } = await apiClient.patch("/companies/me", payload);
    return data;
  },
};

export const invoicesApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    date_from?: string;
    date_to?: string;
    vat_rate?: string;
    seller?: string;
    status?: string;
  }) => {
    const { data } = await apiClient.get("/invoices/", { params });
    return data;
  },
  get: async (id: string) => {
    const { data } = await apiClient.get(`/invoices/${id}`);
    return data;
  },
  verifyEInvoice: async (id: string) => {
    const { data } = await apiClient.post(`/invoices/${id}/verify-einvoice`);
    return data;
  },
  unconfirmedDirection: async (params?: { page?: number; page_size?: number }) => {
    const { data } = await apiClient.get("/invoices/unconfirmed-direction", { params });
    return data;
  },
};

export const reportsApi = {
  vatSummary: async (
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
  ) => {
    const { data } = await apiClient.get("/reports/vat-summary", {
      params: {
        year,
        period,
        period_type: periodType,
        previous_vat_credit: params?.previousVatCredit ?? 0,
        import_purchase_value: params?.importPurchaseValue ?? 0,
        import_purchase_vat: params?.importPurchaseVat ?? 0,
        deductible_input_vat_override: params?.deductibleInputVatOverride ?? undefined,
        adjustment_decrease: params?.adjustmentDecrease ?? 0,
        adjustment_increase: params?.adjustmentIncrease ?? 0,
        transferred_vat_credit: params?.transferredVatCredit ?? 0,
        investment_project_offset_vat: params?.investmentProjectOffsetVat ?? 0,
        refund_requested_vat: params?.refundRequestedVat ?? 0,
      },
    });
    return data;
  },
  citProvisional: async (
    year: number,
    quarter: number,
    params?: {
      nonDeductibleExpenses?: number;
      lossCarriedForward?: number;
      citPaidYtd?: number;
      annualCitEstimate?: number | null;
      citRate?: number;
    }
  ) => {
    const { data } = await apiClient.get("/reports/cit-provisional", {
      params: {
        year,
        quarter,
        non_deductible_expenses: params?.nonDeductibleExpenses ?? 0,
        loss_carried_forward: params?.lossCarriedForward ?? 0,
        cit_paid_ytd: params?.citPaidYtd ?? 0,
        annual_cit_estimate: params?.annualCitEstimate ?? undefined,
        cit_rate: params?.citRate ?? 0.2,
      },
    });
    return data;
  },
  exportVatDeclaration: async (
    year: number,
    period: number,
    periodType: string,
    format: "xlsx" | "pdf",
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
  ) => {
    const response = await apiClient.get("/reports/export/vat-declaration", {
      params: {
        year,
        period,
        period_type: periodType,
        format,
        previous_vat_credit: params?.previousVatCredit ?? 0,
        import_purchase_value: params?.importPurchaseValue ?? 0,
        import_purchase_vat: params?.importPurchaseVat ?? 0,
        deductible_input_vat_override: params?.deductibleInputVatOverride ?? undefined,
        adjustment_decrease: params?.adjustmentDecrease ?? 0,
        adjustment_increase: params?.adjustmentIncrease ?? 0,
        transferred_vat_credit: params?.transferredVatCredit ?? 0,
        investment_project_offset_vat: params?.investmentProjectOffsetVat ?? 0,
        refund_requested_vat: params?.refundRequestedVat ?? 0,
      },
      responseType: "blob",
    });
    return response.data;
  },
  salesInvoices: async (year: number, period: number, periodType: string) => {
    const { data } = await apiClient.get("/reports/invoice-list", {
      params: { year, period, period_type: periodType, invoice_direction: "sale" },
    });
    return data;
  },
  purchaseInvoices: async (year: number, period: number, periodType: string) => {
    const { data } = await apiClient.get("/reports/invoice-list", {
      params: { year, period, period_type: periodType, invoice_direction: "purchase" },
    });
    return data;
  },
  exceptions: async (year: number, period: number, periodType: string) => {
    const { data } = await apiClient.get("/reports/exceptions", {
      params: { year, period, period_type: periodType },
    });
    return data;
  },
};
