"use client";

import React, { useEffect, useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import OverviewTab from "@/components/tabs/OverviewTab";
import MessengerTab from "@/components/tabs/MessengerTab";
import AnnouncementsTab from "@/components/tabs/AnnouncementsTab";
import ModerationTab from "@/components/tabs/ModerationTab";
import AIPlaygroundTab from "@/components/tabs/AIPlaygroundTab";
import MusicTab from "@/components/tabs/MusicTab";
import {
  Server,
  Users,
  Activity,
  Cpu,
  HardDrive,
  CheckCircle,
  Clock,
  Brain,
  Shield,
  MessageSquare,
  AlertOctagon,
  ArrowRight,
  ExternalLink,
  Zap,
  Settings,
  RefreshCw,
  Radio,
  Check,
  AlertCircle,
  Megaphone,
  Music,
  Sparkles,
  LayoutDashboard,
} from "lucide-react";
import { motion } from "framer-motion";

export default function Home() {
  const {
    token,
    user,
    guilds,
    botStats,
    fetchBotStats,
    selectGuild,
    login,
    backendUrl,
    updateBackendUrl,
    activeTab,
    setActiveTab,
    wsEvents
  } = useDashboard();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [backendHealth, setBackendHealth] = useState<"checking" | "online" | "suspended" | "offline">("checking");
  const [showUrlConfig, setShowUrlConfig] = useState(false);
  const [urlInput, setUrlInput] = useState(backendUrl);

  // Ping backend health
  useEffect(() => {
    setUrlInput(backendUrl);
    let isCancelled = false;
    const checkHealth = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000);
        const res = await fetch(`${backendUrl}/health`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (res.ok) {
          if (!isCancelled) setBackendHealth("online");
        } else if (res.status === 503) {
          if (!isCancelled) setBackendHealth("suspended");
        } else {
          if (!isCancelled) setBackendHealth("offline");
        }
      } catch {
        if (!isCancelled) setBackendHealth("offline");
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => {
      isCancelled = true;
      clearInterval(interval);
    };
  }, [backendUrl]);

  // Auto-fetch bot stats when logged in
  useEffect(() => {
    if (token) {
      fetchBotStats();
      const interval = setInterval(fetchBotStats, 10000); // refresh every 10s
      return () => clearInterval(interval);
    }
  }, [token]);

  const handleLogin = async () => {
    setLoading(true);
    try {
      const redirectUri = typeof window !== "undefined" ? window.location.origin + "/api/auth/callback" : "";
      const res = await fetch(`${backendUrl}/api/auth/login?redirect_uri=${encodeURIComponent(redirectUri)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.url) {
          window.location.href = data.url;
        }
      }
    } catch (err) {
      console.error("Failed to start login:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleMasterLogin = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/auth/admin-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_key: "", user_id: "719932313919684670" })
      });
      if (res.ok) {
        const data = await res.json();
        // fetch guilds
        const gRes = await fetch(`${backendUrl}/api/guilds/list`, {
          headers: { "Authorization": `Bearer ${data.token}` }
        });
        const gData = gRes.ok ? await gRes.json() : [];
        login(data.token, data.user, gData.map((g: any) => ({ ...g, invited: true })));
      }
    } catch (err) {
      console.error("Master login error:", err);
    } finally {
      setLoading(false);
    }
  };

  // ── Render LOGIN Page if not authenticated ────────────────────────────────
  if (!token) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#020205] text-zinc-100 font-['Plus_Jakarta_Sans'] relative overflow-hidden">
        {/* Abstract Glowing Gradients */}
        <div className="absolute top-[-20%] left-[-20%] w-[60%] h-[60%] rounded-full bg-purple-600/15 blur-[150px]" />
        <div className="absolute bottom-[-20%] right-[-20%] w-[60%] h-[60%] rounded-full bg-pink-600/10 blur-[150px]" />

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="w-full max-w-[440px] px-8 py-10 rounded-2xl glass-card text-center space-y-7 relative z-10 border border-purple-500/20"
        >
          {/* Logo Icon */}
          <div className="flex justify-center">
            <div className="p-4 bg-purple-500/10 rounded-2xl border border-purple-500/30 animate-pulse-slow">
              <Zap className="h-10 w-10 text-purple-400" />
            </div>
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
              Welcome to <span className="text-purple-400">Sweety Bot</span>
            </h1>
            <p className="text-zinc-400 text-xs leading-relaxed max-w-[320px] mx-auto">
              Real-time telemetry, inter-server communications, direct message announcements, and moderation controls.
            </p>
          </div>

          {/* Backend Status Pill */}
          <div className="flex flex-col items-center gap-1.5">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-zinc-900/90 border border-zinc-800 text-[11px]">
              <span className="relative flex h-2 w-2">
                {backendHealth === "online" && (
                  <>
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </>
                )}
                {backendHealth === "suspended" && (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                )}
                {backendHealth === "offline" && (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                )}
                {backendHealth === "checking" && (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-zinc-500 animate-pulse"></span>
                )}
              </span>
              <span className="text-zinc-300 font-medium">
                {backendHealth === "online" && "Backend Online"}
                {backendHealth === "suspended" && "Render Suspended by Owner"}
                {backendHealth === "offline" && "Backend Offline / Unreachable"}
                {backendHealth === "checking" && "Checking Backend..."}
              </span>
              <button
                type="button"
                onClick={() => setShowUrlConfig(!showUrlConfig)}
                className="text-zinc-500 hover:text-zinc-300 transition ml-1"
                title="Configure Backend URL"
              >
                <Settings className="w-3 h-3" />
              </button>
            </div>

            {backendHealth === "suspended" && (
              <p className="text-[10px] text-amber-400/90 max-w-[340px] leading-tight text-center">
                ⚠️ Your Render service is suspended in your Render console. Click Resume in Render dashboard, or switch to localhost below.
              </p>
            )}

            {showUrlConfig && (
              <div className="w-full mt-2 p-3 bg-zinc-950/80 border border-zinc-800 rounded-xl text-left space-y-2">
                <label className="text-[10px] font-semibold text-zinc-400">Target Backend API URL:</label>
                <div className="flex gap-1.5">
                  <input
                    type="text"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder="https://... or http://localhost:10000"
                    className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                  />
                  <button
                    onClick={() => {
                      updateBackendUrl(urlInput);
                      setShowUrlConfig(false);
                    }}
                    className="px-2.5 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-medium transition"
                  >
                    Save
                  </button>
                </div>
                <div className="flex gap-2 pt-1 text-[10px]">
                  <button
                    type="button"
                    onClick={() => {
                      setUrlInput("https://sweety-bot-ohio.onrender.com");
                      updateBackendUrl("https://sweety-bot-ohio.onrender.com");
                    }}
                    className="text-purple-400 hover:underline"
                  >
                    Use Render
                  </button>
                  <span className="text-zinc-600">•</span>
                  <button
                    type="button"
                    onClick={() => {
                      setUrlInput("http://localhost:10000");
                      updateBackendUrl("http://localhost:10000");
                    }}
                    className="text-purple-400 hover:underline"
                  >
                    Use Localhost
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-3">
            <button
              onClick={handleLogin}
              disabled={loading}
              className="w-full py-3.5 px-4 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-700/50 rounded-xl text-sm font-semibold tracking-wide text-zinc-100 flex items-center justify-center gap-2 border border-purple-500/30 shadow-lg shadow-purple-600/20 hover:shadow-purple-600/35 transition-all duration-300 cursor-pointer disabled:cursor-not-allowed"
            >
              {loading ? (
                <span>Authenticating...</span>
              ) : (
                <>
                  <MessageSquare className="h-4 w-4" />
                  <span>Log In with Discord</span>
                </>
              )}
            </button>

            <button
              onClick={handleMasterLogin}
              disabled={loading}
              className="w-full py-3 px-4 bg-zinc-900 hover:bg-zinc-800 rounded-xl text-xs font-semibold tracking-wide text-purple-300 flex items-center justify-center gap-2 border border-purple-500/30 transition-all duration-300 cursor-pointer"
            >
              <span>👑 1-Click Connect as Master Naraito</span>
            </button>
          </div>

          {/* Direct link to standalone dashboard */}
          <div className="pt-3 border-t border-zinc-800/60 flex flex-col gap-2">
            <a
              href="https://sweety-bot-ohio.onrender.com/dashboard"
              target="_blank"
              rel="noreferrer"
              className="text-[11px] text-zinc-400 hover:text-purple-300 flex items-center justify-center gap-1 transition"
            >
              <span>Open Standalone Web Command Center</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </motion.div>
      </div>
    );
  }

    // ── Render AUTHENTICATED Main Panel ──────────────────────────────────────
  const tabs = [
    { id: "overview", label: "Overview & Servers", icon: LayoutDashboard },
    { id: "messenger", label: "Channel Messenger", icon: MessageSquare },
    { id: "announcements", label: "DM Announcements", icon: Megaphone },
    { id: "moderation", label: "Moderation Hub", icon: Shield },
    { id: "ai_playground", label: "AI Playground", icon: Sparkles },
    { id: "music", label: "Music Controls", icon: Music },
  ];

  return (
    <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
      <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      {/* Main Panel Content Area */}
      <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
        <Header onMenuClick={() => setMobileOpen(true)} />

        <main className="flex-grow p-6 space-y-6 max-w-[1280px] mx-auto w-full">
          {/* Top Tab Switcher */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none border-b border-zinc-800/60">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold whitespace-nowrap transition cursor-pointer ${
                    isActive
                      ? "bg-purple-600/15 border border-purple-500/40 text-purple-300 shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 border border-transparent"
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? "text-purple-400" : "text-zinc-500"}`} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Active Tab Panel Content */}
          {activeTab === "overview" && <OverviewTab />}
          {activeTab === "messenger" && <MessengerTab />}
          {activeTab === "announcements" && <AnnouncementsTab />}
          {activeTab === "moderation" && <ModerationTab />}
          {activeTab === "ai_playground" && <AIPlaygroundTab />}
          {activeTab === "music" && <MusicTab />}
        </main>
      </div>
    </div>
  );
}
