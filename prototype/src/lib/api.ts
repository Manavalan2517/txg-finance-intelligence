// Every number on screen comes from the engine's results API (FR-12). Server-side only.
import "server-only";
import { cookies } from "next/headers";

const API = process.env.TXG_API_URL ?? "http://127.0.0.1:8710";
export const ROLES = ["ceo", "cfo", "subsidiary_cfo", "reviewer"] as const;
export type Role = (typeof ROLES)[number];
export const DEFAULT_PERIOD = "2026-10";
export const PERIOD = /^\d{4}-(0[1-9]|1[0-2])$/;

export type Company = { code: string; name: string; currency: string };
export type Status = "healthy" | "watch" | "act" | "context" | "needs_data";
export type Kpi = {
  company: string;
  period: string;
  kpi_id: string;
  name: string;
  value: string | null;
  unit: string;
  state: "ok" | "n.m." | "not_applicable" | "needs_data";
  provisional: boolean;
  depends_on_held_months: string[];
  status: Status;
  trend: "improving" | "steady" | "slipping" | null;
};
export type Held = { held: true; reason: string; last_good_month: string | null };
export type GroupRow = { code: string; name: string; held: boolean; reason: string | null; kpis: Kpi[] };
export type Series = {
  kpi_id: string; name: string; unit: string; direction: string; months: string[]; values: (number | null)[];
  centre: number | null; lower: number | null; upper: number | null;
};
export type Cash13 = {
  opening: number; minimum: number; weeks: { start: string; p10: number; p50: number; p90: number }[];
  low_point_p50: number; low_point_p10: number; chance_below_minimum: number;
};
export type Receivables = {
  ageing: { bucket: string; sar: string }[]; retention_held: string;
  customers: { customer_id: string; name: string; sales_sar: string; share: number }[]; customers_total_sar: string;
};
export type Integrity = {
  company: string; framing: string;
  tests: { id: string; name: string; [k: string]: unknown }[];
  benford: { digits: number; actual: number; expected: number }[];
  back_dated: { record_id: string; dated: string; created: string; lag_days: number }[];
  unusual: { record_id: string; user_id: string; created: string; reason: string }[];
};
export type MappingEntry = {
  account_id: string; account_name: string; zoho_type: string; std_code: string; confidence: string;
  evidence: string[]; first_reading: string; second_reading: string | null; agreed: boolean; unreviewed: boolean;
  effect_sar: string; stand_in: boolean; reviewed_by: string | null; review_reason: string | null; findings: string[];
};
export type Mappings = { company: string; version: number; reason: string; unreviewed: number; entries: MappingEntry[] };
export type Acquisition = {
  target: { id: string; name: string; cr_number: string; checks_passed: boolean; ebitda: Record<string, number> };
  ask_ev: number; board_confidence: number;
  decision: { verdict: string; walk_away_ev: number; chance_at_ask: number; value_p10: number; value_p50: number;
              value_p90: number; synergy_gap: number; notes: string[] };
  bridge: { debt_like: number; cash: number; items: Record<string, number> };
  peers: { name: string; ticker: string; ev_ebitda: number }[];
  candidates: { candidate_id: string; name: string; city: string; region: string; revenue_band_sar_m: string;
                cr_number: string; identity: string }[];
};

/** A refusal the page explains in words: held month (409), not allowed (403), nothing to show (404). */
export class ApiRefusal extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `The results service answered ${status}`);
  }
  get held(): Held | null {
    return this.status === 409 ? (this.detail as Held) : null;
  }
}

export async function currentRole(): Promise<Role> {
  const value = (await cookies()).get("txg-role")?.value;
  return (ROLES as readonly string[]).includes(value ?? "") ? (value as Role) : "ceo";
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const role = await currentRole();
  const res = await fetch(`${API}${path}`, {
    ...init, cache: "no-store", headers: { "X-TXG-Role": role, "Content-Type": "application/json", ...init?.headers },
  });
  if ([403, 404, 409, 422].includes(res.status)) throw new ApiRefusal(res.status, (await res.json()).detail);
  if (!res.ok) throw new Error(`The results service answered ${res.status} for ${path}`);
  return res.json() as Promise<T>;
}

/** The engine's change stream (§16.8), opened with the viewer's role; the route handler relays it to the browser. */
export async function openLiveStream(signal: AbortSignal): Promise<Response> {
  const role = await currentRole();
  return fetch(`${API}/events/stream`, {
    cache: "no-store", signal, headers: { "X-TXG-Role": role, Accept: "text/event-stream" },
  });
}

const q = (period: string) => `period=${encodeURIComponent(period)}`;
const c = encodeURIComponent;
export const companies = () => call<Company[]>("/companies");
export const kpis = (code: string, period: string) => call<Kpi[]>(`/companies/${c(code)}/kpis?${q(period)}`);
export const group = (period: string) => call<GroupRow[]>(`/group?${q(period)}`);
export const series = (code: string, kpi: string, period: string) =>
  call<Series>(`/companies/${c(code)}/series/${c(kpi)}?${q(period)}`);
export const cash13 = (code: string, period: string) => call<Cash13>(`/companies/${c(code)}/cash13?${q(period)}`);
export const receivables = (code: string, period: string) =>
  call<Receivables>(`/companies/${c(code)}/receivables?${q(period)}`);
export const integrity = (code: string) => call<Integrity>(`/companies/${c(code)}/integrity`);
export const mappings = (code: string) => call<Mappings>(`/companies/${c(code)}/mappings`);
export const acquisition = () => call<Acquisition>("/acquisition");
export const overrideMapping = (code: string, account: string, std_code: string, reason: string) =>
  call<{ version: number }>(`/companies/${c(code)}/mappings/${c(account)}`, {
    method: "POST", body: JSON.stringify({ std_code, reason }),
  });

export function periodFrom(raw: string | undefined): string {
  return raw && PERIOD.test(raw) ? raw : DEFAULT_PERIOD;
}
export type StdAccount = { code: string; name: string; class: string };
export const standardChart = () => call<StdAccount[]>("/standard-chart");
