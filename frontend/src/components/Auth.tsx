import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "../api/client";
import type { AppConfig } from "../api/types";

interface AuthValue {
  config: AppConfig | null;
  username: string | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      tokenStore.clear();
      setUsername(null);
    });
    const loadConfig = api.get<AppConfig>("/config/").then(setConfig).catch(() => setConfig(null));
    const loadUser = tokenStore.get()
      ? api.get<{ username: string }>("/auth/me/").then((me) => setUsername(me.username)).catch(() => tokenStore.clear())
      : Promise.resolve();
    Promise.all([loadConfig, loadUser]).finally(() => setReady(true));
  }, []);

  const login = useCallback(async (user: string, password: string) => {
    const result = await api.post<{ token: string; username: string }>("/auth/login/", { username: user, password });
    tokenStore.set(result.token);
    setUsername(result.username);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout/");
    } finally {
      tokenStore.clear();
      setUsername(null);
    }
  }, []);

  const value = useMemo(() => ({ config, username, ready, login, logout }), [config, username, ready, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
