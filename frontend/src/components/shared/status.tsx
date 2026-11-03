import type { Attempt, RunSummary, Stage } from "@/lib/api/contracts";
import { sourceLabels } from "@/lib/formatters";
import { cn } from "@/lib/utils";

const statuses: Record<Stage["status"], [string, string]> = {
  pending: ["In wachtrij", "neutral"],
  running: ["Bezig", "blue"],
  passed: ["Geslaagd", "green"],
  failed: ["Mislukt", "red"],
  warning: ["Aandachtspunt", "amber"],
  inconclusive: ["Onbeslist", "amber"],
  skipped: ["Niet uitgevoerd", "neutral"],
  error: ["Technische fout", "red"],
};
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={cn("badge", `badge-${tone}`)}>{children}</span>;
}
export function StatusBadge({
  status,
  label,
}: {
  status: Stage["status"];
  label?: string;
}) {
  const [text, tone] = statuses[status];
  return <Badge tone={tone}>{label ?? text}</Badge>;
}
export function SourceBadge({ source }: { source: string }) {
  return (
    <Badge
      tone={
        source === "synthetic"
          ? "amber"
          : source === "live"
            ? "blue"
            : "neutral"
      }
    >
      {sourceLabels[source] ?? source}
    </Badge>
  );
}
export function LifecycleBadge({
  status,
}: {
  status: RunSummary["lifecycle"];
}) {
  return (
    <Badge
      tone={
        status === "FAILED" ? "red" : status === "RUNNING" ? "blue" : "neutral"
      }
    >
      {
        {
          PENDING: "In wachtrij",
          RUNNING: "Bezig",
          COMPLETED: "Afgerond",
          FAILED: "Afgebroken",
        }[status]
      }
    </Badge>
  );
}
export function OutcomeBadge({ outcome }: { outcome: Attempt["outcome"] }) {
  const labels: Record<Attempt["outcome"], string> = {
    accepted: "Geaccepteerd binnen test",
    not_faster: "Gelijk, niet sneller",
    mismatch: "Resultaatverschil",
    safety_rejected: "Statisch afgewezen",
    inconclusive: "Onbeslist",
    error: "Uitvoeringsfout",
    unavailable: "Niet beschikbaar",
  };
  return (
    <Badge
      tone={
        outcome === "accepted"
          ? "green"
          : ["mismatch", "safety_rejected", "error"].includes(outcome)
            ? "red"
            : "amber"
      }
    >
      {labels[outcome]}
    </Badge>
  );
}
