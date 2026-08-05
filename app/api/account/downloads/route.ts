import { NextResponse } from "next/server";
import { db } from "../../../../lib/database";
import { requireUser } from "../../../../lib/security";

export async function GET() {
  const user = await requireUser();
  if (user instanceof NextResponse) return user;

  const grants = await db.downloadGrant.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({ downloads: grants });
}
