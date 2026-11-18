"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useRouter } from "next/navigation";

// Define Types
export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  invited: boolean;
  members?: number;
  channels?: number;
  roles?: number;
}

export interface User {
  id: string;
  username: string;
  avatar: string | null;
}

interface DashboardContextType {
  token: string | null;
  user: User | null;
  guilds: Guild[];
  activeGuildId: string | null;
  activeGuild: Guild | null;
  botStats: any;
  wsConnected: boolean;
  wsEvents: any[];
  login: (token: string, user: User, guilds: Guild[]) => void;
  logout: () => void;
  selectGuild: (guildId: string) => void;
  fetchBotStats: () => Promise<void>;
  updateGuildStatus: (guildId: string, invited: boolean) => void;
  backendUrl: string;
  updateBackendUrl: (url: string) => void;
  wsUrl: string;
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export const DashboardProvider = ({ children }: { children: ReactNode }) => {
  const router = useRouter();
  
  // Base URLs (Adjust automatically based on deployment environment)
  const defaultProdBackend = "https://sweety-bot-ohio.onrender.com";
  const [backendUrl, setBackendUrl] = useState(process.env.NEXT_PUBLIC_BACKEND_URL || defaultProdBackend);
  const [wsUrl, setWsUrl] = useState((process.env.NEXT_PUBLIC_BACKEND_URL || defaultProdBackend).replace(/^http/, "ws"));

  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [activeGuildId, setActiveGuildId] = useState<string | null>(null);
  const [botStats, setBotStats] = useState<any>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [wsEvents, setWsEvents] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<string>("overview");

  // Dynamically set URLs in browser
  useEffect(() => {
    let savedBackend = localStorage.getItem("dash_backend_url");
    // Auto-migrate away from any old/dormant/suspended render services
    const isOutdatedService = savedBackend && (
      savedBackend.includes("sweety-discord-bot-fra") ||
      savedBackend.includes("sweety-discord-bot-sg") ||
      savedBackend.includes("discord-bot-cloud") ||
      savedBackend.includes("discord-gemini-bot")
    );
    if (isOutdatedService || !savedBackend) {
      savedBackend = defaultProdBackend;
      localStorage.setItem("dash_backend_url", defaultProdBackend);
    }

    if (savedBackend) {
      setBackendUrl(savedBackend);
      setWsUrl(savedBackend.replace(/^http/, "ws"));
      return;
    }
    const isLocal = typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");
    if (isLocal) {
      setBackendUrl("http://localhost:10000");
      setWsUrl("ws://localhost:10000");
    } else {
      const activeBackend = process.env.NEXT_PUBLIC_BACKEND_URL || defaultProdBackend;
      setBackendUrl(activeBackend);
      setWsUrl(activeBackend.replace(/^http/, "ws"));
    }
  }, []);

  const updateBackendUrl = (url: string) => {
    const clean = url.trim().replace(/\/$/, "");
    setBackendUrl(clean);
    setWsUrl(clean.replace(/^http/, "ws"));
    if (typeof window !== "undefined") {
      localStorage.setItem("dash_backend_url", clean);
    }
  };

  // Hydrate state from localStorage
  useEffect(() => {
    const savedToken = localStorage.getItem("dash_token");
    const savedUser = localStorage.getItem("dash_user");
    const savedGuilds = localStorage.getItem("dash_guilds");
    const savedActiveGuild = localStorage.getItem("dash_active_guild");

    if (savedToken && savedUser && savedGuilds) {
      setToken(savedToken);
      setUser(JSON.parse(savedUser));
      setGuilds(JSON.parse(savedGuilds));
      if (savedActiveGuild) {
        setActiveGuildId(savedActiveGuild);
      }
    }
  }, []);

  // Synchronize guilds and validate token
  useEffect(() => {
    if (!token) return;

    const syncSession = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/guilds/list`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const freshGuilds = await res.json();
          if (Array.isArray(freshGuilds) && freshGuilds.length > 0) {
            setGuilds(freshGuilds.map((g: any) => ({ ...g, invited: true })));
            localStorage.setItem("dash_guilds", JSON.stringify(freshGuilds.map((g: any) => ({ ...g, invited: true }))));
            if (!activeGuildId) {
              setActiveGuildId(freshGuilds[0].id);
              localStorage.setItem("dash_active_guild", freshGuilds[0].id);
            }
          }
        } else if (res.status === 401) {
          console.warn("Session expired or token invalid. Clearing session.");
          logout();
        }
      } catch (err) {
        console.error("Failed to sync session with backend:", err);
      }
    };

    syncSession();
  }, [token, backendUrl]);

  // WebSocket event subscription for alerts
  useEffect(() => {
    if (!token) {
      setWsConnected(false);
      return;
    }

    let ws: WebSocket;
    const connectWS = () => {
      try {
        const authParam = token ? `?token=${encodeURIComponent(token)}` : "";
        ws = new WebSocket(`${wsUrl}/api/ws/events${authParam}`);
        
        ws.onopen = () => {
          setWsConnected(true);
          console.log("🚀 Real-time events WebSocket connected.");
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            setWsEvents((prev) => [data, ...prev.slice(0, 49)]); // Maintain past 50 events
          } catch (err) {
            console.error("Error parsing WS message:", err);
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          console.log("WebSocket closed. Attempting reconnect in 5s...");
          setTimeout(connectWS, 5000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (e) {
        console.error("Failed to connect to events WS:", e);
      }
    };

    connectWS();

    return () => {
      if (ws) ws.close();
    };
  }, [token, wsUrl]);

  const login = (newToken: string, newUser: User, newGuilds: Guild[]) => {
    localStorage.setItem("dash_token", newToken);
    localStorage.setItem("dash_user", JSON.stringify(newUser));
    localStorage.setItem("dash_guilds", JSON.stringify(newGuilds));
    
    setToken(newToken);
    setUser(newUser);
    setGuilds(newGuilds);
    
    if (newGuilds.length > 0) {
      const firstGuild = newGuilds[0].id;
      setActiveGuildId(firstGuild);
      localStorage.setItem("dash_active_guild", firstGuild);
    }
    
    router.push("/");
  };

  const logout = () => {
    localStorage.clear();
    setToken(null);
    setUser(null);
    setGuilds([]);
    setActiveGuildId(null);
    setBotStats(null);
    router.push("/");
  };

  const selectGuild = (guildId: string) => {
    setActiveGuildId(guildId);
    localStorage.setItem("dash_active_guild", guildId);
  };

  const fetchBotStats = async () => {
    try {
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      
      const res = await fetch(`${backendUrl}/api/bot/overview`, { headers });
      if (res.ok) {
        const data = await res.json();
        setBotStats(data);
        return;
      }
      
      // Fallback
      const res2 = await fetch(`${backendUrl}/api/bot/stats`);
      if (res2.ok) {
        const data2 = await res2.json();
        setBotStats({
          ...data2,
          online: data2.discord_gateway === "connected" || (data2.guilds && data2.guilds > 0),
          guilds_count: data2.guilds,
          users_count: data2.members,
          uptime_seconds: data2.uptime
        });
      }
    } catch (err) {
      console.error("Failed to fetch bot stats:", err);
    }
  };

  const updateGuildStatus = (guildId: string, invited: boolean) => {
    setGuilds((prevGuilds) => {
      const updated = prevGuilds.map((g) => (g.id === guildId ? { ...g, invited } : g));
      localStorage.setItem("dash_guilds", JSON.stringify(updated));
      return updated;
    });
  };

  const activeGuild = guilds.find((g) => g.id === activeGuildId) || null;

  return (
    <DashboardContext.Provider
      value={{
        token,
        user,
        guilds,
        activeGuildId,
        activeGuild,
        botStats,
        wsConnected,
        wsEvents,
        login,
        logout,
        selectGuild,
        fetchBotStats,
        updateGuildStatus,
        backendUrl,
        updateBackendUrl,
        wsUrl,
        activeTab,
        setActiveTab,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
};

export const useDashboard = () => {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error("useDashboard must be used within a DashboardProvider");
  }
  return context;
};
