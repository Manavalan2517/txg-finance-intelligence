import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { CompanyShell } from "@/components/CompanyShell";
import { ApiRefusal, mappings, periodFrom, standardChart, type Mappings } from "@/lib/api";
import { sar } from "@/lib/format";
import { submitOverride } from "./actions";

// The review page (§9.10): unreviewed and disputed mappings first, largest effect first. No approval step:
// numbers are already published; a reviewer's override makes a new version and recomputes.
export default async function ReviewPage({ params, searchParams }: {
  params: Promise<{ code: string }>; searchParams: Promise<{ period?: string; done?: string; error?: string }>;
}) {
  const { code } = await params;
  const sp = await searchParams;
  const period = periodFrom(sp.period);
  let body: Mappings | null = null;
  let refusal = "";
  try {
    body = await mappings(code);
  } catch (e) {
    if (!(e instanceof ApiRefusal)) throw e;
    refusal = e.status === 403 ? "This page is for reviewers and the Group CFO. Switch the role at the top right."
      : String(e.detail);
  }
  const chart = body ? await standardChart() : [];
  const names = new Map(chart.map((a) => [a.code, a.name]));
  return (
    <CompanyShell code={code} period={period} tab="Review">
      {sp.done && <Banner status="success" title={`Saved as mapping version ${Number(sp.done)}`}
                          description="The statements and every measure for this company were recomputed on it." />}
      {sp.error && <Banner status="error" title="The change was not saved" description={sp.error} />}
      {!body ? <Banner status="info" title="Restricted page" description={refusal} /> : (
        <>
          <p className="note">Mapping version {body.version} · {body.unreviewed} unreviewed · {body.reason}</p>
          <ol className="reviews">
            {body.entries.map((e) => (
              <li key={e.account_id} className={e.unreviewed ? "review open" : "review"}>
                <div className="review-head">
                  <strong>{e.account_name}</strong>
                  {e.unreviewed ? <Badge variant="warning" label="▲ Unreviewed" /> : e.reviewed_by
                    ? <span className="ok">✓ Reviewed by {e.reviewed_by}</span> : <span className="note">Agreed by both readings</span>}
                  {e.stand_in && <Badge variant="info" label="Stand-in reading" />}
                </div>
                <p className="note">
                  Mapped to {e.std_code} {names.get(e.std_code)} · first reading {e.first_reading}
                  {e.second_reading ? ` · second reading ${e.second_reading}` : ""} · confidence {e.confidence}
                  {Number(e.effect_sar) ? ` · effect ${sar(Number(e.effect_sar))}` : ""}
                </p>
                {e.evidence.length > 0 && <p className="note">Evidence: {e.evidence.join("; ")}</p>}
                <form action={submitOverride} className="override">
                  <input type="hidden" name="company" value={code} />
                  <input type="hidden" name="account" value={e.account_id} />
                  <input type="hidden" name="period" value={period} />
                  <label>
                    <span className="note">Standard account</span>
                    <select name="std_code" defaultValue={e.std_code}>
                      {chart.map((a) => <option key={a.code} value={a.code}>{a.code} {a.name}</option>)}
                    </select>
                  </label>
                  <label>
                    <span className="note">Reason</span>
                    <input name="reason" required minLength={3} maxLength={500} placeholder="Why this account" />
                  </label>
                  <Button type="submit" label="Save mapping" />
                </form>
              </li>
            ))}
          </ol>
        </>
      )}
    </CompanyShell>
  );
}
