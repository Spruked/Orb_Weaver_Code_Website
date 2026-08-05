import { NextResponse } from "next/server";
import { z } from "zod";
import { createPendingOrder } from "../../../lib/orders";
import { requireUser } from "../../../lib/security";

const schema = z.object({
  sku: z.enum(["developer", "team", "enterprise"]),
});

export async function POST(req: Request) {
  const user = await requireUser();
  if (user instanceof NextResponse) return user;

  try {
    const body = schema.parse(await req.json());
    const order = await createPendingOrder(user.id, body.sku);

    return NextResponse.json({
      orderId: order.id,
      status: order.status,
      amountCents: order.totalCents,
      message: "Order created. Complete payment with your provider session.",
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to create checkout." },
      { status: 400 },
    );
  }
}
