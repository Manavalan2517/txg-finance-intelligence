import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { CompanyShell } from "@/components/CompanyShell";
import { BenfordChart } from "@/components/lazy-charts";
import { ApiRefusal, integrity, periodFrom, type Integrity } from "@/lib/api";
import { sar } from "@/lib/format";

// The integrity page (§13): CFO only, every view is logged, findings are "worth a look", never accusations.
type Test = Integrity["tests"][number];

function summary(t: Test): { flagged: boolean; text: string } {
  switch (t.id) {
    case "IT-01":
      return { flagged: t.result === "nonconformity",
               text: `${t.records} bills; mean absolute deviation ${t.mad} (${t.result}).` };
    case "IT-02":
      return { flagged: Boolean(t.flagged),
               text: `${t.below} bills in the 5% just below ${sar(Number(t.limit))}, ${t.above} just above it.` };
    case "IT-03":
      return { flagged: Number(t.hits) > 0, text: `${t.hits} journals entered unusually late into months already closed.` };
    default:
      return { flagged: Number(t.hits) > 0, text: `${t.hits} entries by rarely-posting users on a Friday, Saturday or late at night.` };
  }
}

export default async function IntegrityPage({ params, searchParams }: {
  params: Promise<{ code: string }>; searchParams: Promise<{ period?: string }>;
}) {
  const { code } = await params;
  const period = periodFrom((await searchParams).period);
  let body: Integrity | null = null;
  let refusal = "";
  try {
    body = await integrity(code);
  } catch (e) {
    if (!(e instanceof ApiRefusal)) throw e;
    refusal = e.status === 403 ? "This page is for the Group CFO. Switch the role at the top right to view it."
      : String(e.detail);
  }
  return (
    <CompanyShell code={code} period={period} tab="Integrity">
      {!body ? <Banner status="info" title="Restricted page" description={refusal} /> : (
        <>
          <p className="note">Each item is worth a look, not proof of anything. This view has been recorded.</p>
          <ul className="checks">
            {body.tests.map((t) => {
              const s = summary(t);
              return (
                <li key={t.id}>
                  <span className="check-id">{t.id}</span>
                  <span className="check-name">{t.name}</span>
                  {s.flagged ? <Badge variant="warning" label="▲ Worth a look" /> : <span className="ok">✓ Nothing unusual</span>}
                  <span className="note">{s.text}</span>
                </li>
              );
            })}
          </ul>
          <h2 className="section">First two digits of bill amounts</h2>
          <BenfordChart rows={body.benford} />
          <div className="two">
            <table className="others compact">
              <caption className="note" style={{ textAlign: "start" }}>Late journals into closed months</caption>
              <thead><tr><th scope="col">Journal</th><th scope="col">Dated</th><th scope="col">Entered</th><th scope="col" className="num">Days late</th></tr></thead>
              <tbody>{body.back_dated.map((x) => (
                <tr key={x.record_id}><td>{x.record_id}</td><td>{x.dated}</td><td>{x.created.slice(0, 10)}</td><td className="num">{x.lag_days}</td></tr>
              ))}</tbody>
            </table>
            <table className="others compact">
              <caption className="note" style={{ textAlign: "start" }}>Unusual posting times by rarely-posting users</caption>
              <thead><tr><th scope="col">Journal</th><th scope="col">User</th><th scope="col">Entered</th><th scope="col">Why</th></tr></thead>
              <tbody>{body.unusual.map((x) => (
                <tr key={x.record_id}><td>{x.record_id}</td><td>{x.user_id}</td>
                  <td>{new Date(x.created).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Riyadh" })}</td>
                  <td>{x.reason}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </CompanyShell>
  );
}
