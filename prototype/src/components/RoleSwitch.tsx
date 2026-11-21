"use client";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

const LABELS = { ceo: "Group CEO", cfo: "Group CFO", subsidiary_cfo: "Company CFO", reviewer: "Reviewer" } as const;

/** Prototype stand-in for sign-in (§6.6): the role travels as a header to the results API, which enforces it. */
export function RoleSwitch({ role }: { role: keyof typeof LABELS }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <label className="role">
      <span className="note">Viewing as</span>
      <select value={role} disabled={pending} onChange={(e) => {
        document.cookie = `txg-role=${e.target.value}; path=/; SameSite=Lax`;
        start(() => router.refresh());
      }}>
        {Object.entries(LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
  );
}
