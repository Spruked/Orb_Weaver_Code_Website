import { NextResponse } from "next/server";
import { markOrderPaid } from "../../../../lib/orders";

export async function POST(req: Request) {
  const webhookSecret = process.env.PAYMENT_WEBHOOK_SECRET;
  const signature = req.headers.get("x-payment-signature");

  if (!webhookSecret || !signature || signature !== webhookSecret) {
    return NextResponse.json({ error: "Invalid webhook signature." }, { status: 401 });
  }

  const payload = await req.json();
  const { orderId, providerEventId, provider } = payload ?? {};

  if (!orderId || !providerEventId || !provider) {
    return NextResponse.json({ error: "Malformed payment payload." }, { status: 400 });
  }

  await markOrderPaid(orderId, provider, providerEventId, JSON.stringify(payload));

  return NextResponse.json({ status: "processed" });
}
