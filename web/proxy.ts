/**
 * Route protection.
 *
 * Next 16 renamed `middleware` to `proxy` and pins it to the Node runtime -
 * see node_modules/next/dist/docs/01-app/02-guides/upgrading/version-16.md
 */
import { auth } from "@/auth";

export default auth((request) => {
  const signedIn = !!request.auth;
  const { pathname } = request.nextUrl;

  if (!signedIn && pathname !== "/signin") {
    return Response.redirect(new URL("/signin", request.nextUrl));
  }
  if (signedIn && pathname === "/signin") {
    return Response.redirect(new URL("/dashboard", request.nextUrl));
  }
});

export const config = {
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico|pdf.worker.min.mjs|.*\.svg).*)"],
};
