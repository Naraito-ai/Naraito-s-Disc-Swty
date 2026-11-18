"use client";

import React from "react";
import { useDashboard } from "@/context/DashboardContext";
import { Menu, Wifi, WifiOff, Bell, User as UserIcon } from "lucide-react";
import Image from "next/image";

export default function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { user, wsConnected, activeGuild, botStats } = useDashboard();
  const isOnline = botStats
    ? (botStats.online !== undefined ? botStats.online !== false : (botStats.discord_gateway === "connected" || botStats.guilds > 0))
    : true;

  return (
    <header className="h-16 border-b border-zinc-800/40 bg-[#07070a]/60 backdrop-blur-md sticky top-0 z-10 flex items-center justify-between px-6 font-['Plus_Jakarta_Sans']">
      {/* Left Area (Menu / Title) */}
      <div className="flex items-center gap-4">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 text-zinc-400 hover:text-zinc-200 bg-zinc-900/60 rounded-xl border border-zinc-800/40 hover:bg-zinc-800/60 transition cursor-pointer"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div>
          <span className="text-[13px] font-semibold text-zinc-100">
            {activeGuild ? activeGuild.name : "Global Controls"}
          </span>
          <span className="hidden md:inline-block mx-2 text-zinc-600 text-xs">/</span>
          <span className="hidden md:inline-block text-zinc-500 text-[11px] font-medium uppercase tracking-wider">
            {activeGuild ? "Server Dashboard" : "Telemetry Stats"}
          </span>
        </div>
      </div>

      {/* Right Area (Websocket Connection Status, Notifications, Profile) */}
      <div className="flex items-center gap-4">
        {/* Real-time Connection Indicator */}
        <div
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-[11px] font-semibold transition-all duration-300 ${
            isOnline
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
              : "bg-red-500/10 border-red-500/30 text-red-400 animate-pulse"
          }`}
        >
          {isOnline ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>{wsConnected ? "Gateway Live" : "Bot Online"}</span>
            </>
          ) : (
            <>
              <WifiOff className="h-3 w-3" />
              <span>Offline</span>
            </>
          )}
        </div>

        {/* User Info & Avatar */}
        {user && (
          <div className="flex items-center gap-3 pl-3 border-l border-zinc-800/40">
            {user.avatar ? (
              <img
                src={`https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png`}
                alt={user.username}
                className="h-8 w-8 rounded-full border border-zinc-800"
              />
            ) : (
              <div className="h-8 w-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-400">
                <UserIcon className="h-4 w-4" />
              </div>
            )}
            <div className="hidden sm:block text-left">
              <p className="text-xs font-semibold text-zinc-200 leading-tight">{user.username}</p>
              <span className="text-[10px] text-zinc-500 font-medium">Administrator</span>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
