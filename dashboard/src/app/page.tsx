"use client";

import React, { useEffect, useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
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
      setBackendHealth("checking");
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000);
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
    return () => { isCancelled = true; };
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

  // Formatting Uptime Helper
  const formatUptime = (totalSeconds: number) => {
    const days = Math.floor(totalSeconds / (3600 * 24));
    const hours = Math.floor((totalSeconds % (3600 * 24)) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  // ── Render AUTHENTICATED Main Panel ──────────────────────────────────────
  return (
    <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
      <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      {/* Main Panel Content Area */}
      <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
        <Header onMenuClick={() => setMobileOpen(true)} />

        <main className="flex-grow p-6 space-y-8 max-w-[1280px] mx-auto w-full">
          {/* Welcome Banner */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 bg-gradient-to-r from-indigo-900/20 to-purple-900/10 rounded-2xl border border-indigo-500/10 backdrop-blur-md">
            <div>
              <h2 className="text-xl font-bold text-zinc-100 leading-tight">
                Hey, <span className="text-indigo-400">{user?.username}</span>!
              </h2>
              <p className="text-xs text-zinc-400 mt-1">
                Here is the global state and telemetry log for your connected Discord servers.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-zinc-500">System Version: v1.1.4</span>
            </div>
          </div>

          {/* Global Stats Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card
              title="Active Servers"
              value={botStats?.guilds ?? 0}
              icon={Server}
              desc="Total servers bot is invited to"
            />
            <Card
              title="Global Members"
              value={botStats?.members ?? 0}
              icon={Users}
              desc="Total users monitored"
            />
            <Card
              title="Gateway Latency"
              value={botStats ? `${botStats.latency} ms` : "0 ms"}
              icon={Activity}
              desc="Discord websocket ping"
            />
            <Card
              title="System Uptime"
              value={botStats ? formatUptime(botStats.uptime) : "0d 0h 0m"}
              icon={Clock}
              desc="Time since last container boot"
            />
          </div>

          {/* Server List & Live Log Split Panel */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Servers List Panel */}
            <div className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between px-1">
                <h3 className="text-sm font-bold text-zinc-300 uppercase tracking-wider">
                  Manage Servers
                </h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {guilds.map((guild) => (
                  <div
                    key={guild.id}
                    className="p-5 rounded-2xl glass-card flex flex-col justify-between h-44 group relative overflow-hidden"
                  >
                    {/* Glow effect on hover */}
                    <div className={`absolute -right-16 -top-16 w-32 h-32 rounded-full blur-[40px] opacity-10 transition duration-300 group-hover:scale-150 ${guild.invited ? "bg-indigo-500" : "bg-yellow-500"}`} />

                    <div className="flex items-center gap-4">
                      {guild.icon ? (
                        <img
                          src={`https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png`}
                          alt={guild.name}
                          className="h-12 w-12 rounded-xl border border-zinc-800"
                        />
                      ) : (
                        <div className="h-12 w-12 rounded-xl bg-zinc-800 border border-zinc-700 flex items-center justify-center font-bold text-lg text-zinc-400">
                          {guild.name.charAt(0)}
                        </div>
                      )}
                      <div>
                        <h4 className="font-bold text-sm text-zinc-200 truncate max-w-[160px]">
                          {guild.name}
                        </h4>
                        <span className="text-[10px] text-zinc-500 font-medium">ID: {guild.id}</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between border-t border-zinc-800/30 pt-4 mt-2">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${
                            guild.invited ? "bg-green-500" : "bg-zinc-700"
                          }`}
                        />
                        <span className="text-[11px] text-zinc-400 font-semibold">
                          {guild.invited ? "Invited" : "Not Invited"}
                        </span>
                      </div>

                      {guild.invited ? (
                        <button
                          onClick={() => selectGuild(guild.id)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600/10 hover:bg-indigo-600 text-indigo-400 hover:text-zinc-100 border border-indigo-500/25 hover:border-indigo-600 rounded-lg text-xs font-semibold tracking-wide transition duration-200 cursor-pointer"
                        >
                          <span>Manage</span>
                          <ArrowRight className="h-3 w-3" />
                        </button>
                      ) : (
                        <a
                          href={`https://discord.com/api/oauth2/authorize?client_id=${process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID || ""}&permissions=8&scope=bot%20applications.commands`}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1 px-3 py-1.5 bg-yellow-500/10 hover:bg-yellow-500 text-yellow-400 hover:text-zinc-950 border border-yellow-500/20 hover:border-yellow-500 rounded-lg text-xs font-semibold tracking-wide transition duration-200"
                        >
                          <span>Invite Bot</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Live Events Log Widget */}
            <div className="space-y-4">
              <div className="px-1">
                <h3 className="text-sm font-bold text-zinc-300 uppercase tracking-wider">
                  Live Security Alerts
                </h3>
              </div>

              <div className="p-5 rounded-2xl glass-card h-[380px] overflow-y-auto space-y-3 scrollbar-thin">
                {wsEvents.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-3">
                    <Activity className="h-8 w-8 text-zinc-600 animate-pulse" />
                    <p className="text-xs text-zinc-500">
                      Listening for real-time Discord & Auto-Mod event packets...
                    </p>
                  </div>
                ) : (
                  wsEvents.map((evt, idx) => (
                    <div
                      key={idx}
                      className="p-3 bg-zinc-900/40 rounded-xl border border-zinc-800/20 text-xs flex flex-col gap-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[10px] uppercase tracking-wider text-indigo-400">
                          {evt.event}
                        </span>
                        <span className="text-[9px] text-zinc-500">
                          {new Date(evt.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-zinc-300 font-medium leading-relaxed">
                        {evt.data?.message || `Event trigger logged for guild.`}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Telemetry Hardware Stats */}
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-zinc-300 uppercase tracking-wider px-1">
              Backend Hardware Telemetry
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <HardwareCard
                title="CPU Consumption"
                value={botStats ? `${botStats.cpu}%` : "0%"}
                icon={Cpu}
                progress={botStats?.cpu ?? 0}
              />
              <HardwareCard
                title="RAM Usage"
                value={botStats ? `${botStats.ram}%` : "0%"}
                icon={HardDrive}
                progress={botStats?.ram ?? 0}
              />
              <HardwareCard
                title="Service Status"
                value={botStats ? "HEALTHY" : "OFFLINE"}
                icon={CheckCircle}
                progress={botStats ? 100 : 0}
                color={botStats ? "bg-green-500" : "bg-red-500"}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

// ── Shared UI Card Components ──────────────────────────────────────────────

function Card({ title, value, icon: Icon, desc }: { title: string; value: any; icon: any; desc: string }) {
  return (
    <div className="p-5 rounded-2xl glass-card flex items-center justify-between">
      <div className="space-y-1">
        <span className="text-zinc-500 text-[11px] font-bold uppercase tracking-wider">{title}</span>
        <h3 className="text-xl font-bold text-zinc-100">{value}</h3>
        <p className="text-[10px] text-zinc-500 leading-tight">{desc}</p>
      </div>
      <div className="p-3 bg-zinc-900/60 rounded-xl border border-zinc-800/40 text-zinc-400">
        <Icon className="h-5 w-5" />
      </div>
    </div>
  );
}

function HardwareCard({
  title,
  value,
  icon: Icon,
  progress,
  color = "bg-indigo-500",
}: {
  title: string;
  value: string;
  icon: any;
  progress: number;
  color?: string;
}) {
  return (
    <div className="p-5 rounded-2xl glass-card flex flex-col justify-between h-32">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-zinc-900/60 rounded-lg border border-zinc-800/40 text-zinc-400">
            <Icon className="h-4 w-4" />
          </div>
          <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">
            {title}
          </span>
        </div>
        <span className="text-xs font-bold text-zinc-100">{value}</span>
      </div>

      <div className="space-y-1 mt-4">
        <div className="w-full h-1.5 bg-zinc-900 rounded-full overflow-hidden border border-zinc-800/20">
          <div
            className={`h-full ${color} rounded-full transition-all duration-500`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  );
}
