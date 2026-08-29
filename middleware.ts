import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const session = request.cookies.get("owcc_session")?.value;
  const { pathname } = request.nextUrl;

  if ((pathname.startsWith("/account") || pathname.startsWith("/session-monitor")) && !session) {
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
