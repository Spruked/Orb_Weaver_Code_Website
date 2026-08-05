import { db } from "./database";
import { getProductBySku, type ProductSku } from "./catalog";

export async function createPendingOrder(userId: string, sku: ProductSku) {
  const product = getProductBySku(sku);

  if (product.priceCents === null) {
    throw new Error("Enterprise plan requires direct sales contact.");
  }

  return db.order.create({
    data: {
      userId,
      subtotalCents: product.priceCents,
      totalCents: product.priceCents,
      items: {
        create: {
          sku: product.sku,
          name: product.name,
          quantity: 1,
          priceCents: product.priceCents,
        },
      },
    },
    include: {
      items: true,
    },
  });
}

export async function markOrderPaid(orderId: string, provider: string, providerEventId: string, payload: string) {
  const order = await db.order.update({
    where: { id: orderId },
    data: {
      status: "PAID",
      paymentEvents: {
        create: {
          provider,
          providerEventId,
          eventType: "payment.succeeded",
          verified: true,
          payload,
        },
      },
    },
    include: { items: true },
  });

  await db.entitlement.create({
    data: {
      userId: order.userId,
      orderId: order.id,
      sku: order.items[0]?.sku ?? "UNKNOWN",
      seats: 1,
      active: true,
    },
  });

  await db.licenseRequest.create({
    data: {
      userId: order.userId,
      orderId: order.id,
      sku: order.items[0]?.sku ?? "UNKNOWN",
      status: "PENDING",
    },
  });

  await db.order.update({
    where: { id: order.id },
    data: { status: "FULFILLMENT_PENDING" },
  });

  return order;
}
