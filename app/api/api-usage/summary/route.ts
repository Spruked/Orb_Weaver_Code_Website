import { NextResponse } from "next/server";

const MONITOR_API = process.env.SESSION_MONITOR_API_URL ?? "http://127.0.0.1:18441";

export async function GET(request: Request) {
  const url = new URL(`${MONITOR_API}/api-usage/summary`);
  const incoming = new URL(request.url);
  for (const key of ["environment_id", "window_id"]) {
    const value = incoming.searchParams.get(key);
    if (value) url.searchParams.set(key, value);
  }

  try {
    const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ ok: false, error: "Session Monitor unavailable." }, { status: 503 });
  }
}
