import { cn } from "@/lib/cn";

export function Table({
  caption,
  className,
  children,
}: {
  caption: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--card)]", className)}>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return (
    <thead className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--muted)] text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
      {children}
    </thead>
  );
}

export function TH({
  className,
  scope = "col",
  numeric,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <th
      scope={scope}
      className={cn("px-4 py-3 font-medium", numeric && "text-right tabular-nums", className)}
      {...props}
    />
  );
}

export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-[var(--border)]">{children}</tbody>;
}

export function TR({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("hover:bg-[var(--muted)]/60", className)} {...props} />;
}

export function TD({
  className,
  numeric,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      className={cn("px-4 py-3 align-middle", numeric && "text-right tabular-nums", className)}
      {...props}
    />
  );
}
