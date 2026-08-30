/**
 * Pass-through to the FastAPI service.
 *
 * The browser needs a same-origin path for PDFs and page renders (the viewer
 * fetches them directly), and this keeps the API's address a server-side detail.
 */
import { NextRequest } from "next/server";

import { auth } from "@/auth";
import { API_BASE } from "@/lib/api";
import { internalApiHeaders } from "@/lib/internal-api";

async function proxy(request: NextRequest, path: string[]) {
  const session = await auth();
  if (!session) return new Response("Unauthorized", { status: 401 });

  const target = new URL(`${API_BASE}/api/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => {
    if (key !== "actor") {
      target.searchParams.set(key, value);
    }
  });

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  for (const [key, value] of Object.entries(internalApiHeaders(session.user?.email))) {
    headers.set(key, value);
  }

  const contentType = request.headers.get("content-type") ?? "";

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    // A navigation away, or a search superseded by the next keystroke, aborts
    // the browser's request; without this the upstream call kept running and
    // the API kept working on an answer nobody was waiting for.
    signal: request.signal,
  };

  if (!["GET", "HEAD"].includes(request.method)) {
    if (contentType.includes("multipart/form-data")) {
      // Re-pack multipart so upstream fetch generates a fresh boundary FastAPI can parse.
      const form = await request.formData();
      const upstreamForm = new FormData();
      for (const [key, value] of form.entries()) {
        upstreamForm.append(key, value);
      }
      init.body = upstreamForm;
      headers.delete("content-type");
    } else {
      init.body = await request.arrayBuffer();
    }
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (error) {
    // An aborted request is the caller giving up, not a failure worth reporting.
    if (error instanceof DOMException && error.name === "AbortError") {
      return new Response(null, { status: 499 });
    }
    return Response.json(
      { detail: `Cannot reach the API at ${API_BASE}.` },
      { status: 503 },
    );
  }

  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function POST(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function PUT(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function PATCH(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function DELETE(request: NextRequest, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
