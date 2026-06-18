"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  RefreshCw,
  Upload,
  XCircle,
} from "lucide-react";
import { ProtectedPage } from "@/components/protected-page";
import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/components/auth-provider";
import {
  useDocument,
  useDocuments,
  useRetryDocument,
  useUploadDocument,
} from "@/hooks/useApi";
import type { Document } from "@/types";

const vnd = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});

const STATUS_CONFIG: Record<
  string,
  { label: string; color: string; icon: React.ReactNode }
> = {
  uploaded: {
    label: "Uploaded",
    color: "bg-slate-100 text-slate-600",
    icon: <Upload size={13} />,
  },
  pending: {
    label: "Pending",
    color: "bg-slate-100 text-slate-600",
    icon: <Clock size={13} />,
  },
  processing: {
    label: "Processing",
    color: "bg-yellow-100 text-yellow-700",
    icon: <Clock size={13} />,
  },
  extracted: {
    label: "Extracted",
    color: "bg-blue-100 text-blue-700",
    icon: <FileText size={13} />,
  },
  verified: {
    label: "Verified",
    color: "bg-emerald-100 text-emerald-700",
    icon: <CheckCircle2 size={13} />,
  },
  failed: {
    label: "Failed",
    color: "bg-red-100 text-red-700",
    icon: <XCircle size={13} />,
  },
};

