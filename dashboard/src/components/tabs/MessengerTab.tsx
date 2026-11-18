"use client";

import React, { useState, useEffect } from "react";
import { useDashboard } from "@/context/DashboardContext";
import { MessageSquare, Send, Hash, Sparkles, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

export default function MessengerTab() {
  const { backendUrl, token, guilds } = useDashboard();

  const [selectedGuild, setSelectedGuild] = useState<string>("");
  const [channels, setChannels] = useState<any[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>("");
  const [loadingChannels, setLoadingChannels] = useState<boolean>(false);

  const [content, setContent] = useState<string>("");
  const [useEmbed, setUseEmbed] = useState<boolean>(false);
  const [embedTitle, setEmbedTitle] = useState<string>("");
  const [embedDesc, setEmbedDesc] = useState<string>("");
  const [embedColor, setEmbedColor] = useState<string>("#8b5cf6");
  const [embedFooter, setEmbedFooter] = useState<string>("Sent via Sweety AI Command Center");

  const [sending, setSending] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<{ text: string; success: boolean } | null>(null);

  // Auto-select first guild
  useEffect(() => {
    if (guilds.length > 0 && !selectedGuild) {
      setSelectedGuild(guilds[0].id);
    }
  }, [guilds]);

  // Fetch channels when selected guild changes
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
          const channelList: any[] = Array.isArray(data) ? data : (data.channels || []);
          // Filter to text and announcement channels (type 0 or 5 or matching)
          const textChannels = channelList.filter((c: any) => c.type === 0 || c.type === 5 || !c.type || c.type === "text" || c.type === "news");
          const finalChannels = textChannels.length > 0 ? textChannels : channelList;
          setChannels(finalChannels);
          if (finalChannels.length > 0) {
            setSelectedChannel(finalChannels[0].id);
          }
        }
      } catch (err) {
        console.error("Failed to load guild channels:", err);
      } finally {
        setLoadingChannels(false);
      }
    };

    fetchChannels();
  }, [selectedGuild, backendUrl, token]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedGuild || !selectedChannel) {
      setStatusMsg({ text: "Please select a server and channel.", success: false });
      return;
    }

    if (!content.trim() && (!useEmbed || !embedTitle.trim())) {
      setStatusMsg({ text: "Please type a message or provide an embed title.", success: false });
      return;
    }

    setSending(true);
    setStatusMsg(null);

    try {
      const payload: any = {
        guild_id: selectedGuild,
        channel_id: selectedChannel,
        content: content.trim()
      };

      if (useEmbed) {
        payload.embed = {
          title: embedTitle.trim() || undefined,
          description: embedDesc.trim() || undefined,
          color: parseInt(embedColor.replace("#", ""), 16) || 0x8b5cf6,
          footer: embedFooter.trim() || undefined
        };
      }

      const res = await fetch(`${backendUrl}/api/messages/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setStatusMsg({
          text: `Message delivered successfully to #${channels.find(c => c.id === selectedChannel)?.name || selectedChannel}!`,
          success: true
        });
        setContent("");
      } else {
        setStatusMsg({ text: data.detail || "Failed to dispatch message.", success: false });
      }
    } catch {
      setStatusMsg({ text: "Network error sending message to Discord API.", success: false });
    } finally {
      setSending(false);
    }
  };

  const colorPresets = [
    { name: "Purple", hex: "#8b5cf6" },
    { name: "Indigo", hex: "#6366f1" },
    { name: "Emerald", hex: "#10b981" },
    { name: "Pink", hex: "#ec4899" },
    { name: "Amber", hex: "#f59e0b" },
    { name: "Rose", hex: "#f43f5e" }
  ];

  return (
    <div className="space-y-6">
      <div className="p-5 bg-gradient-to-r from-purple-900/20 to-indigo-900/10 rounded-2xl border border-purple-500/20 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-purple-500/15 rounded-xl border border-purple-500/30 text-purple-400">
            <MessageSquare className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-zinc-100">Inter-Server Channel Messenger</h2>
            <p className="text-xs text-zinc-400">
              Dispatch real-time messages and rich stylized embeds into any connected server channel as Sweety.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Form Panel */}
        <div className="lg:col-span-2 p-6 rounded-2xl glass-card space-y-5">
          <form onSubmit={handleSend} className="space-y-5">
            {/* Target Selection Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-zinc-300 block mb-1.5">Target Discord Server</label>
                <select
                  value={selectedGuild}
                  onChange={(e) => setSelectedGuild(e.target.value)}
                  className="w-full px-3 py-2.5 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                >
                  {guilds.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-zinc-300 block mb-1.5">
                  Target Channel {loadingChannels && "(Loading...)"}
                </label>
                <select
                  value={selectedChannel}
                  onChange={(e) => setSelectedChannel(e.target.value)}
                  disabled={loadingChannels || channels.length === 0}
                  className="w-full px-3 py-2.5 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500 disabled:opacity-50"
                >
                  {channels.map((c) => (
                    <option key={c.id} value={c.id}>
                      #{c.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Message Body */}
            <div>
              <label className="text-xs font-semibold text-zinc-300 block mb-1.5">
                Message Content (Supports standard Markdown & Emojis)
              </label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Type your message from Sweety..."
                rows={3}
                className="w-full p-3.5 bg-zinc-900/80 rounded-xl border border-zinc-800 text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-purple-500 resize-none"
              />
            </div>

            {/* Rich Embed Toggle */}
            <div className="pt-2 border-t border-zinc-800/60">
              <label className="flex items-center gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={useEmbed}
                  onChange={(e) => setUseEmbed(e.target.checked)}
                  className="rounded text-purple-600 focus:ring-0 bg-zinc-900 border-zinc-700 h-4 w-4"
                />
                <span className="text-xs font-semibold text-purple-300 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" /> Attach Rich Stylized Embed Card
                </span>
              </label>
            </div>

            {/* Rich Embed Fields */}
            {useEmbed && (
              <div className="p-4 bg-zinc-950/60 rounded-xl border border-purple-500/20 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Embed Title</label>
                    <input
                      type="text"
                      value={embedTitle}
                      onChange={(e) => setEmbedTitle(e.target.value)}
                      placeholder="e.g. Official Server Announcement"
                      className="w-full px-3 py-2 bg-zinc-900 rounded-lg border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Footer Note</label>
                    <input
                      type="text"
                      value={embedFooter}
                      onChange={(e) => setEmbedFooter(e.target.value)}
                      placeholder="Footer note text"
                      className="w-full px-3 py-2 bg-zinc-900 rounded-lg border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 block mb-1">Embed Description Body</label>
                  <textarea
                    value={embedDesc}
                    onChange={(e) => setEmbedDesc(e.target.value)}
                    placeholder="Extended markdown embed content..."
                    rows={3}
                    className="w-full p-2.5 bg-zinc-900 rounded-lg border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-purple-500 resize-none"
                  />
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 block mb-1.5">Accent Color Bar</label>
                  <div className="flex flex-wrap items-center gap-2">
                    {colorPresets.map((c) => (
                      <button
                        type="button"
                        key={c.hex}
                        onClick={() => setEmbedColor(c.hex)}
                        className={`px-2.5 py-1 rounded-md text-[10px] font-semibold flex items-center gap-1.5 border transition ${
                          embedColor === c.hex ? "border-white text-white" : "border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        }`}
                      >
                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: c.hex }} />
                        {c.name}
                      </button>
                    ))}
                    <input
                      type="text"
                      value={embedColor}
                      onChange={(e) => setEmbedColor(e.target.value)}
                      className="w-20 px-2 py-1 bg-zinc-900 border border-zinc-800 rounded text-[11px] text-zinc-300 font-mono"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Status Alert */}
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

            {/* Submit Button */}
            <button
              type="submit"
              disabled={sending}
              className="w-full py-3 px-4 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold tracking-wide flex items-center justify-center gap-2 shadow-lg shadow-purple-600/25 transition cursor-pointer"
            >
              {sending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Transmitting to Discord Gateway...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Send Message as Sweety</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Live Preview Panel */}
        <div className="p-6 rounded-2xl glass-card space-y-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">Live Discord Client Preview</h3>
          <div className="p-4 bg-[#313338] rounded-xl text-zinc-200 space-y-3 font-sans">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-purple-600 flex items-center justify-center text-white font-bold text-sm">
                S
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-xs text-white">Sweety</span>
                  <span className="px-1 py-0.2 bg-[#5865F2] text-[9px] font-bold text-white rounded">BOT</span>
                  <span className="text-[10px] text-zinc-400">Today at {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
              </div>
            </div>

            {content && <p className="text-xs text-zinc-200 whitespace-pre-wrap pl-12">{content}</p>}

            {useEmbed && (
              <div
                className="ml-12 p-3 bg-[#2b2d31] rounded border-l-4 text-xs space-y-1.5"
                style={{ borderLeftColor: embedColor }}
              >
                {embedTitle && <h4 className="font-bold text-white text-xs">{embedTitle}</h4>}
                {embedDesc && <p className="text-zinc-300 text-[11px] whitespace-pre-wrap">{embedDesc}</p>}
                {embedFooter && <span className="text-[10px] text-zinc-400 block pt-1 border-t border-zinc-700/50">{embedFooter}</span>}
              </div>
            )}

            {!content && !useEmbed && (
              <p className="text-xs text-zinc-500 italic pl-12">Message preview will appear here as you type...</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
