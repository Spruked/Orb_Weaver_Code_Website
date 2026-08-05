import crypto from "node:crypto";
import { db } from "./database";

function hashToken(token: string) {
  return crypto.createHash("sha256").update(token).digest("hex");
}

export async function createDownloadGrant(userId: string, orderId: string, artifactId: string) {
  const token = crypto.randomBytes(24).toString("hex");
  const expiresAt = new Date(Date.now() + 1000 * 60 * 10);

  await db.downloadGrant.create({
    data: {
      userId,
      orderId,
      artifactId,
      tokenHash: hashToken(token),
      expiresAt,
    },
  });

  return {
    token,
    expiresAt,
  };
}
