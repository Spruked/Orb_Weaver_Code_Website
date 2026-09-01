import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const session = request.cookies.get("owcc_session")?.value;
  const { pathname } = request.nextUrl;
  const hostname = request.headers.get("host")?.split(":")[0] ?? request.nextUrl.hostname;
  const isLocalHost =
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "::1" ||
    hostname === "[::1]";

  if (pathname.startsWith("/account") && !session) {
    const url = request.nextUrl.clone();
    url.pathname = "/checkout";
    return NextResponse.redirect(url);
  }

  if (pathname.startsWith("/session-monitor") && !session && !isLocalHost) {
    const url = request.nextUrl.clone();
    url.pathname = "/checkout";
    return NextResponse.redirect(url);
  }

  if (pathname.startsWith("/api/admin") && !session) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/account/:path*", "/session-monitor/:path*", "/api/admin/:path*"],
};
