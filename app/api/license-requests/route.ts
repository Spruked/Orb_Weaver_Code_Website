import { NextResponse } from "next/server";
import { z } from "zod";
import { db } from "../../../lib/database";
import { requireUser } from "../../../lib/security";

const schema = z.object({
  orderId: z.string().min(1),
  sku: z.string().min(1),
  machineNote: z.string().max(500).optional(),
});

export async function POST(req: Request) {
  const user = await requireUser();
  if (user instanceof NextResponse) return user;

  try {
    const body = schema.parse(await req.json());

    const existing = await db.order.findFirst({
      where: {
        id: body.orderId,
        userId: user.id,
      },
    });

    if (!existing) {
      return NextResponse.json({ error: "Order not found." }, { status: 404 });
    }

    const request = await db.licenseRequest.create({
      data: {
        userId: user.id,
        orderId: body.orderId,
        sku: body.sku,
        machineNote: body.machineNote,
      },
    });

    return NextResponse.json({ request });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Invalid payload." },
      { status: 400 },
    );
  }
}
