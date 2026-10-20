import { Badge } from "@/components/ui/badge";

const ESTIMATE_TONES: Record<string, "neutral" | "scheduled" | "completed" | "danger"> = {
  draft: "neutral",
  sent: "scheduled",
  approved: "completed",
  declined: "danger",
};

export function EstimateStatusBadge({ status }: { status: string }) {
  const tone = ESTIMATE_TONES[status] ?? "neutral";
  return (
    <Badge tone={tone}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}