export default function DocumentsPage() {
  const { user, logout } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  const { data, isLoading, refetch } = useDocuments({ page: 1 });
  const upload = useUploadDocument();
  const retryDoc = useRetryDocument();

  const documents: Document[] = data?.items ?? [];

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) doUpload(file);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const doUpload = (file: File) => {
    setUploadProgress(0);
    const timer = setInterval(() => {
      setUploadProgress((p) => (p === null ? 0 : Math.min(p + 15, 90)));
    }, 200);
    upload.mutate(
      { file, docType: "invoice_vat" },
      {
        onSettled: () => {
          clearInterval(timer);
          setUploadProgress(null);
        },
      }
    );
  };

  const handleUploadClick = () => fileInputRef.current?.click();

  return (
    <ProtectedPage>
      <div className="flex min-h-screen bg-slate-50 text-slate-950">
        <Sidebar />
        <main className="flex-1">
          <header className="border-b bg-white">
            <div className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="text-sm text-slate-500">{user?.email}</p>
                <h1 className="text-2xl font-semibold">Documents</h1>
              </div>
              <button className="rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100" onClick={logout}>Sign out</button>
            </div>
          </header>
          <section className="px-6 py-6 space-y-6">
          {/* Upload Zone */}
          <div
            className={`relative rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
              dragging
                ? "border-emerald-500 bg-emerald-50"
                : "border-slate-300 bg-white hover:border-slate-400"
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input
              ref={fileInputRef}
              className="hidden"
              type="file"
              accept="image/*,application/pdf"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) doUpload(file);
                e.currentTarget.value = "";
              }}
            />
            <Upload
              size={36}
              className="mx-auto mb-3 text-slate-400"
            />
            <p className="mb-1 font-medium">
              Drag and drop an invoice image or PDF
            </p>
            <p className="mb-4 text-sm text-slate-500">
              JPEG, PNG, WEBP, HEIC, PDF — up to 20 MB
            </p>
            <button
              onClick={handleUploadClick}
              disabled={upload.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {upload.isPending ? (
                <RefreshCw size={15} className="animate-spin" />
              ) : (
                <Upload size={15} />
              )}
              {upload.isPending ? "Uploading..." : "Choose file"}
            </button>

            {uploadProgress !== null && (
              <div className="mt-4">
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full bg-emerald-600 transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Uploading... {uploadProgress}%
                </p>
              </div>
            )}

            {upload.isSuccess && (
              <p className="mt-3 text-sm text-emerald-600">
                Uploaded successfully!
              </p>
            )}
            {upload.isError && (
              <p className="mt-3 text-sm text-red-600">
                Upload failed. Please try again.
              </p>
            )}
          </div>

          {/* Polling Preview Card */}
          {selectedDocId && (
            <DocumentPreviewCard
              documentId={selectedDocId}
              onClose={() => setSelectedDocId(null)}
            />
          )}

          {/* Recent Documents */}
          <div className="rounded-lg border bg-white">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h2 className="font-semibold">Recent documents</h2>
              <button
                onClick={() => refetch()}
                disabled={isLoading}
                className="inline-flex items-center gap-1.5 rounded-md border bg-white px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
                Refresh
              </button>
            </div>

            {isLoading ? (
              <p className="px-4 py-8 text-center text-slate-500">
                Loading documents...
              </p>
            ) : documents.length === 0 ? (
              <p className="px-4 py-8 text-center text-slate-500">
                No documents yet. Upload an invoice to get started.
              </p>
            ) : (
              <div className="divide-y">
                {documents.map((doc) => {
                  const cfg =
                    STATUS_CONFIG[doc.status] ?? STATUS_CONFIG["pending"];
                  const isFailed = doc.status === "failed";
                  return (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between gap-4 px-4 py-3"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText
                          size={20}
                          className="shrink-0 text-slate-400"
                        />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">
                            {doc.file_name}
                          </p>
                          <p className="text-xs text-slate-500">
                            {new Date(doc.created_at).toLocaleString("vi-VN")}
                            {doc.doc_type !== "other" && (
                              <span className="ml-2 capitalize">
                                — {doc.doc_type.replace("_", " ")}
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {isFailed && doc.processing_error && (
                          <span className="hidden text-xs text-red-500 sm:block max-w-[200px] truncate">
                            {doc.processing_error}
                          </span>
                        )}
                        {doc.status === "extracted" && (
                          <button
                            onClick={() => setSelectedDocId(doc.id)}
                            className="text-xs text-blue-600 hover:underline"
                          >
                            View data
                          </button>
                        )}
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${cfg.color}`}
                        >
                          {cfg.icon}
                          {cfg.label}
                        </span>
                        {isFailed && (
                          <button
                            onClick={() => retryDoc.mutate(doc.id)}
                            disabled={retryDoc.isPending}
                            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-slate-100 disabled:opacity-50"
                          >
                            <RefreshCw
                              size={12}
                              className={
                                retryDoc.isPending ? "animate-spin" : ""
                              }
                            />
                            Retry
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>
        </main>
        </div>
    </ProtectedPage>
  );
}

function DocumentPreviewCard({
  documentId,
  onClose,
}: {
  documentId: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError } = useDocument(documentId);

  if (isLoading) {
    return (
      <div className="rounded-lg border bg-white p-4 text-center text-slate-500">
        Loading...
      </div>
    );
  }
  if (isError || !data) {
    return null;
  }

  const ed = data.extracted_data;
  const confidence = data.extraction_confidence ?? ed?.confidence ?? null;

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-blue-900">Extracted Invoice Data</h3>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-700"
        >
          <XCircle size={18} />
        </button>
      </div>

      {ed ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Invoice #" value={`${ed.invoice_series ?? ""} ${ed.invoice_number ?? "-"}`} />
          <Field label="Date" value={ed.invoice_date ? new Date(ed.invoice_date).toLocaleDateString("vi-VN") : "-"} />
          <Field label="Seller" value={ed.seller_name ?? "-"} />
          <Field label="Seller MST" value={ed.seller_tax_code ?? "-"} />
          <Field label="Subtotal" value={vnd.format(ed.subtotal_amount ?? 0)} />
          <Field label="VAT Rate" value={ed.vat_rate} />
          <Field label="VAT Amount" value={vnd.format(ed.vat_amount ?? 0)} />
          <Field label="Total" value={vnd.format(ed.total_amount ?? 0)} strong />
          {confidence !== null && (
            <Field
              label="Confidence"
              value={`${(confidence * 100).toFixed(0)}%`}
              valueColor={confidence > 0.8 ? "text-emerald-600" : confidence > 0.5 ? "text-yellow-600" : "text-red-600"}
            />
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm text-blue-700">
          <AlertCircle size={16} />
          No extracted data yet. Document may still be processing.
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  strong = false,
  valueColor = "text-slate-900",
}: {
  label: string;
  value: string;
  strong?: boolean;
  valueColor?: string;
}) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`${valueColor} ${strong ? "font-semibold" : ""}`}>{value}</p>
    </div>
  );
}
