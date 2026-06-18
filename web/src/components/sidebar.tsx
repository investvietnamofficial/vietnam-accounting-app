"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart2,
  ChevronDown,
  ChevronRight,
  FileText,
  LayoutDashboard,
  Receipt,
  Settings,
} from "lucide-react";
import { useState } from "react";
import { clsx } from "clsx";

const NAV_ITEMS = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: <LayoutDashboard size={18} />,
  },
  {
    href: "/documents",
    label: "Documents",
    icon: <FileText size={18} />,
  },
  {
    href: "/invoices",
    label: "Invoices",
    icon: <Receipt size={18} />,
  },
  {
    href: "/reports",
    label: "Reports",
    icon: <BarChart2 size={18} />,
    expandable: true,
    children: [
      { href: "/reports/vat-summary", label: "VAT Summary" },
      { href: "/reports/sales-invoices", label: "Sales Invoices" },
      { href: "/reports/purchase-invoices", label: "Purchase Invoices" },
      { href: "/reports/exceptions", label: "Exceptions" },
    ],
  },
  {
    href: "/settings",
    label: "Settings",
    icon: <Settings size={18} />,
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    "/reports": true,
  });

  const isActive = (href: string) =>
    href === "/"
      ? pathname === "/"
      : pathname.startsWith(href);

  return (
    <aside className="w-56 shrink-0 border-r bg-white">
      <div className="flex h-14 items-center border-b px-4">
        <span className="text-base font-semibold text-emerald-700">VN Accounting</span>
      </div>
      <nav className="p-2 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href);
          const isExpanded = expanded[item.href];

          return (
            <div key={item.href}>
              <Link
                href={item.expandable ? "#" : item.href}
                onClick={
                  item.expandable
                    ? (e) => {
                        e.preventDefault();
                        setExpanded((prev) => ({ ...prev, [item.href]: !prev[item.href] }));
                      }
                    : undefined
                }
                className={clsx(
                  "flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm",
                  active
                    ? "bg-emerald-50 text-emerald-800 font-medium"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                )}
              >
                <span className="flex items-center gap-2">
                  {item.icon}
                  {item.label}
                </span>
                {item.expandable && (
                  <span className="text-slate-400">
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </span>
                )}
              </Link>

              {item.expandable && isExpanded && item.children && (
                <div className="ml-6 mt-0.5 space-y-0.5">
                  {item.children.map((child) => (
                    <Link
                      key={child.href}
                      href={child.href}
                      className={clsx(
                        "block rounded-md px-3 py-1.5 text-sm",
                        pathname === child.href
                          ? "text-emerald-700 font-medium"
                          : "text-slate-500 hover:text-slate-700"
                      )}
                    >
                      {child.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
