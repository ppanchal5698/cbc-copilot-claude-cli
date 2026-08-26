/**
 * Pass-through to the FastAPI service.
 *
 * The browser needs a same-origin path for PDFs and page renders (the viewer
 * fetches them directly), and this keeps the API's address a server-side detail.
 */
import { NextRequest } from "next/server";

import { API_BASE } from "@/lib/api";
import { auth } from "@/auth";

async function proxy(request: NextRequest, path: string[]) {
  const session = await auth();
  if (!session) return new Response("Unauthorized", { status: 401 });

  const target = new URL(`${API_BASE}/api/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));
  if (session.user?.email && !target.searchParams.has("actor")) {
    target.searchParams.set("actor", session.user.email);
  }

  const upstream = await fetch(target, {
    method: request.method,
    headers: (() => {
      const headers = new Headers(request.headers);
      headers.delete("host");
      headers.delete("content-length");
      return headers;
    })(),
    body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.blob(),
    cache: "no-store",
  }).catch(() => null);

  if (!upstream) {
    return Response.json(
      { detail: `Cannot reach the API at ${API_BASE}.` },
      { status: 503 },
    );
  }

  const headers = new Headers(upstream.headers);
  headers.delete("content-encoding");
  headers.delete("content-length");
  return new Response(upstream.body, { status: upstream.status, headers });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function POST(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function PATCH(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function DELETE(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
