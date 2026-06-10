import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format integer VND amount for display */
export function formatVND(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(amount);
}

/** Format VAT rate for display */
export function formatVATRate(rate: string): string {
  const map: Record<string, string> = {
    "0": "0%", "5": "5%", "8": "8%", "10": "10%",
    exempt: "Miễn thuế", na: "Không chịu thuế",
  };
  return map[rate] ?? rate;
}

/** Get status badge color */
export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    processing: "bg-blue-100 text-blue-800",
    extracted: "bg-purple-100 text-purple-800",
    verified: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-800",
  };
  return map[status] ?? "bg-gray-100 text-gray-800";
}
