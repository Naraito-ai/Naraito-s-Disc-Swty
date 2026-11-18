"use client";

import React, { useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import { Megaphone, Send, User, Users, ShieldAlert, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

export default function AnnouncementsTab() {
  const { backendUrl, token, guilds } = useDashboard();

  const [targetType, setTargetType] = useState<"user" | "guild">("user");
  const [targetUserId, setTargetUserId] = useState<string>("");
  const [selectedGuild, setSelectedGuild] = useState<string>(guilds[0]?.id || "");
  const [title, setTitle] = useState<string>("");
  const [message, setMessage] = useState<string>("");

  const [sending, setSending] = useState<boolean>(false);
  const [result, setResult] = useState<{ text: string; success: boolean } | null>(null);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) {
      setResult({ text: "Please enter an announcement message.", success: false });
      return;
    }

    if (targetType === "user" && !targetUserId.trim()) {
      setResult({ text: "Please provide a recipient Discord User ID.", success: false });
      return;
    }

    if (targetType === "guild" && !selectedGuild) {
      setResult({ text: "Please select a target server.", success: false });
      return;
    }

    setSending(true);
    setResult(null);

    try {
      const payload: any = {
        target_type: targetType,
        content: message.trim(),
        title: title.trim() || undefined
      };

      if (targetType === "user") {
        payload.target_id = targetUserId.trim();
        payload.user_id = targetUserId.trim();
      } else {
        payload.guild_id = selectedGuild;
        payload.target_id = selectedGuild;
      }

      const res = await fetch(`${backendUrl}/api/announcements/dm`, {
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
          text: data.message || `Announcement delivered to ${data.sent_count || 1} recipient(s)!`,
          success: true
        });
        setMessage("");
      } else {
        setResult({ text: data.detail || "Failed to transmit announcement.", success: false });
      }
    } catch {
      setResult({ text: "Network error connecting to backend API.", success: false });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="p-5 bg-gradient-to-r from-amber-900/20 to-purple-900/10 rounded-2xl border border-amber-500/20 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-amber-500/15 rounded-xl border border-amber-500/30 text-amber-400">
            <Megaphone className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-zinc-100">Direct Message Announcements & Broadcast</h2>
            <p className="text-xs text-zinc-400">
              Transmit official announcements directly into Discord user inboxes with rate-limit protection.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 p-6 rounded-2xl glass-card space-y-5">
          {/* Target Type Selector */}
          <div>
            <label className="text-xs font-semibold text-zinc-300 block mb-2">Announcement Scope</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setTargetType("user")}
                className={`p-3.5 rounded-xl border text-left flex items-center gap-3 transition cursor-pointer ${
                  targetType === "user"
                    ? "bg-purple-600/15 border-purple-500/40 text-purple-300"
                    : "bg-zinc-900/40 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <User className="h-5 w-5 flex-shrink-0" />
                <div>
                  <span className="text-xs font-bold block">Single User DM</span>
                  <span className="text-[10px] text-zinc-500">Deliver directly to one user</span>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setTargetType("guild")}
                className={`p-3.5 rounded-xl border text-left flex items-center gap-3 transition cursor-pointer ${
                  targetType === "guild"
                    ? "bg-purple-600/15 border-purple-500/40 text-purple-300"
                    : "bg-zinc-900/40 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <Users className="h-5 w-5 flex-shrink-0" />
                <div>
                  <span className="text-xs font-bold block">Server Broadcast</span>
                  <span className="text-[10px] text-zinc-500">DM all server members</span>
                </div>
              </button>
            </div>
          </div>

          <form onSubmit={handleSend} className="space-y-4">
            {targetType === "user" ? (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-zinc-300">Target Discord User ID</label>
                  <button
                    type="button"
                    onClick={() => setTargetUserId("719932313919684670")}
                    className="text-[10px] text-purple-400 hover:text-purple-300 font-semibold"
                  >
                    👑 Set to Master Naraito
                  </button>
                </div>
                <input
                  type="text"
                  value={targetUserId}
                  onChange={(e) => setTargetUserId(e.target.value)}
                  placeholder="e.g. 719932313919684670"
                  className="w-full px-3 py-2.5 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500 font-mono"
                />
              </div>
            ) : (
              <div>
                <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Target Discord Server</label>
                <select
                  value={selectedGuild}
                  onChange={(e) => setSelectedGuild(e.target.value)}
                  className="w-full px-3 py-2.5 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                >
                  {guilds.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name} ({g.members || 0} members)
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div>
              <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Announcement Title (Optional)</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Urgent Community Notice"
                className="w-full px-3 py-2 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Announcement Message</label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Write your announcement body..."
                rows={4}
                className="w-full p-3 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-purple-500 resize-none"
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
              disabled={sending}
              className="w-full py-3 px-4 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold tracking-wide flex items-center justify-center gap-2 shadow-lg shadow-amber-600/25 transition cursor-pointer"
            >
              {sending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Dispatching Direct Messages...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>{targetType === "user" ? "Send Direct Message" : "Broadcast to Server Members"}</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Safety & Info Card */}
        <div className="p-6 rounded-2xl glass-card space-y-4">
          <div className="flex items-center gap-2 text-amber-400">
            <ShieldAlert className="w-4 h-4" />
            <h3 className="text-xs font-bold uppercase tracking-wider">Safety & Anti-Abuse Guards</h3>
          </div>
          <div className="text-xs text-zinc-400 space-y-3 leading-relaxed">
            <p>
              • Single user DMs are sent instantly through Discord Gateway.
            </p>
            <p>
              • Server broadcasts are metered with a safety delay between each member to prevent Discord Bot API rate limits.
            </p>
            <p>
              • If a member has server DMs disabled, Sweety will gracefully skip them without throwing an error.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
