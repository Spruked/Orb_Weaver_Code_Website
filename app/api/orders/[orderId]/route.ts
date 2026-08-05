import { NextResponse } from "next/server";
import { db } from "../../../../lib/database";
import { requireUser } from "../../../../lib/security";

type Ctx = { params: { orderId: string } };

export async function GET(_req: Request, ctx: Ctx) {
  const user = await requireUser();
  if (user instanceof NextResponse) return user;

  const order = await db.order.findUnique({
    where: { id: ctx.params.orderId },
    include: { items: true, paymentEvents: true },
  });

  if (!order) {
    return NextResponse.json({ error: "Order not found." }, { status: 404 });
  }

  if (order.userId !== user.id && user.role !== "ADMIN") {
    return NextResponse.json({ error: "Forbidden." }, { status: 403 });
  }

  return NextResponse.json({ order });
}
