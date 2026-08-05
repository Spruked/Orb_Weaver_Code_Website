import { NextResponse } from "next/server";
import { clearSessionCookie } from "../../../../lib/security";

export async function POST() {
  clearSessionCookie();
  return NextResponse.json({ status: "ok" });
}
