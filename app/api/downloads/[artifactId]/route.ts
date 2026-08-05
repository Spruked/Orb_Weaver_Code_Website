import { NextResponse } from "next/server";
import { db } from "../../../../lib/database";
import { createDownloadGrant } from "../../../../lib/downloads";
import { requireUser } from "../../../../lib/security";

type Ctx = { params: { artifactId: string } };

export async function GET(_req: Request, ctx: Ctx) {
  const user = await requireUser();
  if (user instanceof NextResponse) return user;

  const entitlement = await db.entitlement.findFirst({
    where: {
      userId: user.id,
      active: true,
    },
    include: { order: true },
  });

  if (!entitlement) {
    return NextResponse.json({ error: "No active entitlement." }, { status: 403 });
  }

  const grant = await createDownloadGrant(user.id, entitlement.orderId, ctx.params.artifactId);
  return NextResponse.json({
    downloadToken: grant.token,
    expiresAt: grant.expiresAt.toISOString(),
    message: "Use this grant token with your artifact gateway.",
  });
}
