import { NextResponse } from "next/server";
import { getScores } from "@/app/lib/db";

// Always read fresh from SQLite (the collector updates it out of band).
export const dynamic = "force-dynamic";

export function GET() {
  try {
    const data = getScores();
    return NextResponse.json(data);
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
