"use server";
import { redirect } from "next/navigation";
import { ApiRefusal, overrideMapping } from "@/lib/api";

const CODE = /^[A-Z]{2}-\d{2}$/;
const STD = /^\d{4}$/;

/** A reviewer's override (§9.10): the engine writes a new mapping version and recomputes the statements. */
export async function submitOverride(formData: FormData): Promise<void> {
  const company = String(formData.get("company") ?? "");
  const account = String(formData.get("account") ?? "");
  const std = String(formData.get("std_code") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  const raw = String(formData.get("period") ?? "");
  const period = /^\d{4}-(0[1-9]|1[0-2])$/.test(raw) ? raw : "2026-10";
  const back = `/company/${encodeURIComponent(company)}/review?period=${period}`;
  if (!CODE.test(company) || !/^\d{1,32}$/.test(account) || !STD.test(std) || reason.length < 3 || reason.length > 500) {
    redirect(`${back}&error=${encodeURIComponent("Choose a standard account and give a reason of 3 to 500 characters.")}`);
  }
  let message: string;
  try {
    const result = await overrideMapping(company, account, std, reason);
    message = `done=${result.version}`;
  } catch (e) {
    if (!(e instanceof ApiRefusal)) throw e;
    message = `error=${encodeURIComponent(e.status === 403 ? "Only a reviewer or the Group CFO can change a mapping."
      : typeof e.detail === "string" ? e.detail : "The results service could not accept this change.")}`;
  }
  redirect(`${back}&${message}`);
}
