import { NextResponse } from "next/server";
import { z } from "zod";
import { db } from "../../../../lib/database";
import { createSessionToken, setSessionCookie, verifyPassword } from "../../../../lib/security";

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export async function POST(req: Request) {
  try {
    const body = schema.parse(await req.json());
    const user = await db.user.findUnique({ where: { email: body.email.toLowerCase() } });

    if (!user) {
      return NextResponse.json({ error: "Invalid email or password." }, { status: 401 });
    }

    const ok = await verifyPassword(body.password, user.passwordHash);
    if (!ok) {
      return NextResponse.json({ error: "Invalid email or password." }, { status: 401 });
    }

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
      { error: error instanceof Error ? error.message : "Invalid login payload." },
      { status: 400 },
    );
  }
}
