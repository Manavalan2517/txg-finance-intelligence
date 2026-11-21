import { openLiveStream } from "@/lib/api";

// Relays the engine's change stream to the browser, so the browser only ever talks to the prototype (FR-12) and the
// role comes from the server-side cookie, never from the page.
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  let upstream: Response;
  try {
    upstream = await openLiveStream(request.signal);
  } catch {
    return new Response("Live updates are unavailable", { status: 502 });
  }
  if (!upstream.ok || !upstream.body) {
    return new Response("Live updates are unavailable", { status: upstream.status === 401 ? 401 : 502 });
  }
  return new Response(upstream.body, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no" },
  });
}
