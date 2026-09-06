import { SignJWT, jwtVerify, type JWTPayload } from "jose";

export const SESSION_COOKIE = "owcc_session";
export const SESSION_AGE_SECONDS = 60 * 60 * 24 * 14;

export type SessionClaims = JWTPayload & {
  sub: string;
  role?: string;
};

function sessionSecret() {
  const secret = process.env.SESSION_SECRET;
  if (!secret) {
    throw new Error("SESSION_SECRET is not configured.");
  }
  return new TextEncoder().encode(secret);
}

export async function createSessionToken(userId: string, role: string) {
  return new SignJWT({ sub: userId, role })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_AGE_SECONDS}s`)
    .sign(sessionSecret());
}

export async function verifySessionToken(token: string): Promise<SessionClaims | null> {
  try {
    const { payload } = await jwtVerify(token, sessionSecret(), {
      algorithms: ["HS256"],
      requiredClaims: ["sub", "iat", "exp"],
    });

    if (typeof payload.sub !== "string" || payload.sub.length === 0) {
      return null;
    }

    return payload as SessionClaims;
  } catch {
    return null;
  }
}
