import { NextResponse } from "next/server";
import { db } from "../../../../lib/database";
import { requireUser } from "../../../../lib/security";

export async function GET() {
  const user = await requireUser();
  if (user instanceof NextResponse) return user;

  const licenses = await db.licenseRequest.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({ licenses });
}
