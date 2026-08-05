import { NextResponse } from "next/server";
import { db } from "../../../../lib/database";
import { requireAdmin } from "../../../../lib/security";

export async function GET() {
  const admin = await requireAdmin();
  if (admin instanceof NextResponse) return admin;

  const [totalUsers, totalOrders, paidOrders, revenue] = await Promise.all([
    db.user.count(),
    db.order.count(),
    db.order.count({ where: { status: "PAID" } }),
    db.order.aggregate({
      _sum: { totalCents: true },
      where: { status: { in: ["PAID", "FULFILLED", "FULFILLMENT_PENDING"] } },
    }),
  ]);

  return NextResponse.json({
    totalUsers,
    totalOrders,
    paidOrders,
    grossRevenueCents: revenue._sum.totalCents ?? 0,
  });
}
