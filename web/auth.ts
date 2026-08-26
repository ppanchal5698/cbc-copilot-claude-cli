/**
 * NextAuth credentials auth.
 *
 * Passwords are verified by the API against bcrypt hashes in Mongo - the web
 * tier never sees a hash and never talks to the database directly.
 */
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

import { API_BASE } from "@/lib/api";

export const { handlers, signIn, signOut, auth } = NextAuth({
  trustHost: true,
  session: { strategy: "jwt" },
  pages: { signIn: "/signin" },
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        const response = await fetch(`${API_BASE}/api/auth/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
          cache: "no-store",
        }).catch(() => null);

        if (!response?.ok) return null;

        const user = await response.json();
        return {
          id: user.id,
          email: user.email,
          name: user.name,
          initials: user.initials,
          role: user.role,
        };
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.initials = (user as { initials?: string }).initials;
        token.role = (user as { role?: string }).role;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        session.user.id = token.sub ?? "";
        (session.user as { initials?: string }).initials = token.initials as string;
        (session.user as { role?: string }).role = token.role as string;
      }
      return session;
    },
  },
});
