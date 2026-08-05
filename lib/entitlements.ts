import { db } from "./database";

export async function userHasSkuEntitlement(userId: string, sku: string) {
  const entitlement = await db.entitlement.findFirst({
    where: {
      userId,
      sku,
      active: true,
    },
  });

  return Boolean(entitlement);
}
