import { NextResponse } from "next/server";
import { getScores } from "@/app/lib/db";

// force-static so the route can be pre-rendered into a plain JSON file during the
// static export (GitHub Pages) build. In `next dev` it is still recomputed on request,
// and a node-server deployment can change this to "force-dynamic" for live reads.
export const dynamic = "force-static";

export function GET() {
  try {
    const data = getScores();
    return NextResponse.json(data);
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
