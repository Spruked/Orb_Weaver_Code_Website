import { createPendingOrder } from "./orders";
import type { ProductSku } from "./catalog";

export async function createCheckoutSession(userId: string, sku: ProductSku) {
  return createPendingOrder(userId, sku);
}
