"use client";

import React, { useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import { Music, Play, Pause, SkipForward, Square, Radio, CheckCircle2, AlertCircle, Loader2, Volume2 } from "lucide-react";

export default function MusicTab() {
  const { backendUrl, token, guilds, botStats, fetchBotStats } = useDashboard();

  const [selectedGuild, setSelectedGuild] = useState<string>(guilds[0]?.id || "");
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<{ text: string; success: boolean } | null>(null);

  const handleAction = async (action: "pause" | "resume" | "skip" | "stop") => {
    if (!selectedGuild) {
      setStatusMsg({ text: "Please select a server voice client.", success: false });
      return;
    }

    setLoadingAction(action);
    setStatusMsg(null);

    try {
      const res = await fetch(`${backendUrl}/api/music/control`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          guild_id: selectedGuild,
          action: action
        })
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setStatusMsg({ text: data.message || `Action ${action.toUpperCase()} sent to player.`, success: true });
        fetchBotStats();
      } else {
        setStatusMsg({ text: data.detail || "Failed to execute music control command.", success: false });
      }
    } catch {
      setStatusMsg({ text: "Network error sending music command.", success: false });
    } finally {
      setLoadingAction(null);
    }
  };

  const activeStreams = botStats?.active_music_streams || [];

  return (
    <div className="space-y-6">
      <div className="p-5 bg-gradient-to-r from-emerald-900/20 via-teal-900/10 to-indigo-900/10 rounded-2xl border border-emerald-500/20 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-emerald-500/15 rounded-xl border border-emerald-500/30 text-emerald-400">
            <Music className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-zinc-100">Live Music & Voice Remote Controller</h2>
            <p className="text-xs text-zinc-400">
              Manage YouTube & Spotify audio playback across server voice channels remotely.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Controls Card */}
        <div className="lg:col-span-2 p-6 rounded-2xl glass-card space-y-5">
          <div>
            <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Select Voice Server</label>
            <select
              value={selectedGuild}
              onChange={(e) => setSelectedGuild(e.target.value)}
              className="w-full px-3 py-2.5 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
            >
              {guilds.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>

          {/* Quick Remote Control Action Buttons */}
          <div className="pt-2 border-t border-zinc-800/60">
            <label className="text-xs font-semibold text-zinc-300 block mb-3">Playback Remote Controls</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <button
                type="button"
                onClick={() => handleAction("resume")}
                disabled={loadingAction !== null}
                className="p-3 bg-zinc-900/60 hover:bg-emerald-600/15 border border-zinc-800 hover:border-emerald-500/40 rounded-xl flex items-center justify-center gap-2 text-xs font-bold text-emerald-300 transition cursor-pointer disabled:opacity-50"
              >
                {loadingAction === "resume" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                <span>Resume</span>
              </button>

              <button
                type="button"
                onClick={() => handleAction("pause")}
                disabled={loadingAction !== null}
                className="p-3 bg-zinc-900/60 hover:bg-amber-600/15 border border-zinc-800 hover:border-amber-500/40 rounded-xl flex items-center justify-center gap-2 text-xs font-bold text-amber-300 transition cursor-pointer disabled:opacity-50"
              >
                {loadingAction === "pause" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Pause className="w-4 h-4" />}
                <span>Pause</span>
              </button>

              <button
                type="button"
                onClick={() => handleAction("skip")}
                disabled={loadingAction !== null}
                className="p-3 bg-zinc-900/60 hover:bg-blue-600/15 border border-zinc-800 hover:border-blue-500/40 rounded-xl flex items-center justify-center gap-2 text-xs font-bold text-blue-300 transition cursor-pointer disabled:opacity-50"
              >
                {loadingAction === "skip" ? <Loader2 className="w-4 h-4 animate-spin" /> : <SkipForward className="w-4 h-4" />}
                <span>Skip</span>
              </button>

              <button
                type="button"
                onClick={() => handleAction("stop")}
                disabled={loadingAction !== null}
                className="p-3 bg-zinc-900/60 hover:bg-red-600/15 border border-zinc-800 hover:border-red-500/40 rounded-xl flex items-center justify-center gap-2 text-xs font-bold text-red-300 transition cursor-pointer disabled:opacity-50"
              >
                {loadingAction === "stop" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
                <span>Stop</span>
              </button>
            </div>
          </div>

          {statusMsg && (
            <div
              className={`p-3 rounded-xl border flex items-center gap-2 text-xs ${
                statusMsg.success
                  ? "bg-emerald-950/30 border-emerald-500/30 text-emerald-300"
                  : "bg-red-950/30 border-red-500/30 text-red-300"
              }`}
            >
              {statusMsg.success ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
              <span>{statusMsg.text}</span>
            </div>
          )}
        </div>

        {/* Active Streams Status Card */}
        <div className="p-6 rounded-2xl glass-card space-y-4">
          <div className="flex items-center gap-2 text-emerald-400">
            <Radio className="w-4 h-4" />
            <h3 className="text-xs font-bold uppercase tracking-wider">Active Audio Streams</h3>
          </div>

          <div className="space-y-3">
            {activeStreams.length === 0 ? (
              <div className="p-6 text-center text-zinc-500 text-xs italic space-y-1">
                <Volume2 className="w-6 h-6 mx-auto text-zinc-600 mb-2" />
                <p>No voice connections active right now.</p>
                <p className="text-[10px]">Use <code className="text-emerald-400">!play &lt;song&gt;</code> in Discord to start playback.</p>
              </div>
            ) : (
              activeStreams.map((st: any, idx: number) => (
                <div key={idx} className="p-3 bg-zinc-900/70 border border-zinc-800 rounded-xl space-y-1 text-xs">
                  <span className="font-bold text-zinc-200">{st.guild_name}</span>
                  <span className="text-[10px] text-zinc-400 block">Playing: {st.now_playing || "Audio Track"}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
