import { NextResponse } from "next/server";
import { z } from "zod";
import { db } from "../../../../lib/database";
import { createSessionToken, hashPassword, setSessionCookie } from "../../../../lib/security";

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(10),
  name: z.string().min(1).max(80).optional(),
});

export async function POST(req: Request) {
  try {
    const body = schema.parse(await req.json());

    const exists = await db.user.findUnique({ where: { email: body.email.toLowerCase() } });
    if (exists) {
      return NextResponse.json({ error: "Email already registered." }, { status: 409 });
    }

    const user = await db.user.create({
      data: {
        email: body.email.toLowerCase(),
        name: body.name,
        passwordHash: await hashPassword(body.password),
      },
    });

    const token = await createSessionToken(user.id, user.role);
    await setSessionCookie(token);

    return NextResponse.json({
      user: {
        id: user.id,
        email: user.email,
        role: user.role,
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Invalid signup payload." },
      { status: 400 },
    );
  }
}
