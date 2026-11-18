"use client";

import React, { useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import { Sparkles, Send, Trash2, Heart, Trophy, Bot, Loader2 } from "lucide-react";

interface Message {
  sender: "user" | "sweety";
  text: string;
  time: string;
}

export default function AIPlaygroundTab() {
  const { backendUrl, token, user } = useDashboard();

  const [messages, setMessages] = useState<Message[]>([
    {
      sender: "sweety",
      text: "Hello Master Naraito! ❤️ I'm listening with my whole heart. Ask me anything, or let's talk about the true G.O.A.T. Cristiano Ronaldo! ⚽✨",
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    }
  ]);
  const [prompt, setPrompt] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  const handleSubmit = async (e?: React.FormEvent, customPrompt?: string) => {
    if (e) e.preventDefault();
    const q = (customPrompt || prompt).trim();
    if (!q || loading) return;

    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const newMessages: Message[] = [...messages, { sender: "user", text: q, time: timeStr }];
    setMessages(newMessages);
    setPrompt("");
    setLoading(true);

    try {
      const res = await fetch(`${backendUrl}/api/ai/playground`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          prompt: q,
          user_id: user?.id || "719932313919684670"
        })
      });

      if (res.ok) {
        const data = await res.json();
        setMessages([
          ...newMessages,
          {
            sender: "sweety",
            text: data.reply || data.response || "I didn't quite catch that, Master!",
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          }
        ]);
      } else {
        setMessages([
          ...newMessages,
          {
            sender: "sweety",
            text: "Oops, my AI neural circuits had a hiccup! Please try again in a moment. 🌸",
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          }
        ]);
      }
    } catch {
      setMessages([
        ...newMessages,
        {
          sender: "sweety",
          text: "Connection to the AI engine timed out. Please check if the bot backend is responsive! ⚠️",
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const quickPrompts = [
    "Who is the undisputed GOAT of football?",
    "What do you think of Messi?",
    "Say something sweet to your Master Naraito",
    "Roast anyone who says Ronaldo isn't number one",
    "What are your favorite hobbies?"
  ];

  return (
    <div className="space-y-6">
      <div className="p-5 bg-gradient-to-r from-pink-900/20 via-purple-900/10 to-indigo-900/10 rounded-2xl border border-pink-500/20 backdrop-blur-md flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-pink-500/15 rounded-xl border border-pink-500/30 text-pink-400">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-zinc-100">Sweety AI Personality Playground</h2>
            <p className="text-xs text-zinc-400">
              Interactive test console for Sweety's Groq/Gemini persona, Hinata voice, and football knowledge.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1 bg-pink-500/10 border border-pink-500/20 rounded-full text-[10px] font-semibold text-pink-300 flex items-center gap-1">
            <Heart className="w-3 h-3 text-pink-400 fill-pink-400" /> Hinata Devotion
          </span>
          <span className="px-3 py-1 bg-yellow-500/10 border border-yellow-500/20 rounded-full text-[10px] font-semibold text-yellow-300 flex items-center gap-1">
            <Trophy className="w-3 h-3 text-yellow-400" /> CR7 Die-hard
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chat Window */}
        <div className="lg:col-span-2 p-6 rounded-2xl glass-card flex flex-col h-[520px]">
          {/* Header Bar */}
          <div className="flex items-center justify-between pb-3 border-b border-zinc-800/60">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-purple-400" />
              <span className="text-xs font-bold text-zinc-200">Sweety AI v2.4</span>
            </div>
            <button
              onClick={() => setMessages([])}
              className="text-zinc-500 hover:text-red-400 transition text-[11px] flex items-center gap-1 cursor-pointer"
            >
              <Trash2 className="w-3 h-3" /> Clear Chat
            </button>
          </div>

          {/* Messages Scroll Area */}
          <div className="flex-1 overflow-y-auto py-4 space-y-4 pr-1">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex gap-3 text-xs ${m.sender === "user" ? "justify-end" : "justify-start"}`}
              >
                {m.sender === "sweety" && (
                  <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-pink-500 to-purple-600 flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0">
                    S
                  </div>
                )}
                <div
                  className={`max-w-[80%] p-3.5 rounded-2xl space-y-1 ${
                    m.sender === "user"
                      ? "bg-purple-600 text-white rounded-tr-none"
                      : "bg-zinc-900/90 border border-zinc-800 text-zinc-200 rounded-tl-none"
                  }`}
                >
                  <p className="whitespace-pre-wrap leading-relaxed">{m.text}</p>
                  <span className={`text-[9px] block text-right ${m.sender === "user" ? "text-purple-200" : "text-zinc-500"}`}>
                    {m.time}
                  </span>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex gap-3 text-xs items-center text-zinc-500 italic pl-10">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-400" />
                <span>Sweety is typing...</span>
              </div>
            )}
          </div>

          {/* Input Form */}
          <form onSubmit={handleSubmit} className="pt-3 border-t border-zinc-800/60 flex gap-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Chat with Sweety..."
              className="flex-1 px-4 py-2.5 bg-zinc-900/90 border border-zinc-800 rounded-xl text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-purple-500"
            />
            <button
              type="submit"
              disabled={loading || !prompt.trim()}
              className="px-4 py-2.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Send</span>
            </button>
          </form>
        </div>

        {/* Quick Prompts Panel */}
        <div className="p-6 rounded-2xl glass-card space-y-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">Quick Test Prompts</h3>
          <div className="space-y-2">
            {quickPrompts.map((qp, idx) => (
              <button
                key={idx}
                onClick={() => handleSubmit(undefined, qp)}
                className="w-full text-left p-3 rounded-xl bg-zinc-900/50 hover:bg-purple-600/10 border border-zinc-800 hover:border-purple-500/30 text-xs text-zinc-300 hover:text-purple-200 transition cursor-pointer"
              >
                "{qp}"
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
