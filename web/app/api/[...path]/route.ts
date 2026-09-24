import { NextRequest, NextResponse } from "next/server";

const API = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function proxy(req: NextRequest, path: string[]) {
  const target = `${API}/${path.join("/")}${req.nextUrl.search}`;
  try {
    const headers = new Headers();
    const ct = req.headers.get("content-type");
    if (ct) headers.set("content-type", ct);
    headers.set("x-forwarded-for", req.headers.get("x-forwarded-for") ?? "unknown");

    const res = await fetch(target, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.text(),
      cache: "no-store",
    });
    const body = await res.arrayBuffer();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "The sun server is offline. Start the Python API, or set API_URL." },
      { status: 503 },
    );
  }
}

export async function GET(req: NextRequest, ctx: RouteContext<"/api/[...path]">) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function POST(req: NextRequest, ctx: RouteContext<"/api/[...path]">) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
