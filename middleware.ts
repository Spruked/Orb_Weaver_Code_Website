import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "./lib/session-token";

export async function middleware(request: NextRequest) {
  const cookieToken = request.cookies.get(SESSION_COOKIE)?.value;
  const authorization = request.headers.get("authorization");
  const bearerToken = authorization?.match(/^Bearer\s+(.+)$/i)?.[1];
  const token = cookieToken || bearerToken;

  if (!token) {
    return rejectRequest(request);
  }

  const claims = await verifySessionToken(token);
  if (!claims) {
    return rejectRequest(request);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-user-id", claims.sub);
  if (claims.role) requestHeaders.set("x-user-role", claims.role);

  return NextResponse.next({ request: { headers: requestHeaders } });
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
  matcher: [
    "/account/:path*",
    "/session-monitor/:path*",
    "/api/admin/:path*",
    "/api/telemetry/:path*",
    "/api/api-usage/:path*",
  ],
};
