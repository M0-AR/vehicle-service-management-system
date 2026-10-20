import { cn } from "@/lib/cn";
import { titleCase } from "@/lib/format";

type Tone =
  | "neutral"
  | "brand"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "scheduled"
  | "progress"
  | "parts"
  | "completed"
  | "invoiced"
  | "cancelled";

/* Soft tinted chip: 10% hue fill, 28% hue border, text blends the hue with
 * the theme foreground so it stays >=4.5:1 in both light and dark. */
function tinted(v: string) {
  return `border-[color-mix(in_oklab,${v}_28%,transparent)] bg-[color-mix(in_oklab,${v}_10%,transparent)] text-[color-mix(in_oklab,${v}_60%,var(--foreground))]`;
}

const TONES: Record<Tone, string> = {
  neutral: "border-[var(--border)] bg-[var(--muted)] text-[var(--muted-foreground)]",
  brand: tinted("var(--brand-primary)"),
  info: tinted("var(--status-scheduled)"),
  scheduled: tinted("var(--status-scheduled)"),
  progress: tinted("var(--status-in-progress)"),
  warning: tinted("var(--status-in-progress)"),
  parts: tinted("var(--status-awaiting-parts)"),
  success: tinted("var(--status-completed)"),
  completed: tinted("var(--status-completed)"),
  invoiced: tinted("var(--status-invoiced)"),
  cancelled: tinted("var(--status-cancelled)"),
  danger: tinted("var(--destructive)"),
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const ORDER_TONES: Record<string, Tone> = {
  scheduled: "scheduled",
  in_progress: "progress",
  awaiting_parts: "parts",
  completed: "completed",
  invoiced: "invoiced",
  cancelled: "cancelled",
};

const INVOICE_TONES: Record<string, Tone> = {
  draft: "neutral",
  sent: "scheduled",
  paid: "completed",
  overdue: "danger",
  void: "neutral",
};

const VEHICLE_TONES: Record<string, Tone> = {
  active: "completed",
  in_service: "progress",
  retired: "neutral",
};

const PRIORITY_TONES: Record<string, Tone> = {
  low: "neutral",
  normal: "neutral",
  high: "progress",
  urgent: "danger",
};

export function StatusBadge({
  status,
  kind,
}: {
  status: string;
  kind: "order" | "invoice" | "vehicle" | "priority";
}) {
  const map =
    kind === "order"
      ? ORDER_TONES
      : kind === "invoice"
        ? INVOICE_TONES
        : kind === "vehicle"
          ? VEHICLE_TONES
          : PRIORITY_TONES;
  const tone = map[status] ?? "neutral";
  return (
    <Badge tone={tone} className={status === "void" ? "line-through" : undefined}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      {titleCase(status)}
    </Badge>
  );
}
