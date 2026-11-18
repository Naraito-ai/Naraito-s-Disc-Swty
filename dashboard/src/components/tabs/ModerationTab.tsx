"use client";

import React, { useState, useEffect } from "react";
import { useDashboard } from "@/context/DashboardContext";
import { Shield, ShieldAlert, Ban, UserMinus, Clock, Volume2, AlertTriangle, Trash2, Lock, Unlock, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

export default function ModerationTab() {
  const { backendUrl, token, guilds } = useDashboard();

  const [selectedGuild, setSelectedGuild] = useState<string>(guilds[0]?.id || "");
  const [action, setAction] = useState<string>("timeout");
  const [targetId, setTargetId] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [duration, setDuration] = useState<number>(600); // 10 minutes in seconds
  const [deleteDays, setDeleteDays] = useState<number>(1);
  const [purgeCount, setPurgeCount] = useState<number>(25);

  const [channels, setChannels] = useState<any[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>("");
  const [loadingChannels, setLoadingChannels] = useState<boolean>(false);

  const [executing, setExecuting] = useState<boolean>(false);
  const [result, setResult] = useState<{ text: string; success: boolean } | null>(null);

  // Fetch channels for the selected guild
  useEffect(() => {
    if (!selectedGuild || !token) return;

    const fetchChannels = async () => {
      setLoadingChannels(true);
      try {
        const res = await fetch(`${backendUrl}/api/guilds/${selectedGuild}/channels`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          setChannels(data);
          if (data.length > 0) setSelectedChannel(data[0].id);
        }
      } catch (err) {
        console.error("Failed to load channels:", err);
      } finally {
        setLoadingChannels(false);
      }
    };

    fetchChannels();
  }, [selectedGuild, backendUrl, token]);

  const handleExecute = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedGuild) {
      setResult({ text: "Please select a target server.", success: false });
      return;
    }

    const needsUser = ["kick", "ban", "unban", "timeout", "untimeout", "warn"].includes(action);
    const needsChannel = ["purge", "lock", "unlock"].includes(action);

    if (needsUser && !targetId.trim()) {
      setResult({ text: "Please enter a target Discord User ID.", success: false });
      return;
    }

    if (needsChannel && !selectedChannel) {
      setResult({ text: "Please select a target channel.", success: false });
      return;
    }

    setExecuting(true);
    setResult(null);

    try {
      const payload: any = {
        guild_id: selectedGuild,
        action: action,
        user_id: needsUser ? targetId.trim() : undefined,
        channel_id: needsChannel ? selectedChannel : undefined,
        reason: reason.trim() || `Moderation action executed via Sweety Command Center`,
        duration: action === "timeout" ? duration : undefined,
        delete_days: action === "ban" ? deleteDays : undefined,
        purge_limit: action === "purge" ? purgeCount : undefined
      };

      const res = await fetch(`${backendUrl}/api/moderate/action`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setResult({
          text: data.message || `Action '${action.toUpperCase()}' completed successfully!`,
          success: true
        });
        setTargetId("");
        setReason("");
      } else {
        setResult({ text: data.detail || "Failed to execute moderation action.", success: false });
      }
    } catch {
      setResult({ text: "Network error communicating with moderation API.", success: false });
    } finally {
      setExecuting(false);
    }
  };

  const actionList = [
    { id: "timeout", label: "Timeout / Mute", icon: Clock, desc: "Isolate user from text & voice", color: "text-amber-400" },
    { id: "untimeout", label: "Remove Timeout", icon: Volume2, desc: "Restore member communication", color: "text-emerald-400" },
    { id: "warn", label: "Issue Warning", icon: AlertTriangle, desc: "Record infraction to database", color: "text-yellow-400" },
    { id: "kick", label: "Kick Member", icon: UserMinus, desc: "Remove user from server", color: "text-orange-400" },
    { id: "ban", label: "Ban Member", icon: Ban, desc: "Permanently ban & delete messages", color: "text-red-400" },
    { id: "purge", label: "Purge Messages", icon: Trash2, desc: "Bulk delete recent channel chat", color: "text-blue-400" },
    { id: "lock", label: "Lock Channel", icon: Lock, desc: "Restrict @everyone from sending messages", color: "text-rose-400" },
    { id: "unlock", label: "Unlock Channel", icon: Unlock, desc: "Re-enable channel chat permissions", color: "text-teal-400" }
  ];

  return (
    <div className="space-y-6">
      <div className="p-5 bg-gradient-to-r from-red-900/20 to-purple-900/10 rounded-2xl border border-red-500/20 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-red-500/15 rounded-xl border border-red-500/30 text-red-400">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-zinc-100">Instant Moderation Control Hub</h2>
            <p className="text-xs text-zinc-400">
              Execute real-time security actions across your Discord servers directly from your browser.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 p-6 rounded-2xl glass-card space-y-5">
          {/* Server Selector */}
          <div>
            <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Target Discord Server</label>
            <select
              value={selectedGuild}
              onChange={(e) => setSelectedGuild(e.target.value)}
              className="w-full px-3 py-2.5 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-red-500"
            >
              {guilds.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>

          {/* Action Selector Grid */}
          <div>
            <label className="text-xs font-semibold text-zinc-300 block mb-2">Select Security Action</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {actionList.map((act) => {
                const Icon = act.icon;
                const isSelected = action === act.id;
                return (
                  <button
                    type="button"
                    key={act.id}
                    onClick={() => setAction(act.id)}
                    className={`p-3 rounded-xl border text-left transition cursor-pointer flex flex-col justify-between h-20 ${
                      isSelected
                        ? "bg-red-600/15 border-red-500/50 shadow-sm"
                        : "bg-zinc-900/40 border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <Icon className={`h-4 w-4 ${act.color}`} />
                    <div>
                      <span className="text-xs font-bold block text-zinc-200">{act.label}</span>
                      <span className="text-[9px] text-zinc-500 line-clamp-1">{act.desc}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <form onSubmit={handleExecute} className="space-y-4 pt-2 border-t border-zinc-800/60">
            {/* User Target Input */}
            {["kick", "ban", "unban", "timeout", "untimeout", "warn"].includes(action) && (
              <div>
                <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Target Member User ID</label>
                <input
                  type="text"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  placeholder="e.g. 123456789012345678"
                  className="w-full px-3 py-2 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-red-500 font-mono"
                />
              </div>
            )}

            {/* Channel Target Input */}
            {["purge", "lock", "unlock"].includes(action) && (
              <div>
                <label className="text-xs font-semibold text-zinc-300 block mb-1.5">
                  Target Channel {loadingChannels && "(Loading...)"}
                </label>
                <select
                  value={selectedChannel}
                  onChange={(e) => setSelectedChannel(e.target.value)}
                  disabled={loadingChannels || channels.length === 0}
                  className="w-full px-3 py-2 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-red-500 disabled:opacity-50"
                >
                  {channels.map((c) => (
                    <option key={c.id} value={c.id}>
                      #{c.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Timeout Duration Selector */}
            {action === "timeout" && (
              <div>
                <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Mute / Timeout Duration</label>
                <div className="flex flex-wrap gap-2">
                  {[
                    { label: "60s", sec: 60 },
                    { label: "5m", sec: 300 },
                    { label: "10m", sec: 600 },
                    { label: "1h", sec: 3600 },
                    { label: "1d", sec: 86400 },
                    { label: "1w", sec: 604800 }
                  ].map((dur) => (
                    <button
                      type="button"
                      key={dur.sec}
                      onClick={() => setDuration(dur.sec)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition ${
                        duration === dur.sec
                          ? "bg-amber-500/20 border-amber-500 text-amber-300"
                          : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      {dur.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Purge Count */}
            {action === "purge" && (
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="text-xs font-semibold text-zinc-300">Message Purge Count</label>
                  <span className="text-xs font-bold text-red-400">{purgeCount} messages</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={100}
                  value={purgeCount}
                  onChange={(e) => setPurgeCount(parseInt(e.target.value))}
                  className="w-full accent-red-500 cursor-pointer"
                />
              </div>
            )}

            {/* Ban Delete Message Days */}
            {action === "ban" && (
              <div>
                <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Delete Message History</label>
                <select
                  value={deleteDays}
                  onChange={(e) => setDeleteDays(parseInt(e.target.value))}
                  className="w-full px-3 py-2 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-red-500"
                >
                  <option value={0}>Don't delete any message history</option>
                  <option value={1}>Delete messages from the past 24 hours</option>
                  <option value={7}>Delete messages from the past 7 days</option>
                </select>
              </div>
            )}

            {/* Reason */}
            <div>
              <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Action Reason / Audit Log Note</label>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Violation of community rule #3 (Spamming)"
                className="w-full px-3 py-2 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-red-500"
              />
            </div>

            {result && (
              <div
                className={`p-3 rounded-xl border flex items-center gap-2 text-xs ${
                  result.success
                    ? "bg-emerald-950/30 border-emerald-500/30 text-emerald-300"
                    : "bg-red-950/30 border-red-500/30 text-red-300"
                }`}
              >
                {result.success ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
                <span>{result.text}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={executing}
              className="w-full py-3 px-4 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold tracking-wide flex items-center justify-center gap-2 shadow-lg shadow-red-600/25 transition cursor-pointer"
            >
              {executing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Executing Action on Discord Guild...</span>
                </>
              ) : (
                <>
                  <ShieldAlert className="w-4 h-4" />
                  <span>Execute {action.toUpperCase()}</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Audit Log / Safety Panel */}
        <div className="p-6 rounded-2xl glass-card space-y-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">Security Architecture</h3>
          <div className="text-xs text-zinc-400 space-y-3 leading-relaxed">
            <p>
              • All moderation actions are verified against bot permissions and logged to the Discord Audit Log.
            </p>
            <p>
              • You cannot moderate users with higher role hierarchy than Sweety.
            </p>
            <p>
              • Channel locks update <code className="text-purple-300">@everyone</code> permissions without affecting administrative roles.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
