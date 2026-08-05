import { NextResponse } from "next/server";
import { db } from "../../../../lib/database";
import { requireAdmin } from "../../../../lib/security";

export async function GET() {
  const admin = await requireAdmin();
  if (admin instanceof NextResponse) return admin;

  const orders = await db.order.findMany({
    include: { items: true, paymentEvents: true },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({ orders });
}
