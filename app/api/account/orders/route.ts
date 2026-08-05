import { NextResponse } from "next/server";
import { db } from "../../../../lib/database";
import { requireUser } from "../../../../lib/security";

export async function GET() {
  const user = await requireUser();
  if (user instanceof NextResponse) return user;

  const orders = await db.order.findMany({
    where: { userId: user.id },
    include: { items: true },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({ orders });
}
