import { Badge } from "@astryxdesign/core/Badge";
import type { Kpi, Status } from "@/lib/api";

// Colour always comes with an icon and a word (§10.5). Only watch and act get a badge: they need attention.
export function StatusMark({ status }: { status: Status | string }) {
  if (status === "act") return <Badge variant="error" label="◆ Act" />;
  if (status === "watch") return <Badge variant="warning" label="▲ Watch" />;
  if (status === "healthy") return <span className="ok">✓ Healthy</span>;
  if (status === "context") return <span className="note">i Context</span>;
  return <span className="note">Needs data</span>;
}

const TRENDS = { improving: "↗ Improving", steady: "→ Steady", slipping: "↘ Slipping" } as const;

export function TrendMark({ trend }: { trend: Kpi["trend"] }) {
  return trend ? <span className={trend === "slipping" ? "slip" : "note"}>{TRENDS[trend]}</span> : null;
}

export function StatusLine({ k }: { k?: Kpi }) {
  if (!k || k.state === "not_applicable" || k.state === "n.m.") return null;
  return <span className="status"><StatusMark status={k.status} /><TrendMark trend={k.trend} /></span>;
}
