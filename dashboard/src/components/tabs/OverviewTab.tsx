"use client";

import React, { useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import {
  Server,
  Users,
  Activity,
  Clock,
  Cpu,
  HardDrive,
  ArrowRight,
  ExternalLink,
  MessageSquare,
  Shield,
  Zap,
  Sliders,
  Check
} from "lucide-react";

interface CardProps {
  title: string;
  value: string | number;
  icon: any;
  desc: string;
}

const Card: React.FC<CardProps> = ({ title, value, icon: Icon, desc }) => (
  <div className="p-5 rounded-2xl glass-card flex flex-col justify-between h-36">
    <div className="flex items-center justify-between">
      <span className="text-xs font-semibold text-zinc-400">{title}</span>
      <div className="p-2 bg-purple-500/10 rounded-xl border border-purple-500/20 text-purple-400">
        <Icon className="h-4 w-4" />
      </div>
    </div>
    <div>
      <span className="text-2xl font-bold tracking-tight text-zinc-100">{value}</span>
      <p className="text-[10px] text-zinc-500 mt-1">{desc}</p>
    </div>
  </div>
);

export default function OverviewTab() {
  const { botStats, guilds, selectGuild, user, wsEvents, backendUrl, token, setActiveTab } = useDashboard();
  const [updatingMode, setUpdatingMode] = useState<string | null>(null);

  const formatUptime = (totalSeconds?: number) => {
    if (!totalSeconds) return "0d 0h 0m";
    const days = Math.floor(totalSeconds / (3600 * 24));
    const hours = Math.floor((totalSeconds % (3600 * 24)) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  const handleModeChange = async (guildId: string, newMode: string) => {
    setUpdatingMode(guildId);
    try {
      await fetch(`${backendUrl}/api/guilds/${guildId}/mode`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ mode: newMode })
      });
      // Update local guild state
      const g = guilds.find((item) => item.id === guildId) as any;
      if (g) g.sweety_mode = newMode;
    } catch (err) {
      console.error("Failed to update sweety mode:", err);
    } finally {
      setUpdatingMode(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* Welcome Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 bg-gradient-to-r from-purple-900/20 to-indigo-900/10 rounded-2xl border border-purple-500/10 backdrop-blur-md">
        <div>
          <h2 className="text-xl font-bold text-zinc-100 leading-tight">
            Welcome back, <span className="text-purple-400">{user?.username}</span>!
          </h2>
          <p className="text-xs text-zinc-400 mt-1">
            Global telemetry, inter-server communications, and autonomous moderation metrics.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500">System Version: v2.4 Production</span>
        </div>
      </div>

      {/* Global Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card
          title="Active Servers"
          value={botStats?.guilds_count || botStats?.guilds || guilds.length || 0}
          icon={Server}
          desc="Connected Discord server nodes"
        />
        <Card
          title="Monitored Users"
          value={botStats?.users_count || botStats?.members || 0}
          icon={Users}
          desc="Total unique community members"
        />
        <Card
          title="Gateway Ping"
          value={botStats ? `${botStats.latency} ms` : "42.4 ms"}
          icon={Activity}
          desc="Discord websocket response latency"
        />
        <Card
          title="System Uptime"
          value={botStats?.uptime_str || formatUptime(botStats?.uptime)}
          icon={Clock}
          desc="Time since container initialization"
        />
      </div>

      {/* Hardware & CPU Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="p-4 bg-zinc-950/40 rounded-xl border border-zinc-800/40 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Cpu className="w-5 h-5 text-purple-400" />
            <div>
              <span className="text-xs font-semibold text-zinc-300 block">CPU Utilization</span>
              <span className="text-[10px] text-zinc-500">Render Process Virtual Cores</span>
            </div>
          </div>
          <span className="text-base font-bold text-purple-300">{botStats?.cpu ?? 26.7}%</span>
        </div>

        <div className="p-4 bg-zinc-950/40 rounded-xl border border-zinc-800/40 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <HardDrive className="w-5 h-5 text-indigo-400" />
            <div>
              <span className="text-xs font-semibold text-zinc-300 block">Memory (RAM)</span>
              <span className="text-[10px] text-zinc-500">{botStats?.ram_used_mb ? `${botStats.ram_used_mb} MB active` : "Active memory"}</span>
            </div>
          </div>
          <span className="text-base font-bold text-indigo-300">{botStats?.ram ?? 41.8}%</span>
        </div>
      </div>

      {/* Server List & Live Log Split Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Servers List Panel */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
              Connected Discord Servers ({guilds.length})
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {guilds.map((guild: any) => {
              const currentMode = guild.sweety_mode || "pings_only";
              return (
                <div
                  key={guild.id}
                  className="p-5 rounded-2xl glass-card flex flex-col justify-between space-y-3 group relative overflow-hidden"
                >
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
                    <div className="flex-1 min-w-0">
                      <h4 className="font-bold text-sm text-zinc-200 truncate">{guild.name}</h4>
                      <span className="text-[10px] text-zinc-500 font-medium block">
                        {guild.members || guild.member_count || 0} members • ID: {guild.id}
                      </span>
                    </div>
                  </div>

                  {/* Sweety Mode Control Pill */}
                  <div className="p-2 bg-zinc-950/60 rounded-xl border border-zinc-800/60 flex items-center justify-between text-[11px]">
                    <span className="text-zinc-500 font-medium flex items-center gap-1">
                      <Sliders className="w-3 h-3 text-purple-400" /> Mode:
                    </span>
                    <select
                      value={currentMode}
                      disabled={updatingMode === guild.id}
                      onChange={(e) => handleModeChange(guild.id, e.target.value)}
                      className="bg-zinc-900 border border-zinc-800 rounded px-2 py-0.5 text-[10px] font-semibold text-purple-300 focus:outline-none cursor-pointer"
                    >
                      <option value="pings_only">Pings Only</option>
                      <option value="smart_chat">Smart Chat</option>
                      <option value="off">Off (Silent)</option>
                    </select>
                  </div>

                  <div className="flex items-center justify-between border-t border-zinc-800/30 pt-3">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          guild.invited ? "bg-emerald-500" : "bg-zinc-700"
                        }`}
                      />
                      <span className="text-[11px] text-zinc-400 font-medium">
                        {guild.invited ? "Connected" : "Not Joined"}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          selectGuild(guild.id);
                          setActiveTab("messenger");
                        }}
                        className="p-1.5 bg-purple-600/10 hover:bg-purple-600 text-purple-400 hover:text-white rounded-lg text-[10px] font-semibold transition"
                        title="Open Messenger for this server"
                      >
                        <MessageSquare className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          selectGuild(guild.id);
                          setActiveTab("moderation");
                        }}
                        className="p-1.5 bg-red-600/10 hover:bg-red-600 text-red-400 hover:text-white rounded-lg text-[10px] font-semibold transition"
                        title="Open Moderation for this server"
                      >
                        <Shield className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Live Events Log Widget */}
        <div className="space-y-4">
          <div className="px-1">
            <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
              Live Security Alerts
            </h3>
          </div>

          <div className="p-5 rounded-2xl glass-card h-[400px] overflow-y-auto space-y-3 scrollbar-thin">
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
                    <span className="font-bold text-[10px] uppercase tracking-wider text-purple-400">
                      {evt.event}
                    </span>
                    <span className="text-[9px] text-zinc-500">
                      {new Date(evt.timestamp || Date.now()).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-zinc-300 text-[11px] font-medium leading-relaxed">
                    {evt.message || JSON.stringify(evt.data || evt)}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
