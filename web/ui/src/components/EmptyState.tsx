import type { ReactNode } from "react";

// A consistent, friendly empty state used across screens (no results, nothing
// selected, all-unmatched VCF, …).
export function EmptyState({
  icon = "◦",
  title,
  children,
}: {
  icon?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="emptybox">
      <div className="empty-icon" aria-hidden>
        {icon}
      </div>
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}
