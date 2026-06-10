"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, clearStoredTokens, getStoredAccessToken, getStoredRefreshToken, setStoredTokens } from "@/lib/api";
import type { AuthSession, ForgotPasswordResponse, LoginPayload, RegisterPayload, User } from "@/types";

type AuthContextValue = {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  forgotPassword: (email: string) => Promise<ForgotPasswordResponse>;
  resetPassword: (resetToken: string, newPassword: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const accessToken = getStoredAccessToken();
      const refreshToken = getStoredRefreshToken();
      if (!accessToken) {
        setIsLoading(false);
        return;
      }

      try {
        const session = await authApi.me();
        if (!cancelled) {
          setUser(session.user);
        }
      } catch {
        if (!refreshToken) {
          clearStoredTokens();
          if (!cancelled) setUser(null);
        } else {
          try {
            const refreshed = await authApi.refresh(refreshToken);
            setStoredTokens(refreshed);
            const session = await authApi.me();
            if (!cancelled) {
              setUser(session.user);
            }
          } catch {
            clearStoredTokens();
            if (!cancelled) setUser(null);
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  async function applySession(tokens: AuthSession) {
    setStoredTokens(tokens);
    const session = await authApi.me();
    setUser(session.user);
    queryClient.invalidateQueries();
  }

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isLoading,
    isAuthenticated: !!user,
    login: async (payload) => {
      const tokens = await authApi.login(payload);
      await applySession(tokens);
    },
    register: async (payload) => {
      const tokens = await authApi.register(payload);
      await applySession(tokens);
    },
    forgotPassword: async (email) => authApi.forgotPassword(email),
    resetPassword: async (resetToken, newPassword) => {
      const tokens = await authApi.resetPassword({ resetToken, newPassword });
      await applySession(tokens);
    },
    logout: () => {
      clearStoredTokens();
      setUser(null);
      queryClient.clear();
    },
  }), [isLoading, queryClient, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
