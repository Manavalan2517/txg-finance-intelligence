"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Live = { state: "connecting" | "live" | "offline"; last: string | null };
const REFRESH_DELAY_MS = 400; // changes that arrive together refresh the page once

/** Listens to the engine's change stream; when a record changes, the page re-renders from the results API without a
 * reload (§16.8). Shows when it is live and what changed last. */
export function LiveUpdates() {
  const router = useRouter();
  const [live, setLive] = useState<Live>({ state: "connecting", last: null });
  useEffect(() => {
    const source = new EventSource("/api/live");
    let timer: ReturnType<typeof setTimeout> | undefined;
    source.onopen = () => setLive((l) => ({ ...l, state: "live" }));
    source.onerror = () => setLive((l) => ({ ...l, state: "offline" })); // EventSource reconnects by itself
    source.addEventListener("change", (e) => {
      let what = "A record changed";
      try {
        const d = JSON.parse((e as MessageEvent<string>).data) as { seq: number; company: string };
        what = `${d.company} change ${d.seq}`;
      } catch { /* a malformed notice still refreshes the page */ }
      clearTimeout(timer);
      timer = setTimeout(() => {
        router.refresh();
        const at = new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Riyadh" });
        setLive({ state: "live", last: `${what}, updated ${at}` });
      }, REFRESH_DELAY_MS);
    });
    return () => { clearTimeout(timer); source.close(); };
  }, [router]);
  const label = live.state === "live" ? "Live" : live.state === "offline" ? "Reconnecting" : "Connecting";
  return (
    <p className="live" role="status" aria-live="polite" data-live={live.state}>
      <span className="live-dot" aria-hidden="true" />{label}
      {live.last && <span className="note"> · {live.last}</span>}
    </p>
  );
}
