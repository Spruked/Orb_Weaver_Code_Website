import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "./lib/session-token";

export async function middleware(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;

  if (!token) {
    return rejectRequest(request);
  }

  const claims = await verifySessionToken(token);
  if (!claims) {
    return rejectRequest(request);
  }

  return NextResponse.next();
}

function rejectRequest(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/api/")) {
    const response = NextResponse.json({ error: "Authentication required." }, { status: 401 });
    response.cookies.delete(SESSION_COOKIE);
    return response;
  }

  const url = request.nextUrl.clone();
  url.pathname = "/checkout";
  url.search = "";

  const response = NextResponse.redirect(url);
  response.cookies.delete(SESSION_COOKIE);
  return response;
}

export const config = {
  matcher: ["/account/:path*", "/session-monitor/:path*", "/api/admin/:path*"],
};
