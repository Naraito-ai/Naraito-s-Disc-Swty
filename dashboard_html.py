"""
Sweety Web Dashboard — Single-Page Application Template
High-fidelity dark glassmorphic control center for Sweety Discord Bot.
"""

def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sweety AI — Bot Command Center & Web Dashboard</title>
  <link rel="icon" type="image/png" href="https://cdn.discordapp.com/emojis/1154407886915784744.webp?size=96&quality=lossless">
  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Lucide Icons CDN -->
  <script src="https://unpkg.com/lucide@latest"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#f5f3ff',
              100: '#ede9fe',
              400: '#a78bfa',
              500: '#8b5cf6',
              600: '#7c3aed',
              700: '#6d28d9',
            },
            carbon: {
              900: '#07070a',
              800: '#0d0d12',
              700: '#14141d',
              600: '#1d1d2b',
              500: '#2a2a3d',
            }
          },
          fontFamily: {
            sans: ['Plus Jakarta Sans', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace'],
          }
        }
      }
    }
  </script>
  <style>
    body {
      background-color: #07070a;
      background-image: 
        radial-gradient(at 0% 0%, rgba(124, 58, 237, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(14, 165, 233, 0.08) 0px, transparent 50%),
        radial-gradient(at 50% 100%, rgba(236, 72, 153, 0.06) 0px, transparent 50%);
      background-attachment: fixed;
    }
    .glass-panel {
      background: rgba(13, 13, 18, 0.7);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.07);
    }
    .glass-panel-elevated {
      background: rgba(20, 20, 29, 0.85);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .discord-embed-preview {
      background: #2b2d31;
      border-radius: 4px;
      border-left-width: 4px;
    }
    /* Custom Scrollbar */
    ::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    ::-webkit-scrollbar-track {
      background: #0d0d12;
    }
    ::-webkit-scrollbar-thumb {
      background: #272738;
      border-radius: 9999px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: #7c3aed;
    }
    @keyframes pulse-slow {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(0.97); }
    }
    .animate-pulse-slow {
      animation: pulse-slow 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
    .equalizer-bar {
      display: inline-block;
      width: 3px;
      background: #a78bfa;
      border-radius: 3px;
      animation: bounce 1.2s ease infinite alternate;
    }
    @keyframes bounce {
      10% { height: 6px; }
      100% { height: 22px; }
    }
    .eq-1 { animation-delay: 0.1s; }
    .eq-2 { animation-delay: 0.4s; }
    .eq-3 { animation-delay: 0.2s; }
    .eq-4 { animation-delay: 0.6s; }
  </style>
</head>
<body class="min-h-screen text-zinc-100 flex flex-col font-sans antialiased selection:bg-brand-500 selection:text-white">

  <!-- TOP APP BAR -->
  <header class="sticky top-0 z-50 glass-panel border-b border-zinc-800/80 px-4 lg:px-8 py-3 flex items-center justify-between">
    <!-- Brand Info -->
    <div class="flex items-center gap-3">
      <div class="relative">
        <div class="w-10 h-10 rounded-2xl bg-gradient-to-tr from-brand-600 to-pink-500 flex items-center justify-center shadow-lg shadow-brand-600/30 overflow-hidden border border-white/20">
          <img id="bot-avatar" src="https://cdn.discordapp.com/emojis/1154407886915784744.webp?size=96&quality=lossless" alt="Sweety" class="w-full h-full object-cover">
        </div>
        <span id="gateway-dot" class="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 bg-emerald-500 rounded-full border-2 border-carbon-900 ring-2 ring-emerald-500/20"></span>
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-base font-bold tracking-tight text-white flex items-center gap-1.5">
            Sweety <span class="text-xs px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-400 font-semibold border border-brand-500/30">AI 2.5</span>
          </h1>
          <span class="hidden sm:inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Online
          </span>
        </div>
        <p class="text-xs text-zinc-400 flex items-center gap-2 font-mono">
          <span id="header-latency">Ping: -- ms</span> • <span id="header-uptime">Uptime: --</span>
        </p>
      </div>
    </div>

    <!-- Center Quick Navigation Tabs (Desktop) -->
    <nav class="hidden xl:flex items-center gap-1 p-1 bg-carbon-800/80 rounded-xl border border-zinc-800/70">
      <button onclick="switchTab('overview')" data-tab="overview" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-white bg-brand-600 shadow">
        <i data-lucide="activity" class="w-3.5 h-3.5"></i> Telemetry
      </button>
      <button onclick="switchTab('messenger')" data-tab="messenger" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60">
        <i data-lucide="send" class="w-3.5 h-3.5"></i> Server Message
      </button>
      <button onclick="switchTab('announcements')" data-tab="announcements" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60">
        <i data-lucide="mail" class="w-3.5 h-3.5"></i> Direct Messages
      </button>
      <button onclick="switchTab('moderation')" data-tab="moderation" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60">
        <i data-lucide="shield" class="w-3.5 h-3.5"></i> Moderation
      </button>
      <button onclick="switchTab('ai')" data-tab="ai" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60">
        <i data-lucide="sparkles" class="w-3.5 h-3.5 text-pink-400"></i> AI Playground
      </button>
      <button onclick="switchTab('music')" data-tab="music" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60">
        <i data-lucide="music" class="w-3.5 h-3.5 text-indigo-400"></i> Music Station
      </button>
      <button onclick="switchTab('servers')" data-tab="servers" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60">
        <i data-lucide="server" class="w-3.5 h-3.5"></i> Servers
      </button>
      <button onclick="switchTab('console')" data-tab="console" class="tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60">
        <i data-lucide="terminal" class="w-3.5 h-3.5"></i> Console
      </button>
    </nav>

    <!-- Right Controls & Master Auth -->
    <div class="flex items-center gap-2 sm:gap-3">
      <!-- Quick Status Refresh Button -->
      <button onclick="fetchBotStats(true)" title="Force Refresh Data" class="p-2 text-zinc-400 hover:text-white hover:bg-zinc-800/70 rounded-xl border border-zinc-800/60 transition cursor-pointer">
        <i data-lucide="refresh-cw" id="refresh-icon" class="w-4 h-4"></i>
      </button>

      <!-- Auth State Badge -->
      <div id="auth-status-container">
        <button onclick="openAuthModal()" class="px-3 py-1.5 text-xs font-semibold rounded-xl bg-brand-600 hover:bg-brand-500 text-white transition flex items-center gap-1.5 shadow-lg shadow-brand-600/20">
          <i data-lucide="key" class="w-3.5 h-3.5"></i> Master Connect
        </button>
      </div>

      <!-- Mobile Menu Toggle Button -->
      <button onclick="toggleMobileMenu()" class="xl:hidden p-2 text-zinc-400 hover:text-white hover:bg-zinc-800/70 rounded-xl border border-zinc-800/60">
        <i data-lucide="menu" class="w-5 h-5"></i>
      </button>
    </div>
  </header>

  <!-- MOBILE NAVIGATION DRAWER -->
  <div id="mobile-menu" class="xl:hidden hidden glass-panel border-b border-zinc-800/80 px-4 py-3 space-y-1">
    <div class="grid grid-cols-2 gap-1.5 text-xs">
      <button onclick="switchTab('overview'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="activity" class="w-4 h-4 text-brand-400"></i> Telemetry
      </button>
      <button onclick="switchTab('messenger'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="send" class="w-4 h-4 text-emerald-400"></i> Server Message
      </button>
      <button onclick="switchTab('announcements'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="mail" class="w-4 h-4 text-sky-400"></i> Direct Messages
      </button>
      <button onclick="switchTab('moderation'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="shield" class="w-4 h-4 text-red-400"></i> Moderation
      </button>
      <button onclick="switchTab('ai'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="sparkles" class="w-4 h-4 text-pink-400"></i> AI Playground
      </button>
      <button onclick="switchTab('music'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="music" class="w-4 h-4 text-indigo-400"></i> Music Station
      </button>
      <button onclick="switchTab('servers'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="server" class="w-4 h-4 text-amber-400"></i> Servers
      </button>
      <button onclick="switchTab('console'); toggleMobileMenu()" class="p-2 rounded-lg text-left flex items-center gap-2 hover:bg-zinc-800/60 text-zinc-200">
        <i data-lucide="terminal" class="w-4 h-4 text-emerald-400"></i> Console
      </button>
    </div>
  </div>

  <!-- TOAST NOTIFICATION CONTAINER -->
  <div id="toast-container" class="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none"></div>

  <!-- MAIN VIEWPORT CONTAINER -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 1: TELEMETRY & SYSTEM OVERVIEW
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-overview" class="space-y-6">
      <!-- Welcome Hero Banner -->
      <div class="glass-panel rounded-2xl p-6 relative overflow-hidden border border-brand-500/20 bg-gradient-to-r from-brand-950/40 via-carbon-800/60 to-carbon-900/80">
        <div class="absolute -right-10 -bottom-10 w-60 h-60 bg-brand-500/10 rounded-full blur-3xl pointer-events-none"></div>
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
          <div>
            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-brand-500/10 text-brand-300 text-xs font-semibold border border-brand-500/20 mb-2">
              <i data-lucide="crown" class="w-3.5 h-3.5 text-amber-400"></i> Master Naraito Control Suite
            </span>
            <h2 class="text-2xl font-extrabold text-white tracking-tight">Sweety Bot Telemetry & Command Center</h2>
            <p class="text-sm text-zinc-400 mt-1 max-w-2xl">
              Real-time monitoring, inter-server communications, direct message announcements, and one-click moderation controls for Sweety.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2.5">
            <button onclick="switchTab('messenger')" class="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold transition flex items-center gap-2 shadow-lg shadow-brand-600/30">
              <i data-lucide="send" class="w-4 h-4"></i> Send Message
            </button>
            <button onclick="switchTab('moderation')" class="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold transition flex items-center gap-2 border border-zinc-700">
              <i data-lucide="shield" class="w-4 h-4 text-red-400"></i> Quick Mod
            </button>
            <button onclick="triggerGlobalSync()" class="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold transition flex items-center gap-2 border border-zinc-700" title="Resync Discord Slash Commands">
              <i data-lucide="zap" class="w-4 h-4 text-amber-400"></i> Sync Commands
            </button>
          </div>
        </div>
      </div>

      <!-- Live Metric Cards Grid -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
        <!-- Latency -->
        <div class="glass-panel rounded-2xl p-4 flex flex-col justify-between hover:border-brand-500/30 transition">
          <div class="flex items-center justify-between text-zinc-400 mb-2">
            <span class="text-xs font-medium uppercase tracking-wider">Gateway Ping</span>
            <i data-lucide="wifi" class="w-4 h-4 text-emerald-400"></i>
          </div>
          <div class="flex items-baseline gap-1.5">
            <span id="metric-latency" class="text-2xl font-extrabold text-white">--</span>
            <span class="text-xs text-zinc-500">ms</span>
          </div>
          <span class="text-[11px] text-emerald-400 mt-1 flex items-center gap-1">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> WebSocket Live
          </span>
        </div>

        <!-- Uptime -->
        <div class="glass-panel rounded-2xl p-4 flex flex-col justify-between hover:border-brand-500/30 transition">
          <div class="flex items-center justify-between text-zinc-400 mb-2">
            <span class="text-xs font-medium uppercase tracking-wider">Bot Uptime</span>
            <i data-lucide="clock" class="w-4 h-4 text-brand-400"></i>
          </div>
          <div class="flex items-baseline gap-1.5">
            <span id="metric-uptime" class="text-xl font-bold text-white truncate">--</span>
          </div>
          <span class="text-[11px] text-zinc-500 mt-1">Continuous uptime</span>
        </div>

        <!-- Connected Guilds -->
        <div class="glass-panel rounded-2xl p-4 flex flex-col justify-between hover:border-brand-500/30 transition">
          <div class="flex items-center justify-between text-zinc-400 mb-2">
            <span class="text-xs font-medium uppercase tracking-wider">Servers</span>
            <i data-lucide="server" class="w-4 h-4 text-sky-400"></i>
          </div>
          <div class="flex items-baseline gap-1.5">
            <span id="metric-guilds" class="text-2xl font-extrabold text-white">--</span>
          </div>
          <span class="text-[11px] text-sky-400 mt-1">Connected Guilds</span>
        </div>

        <!-- Total Users Reached -->
        <div class="glass-panel rounded-2xl p-4 flex flex-col justify-between hover:border-brand-500/30 transition">
          <div class="flex items-center justify-between text-zinc-400 mb-2">
            <span class="text-xs font-medium uppercase tracking-wider">Audience</span>
            <i data-lucide="users" class="w-4 h-4 text-indigo-400"></i>
          </div>
          <div class="flex items-baseline gap-1.5">
            <span id="metric-members" class="text-2xl font-extrabold text-white">--</span>
          </div>
          <span class="text-[11px] text-zinc-500 mt-1">Total Users</span>
        </div>

        <!-- AI Requests -->
        <div class="glass-panel rounded-2xl p-4 flex flex-col justify-between hover:border-brand-500/30 transition">
          <div class="flex items-center justify-between text-zinc-400 mb-2">
            <span class="text-xs font-medium uppercase tracking-wider">AI Queries</span>
            <i data-lucide="sparkles" class="w-4 h-4 text-pink-400"></i>
          </div>
          <div class="flex items-baseline gap-1.5">
            <span id="metric-ai-reqs" class="text-2xl font-extrabold text-white">--</span>
          </div>
          <span class="text-[11px] text-pink-400 mt-1">Gemini & Groq</span>
        </div>

        <!-- Active Voice / Music -->
        <div class="glass-panel rounded-2xl p-4 flex flex-col justify-between hover:border-brand-500/30 transition">
          <div class="flex items-center justify-between text-zinc-400 mb-2">
            <span class="text-xs font-medium uppercase tracking-wider">Active VC</span>
            <i data-lucide="headphones" class="w-4 h-4 text-amber-400"></i>
          </div>
          <div class="flex items-baseline gap-1.5">
            <span id="metric-voice" class="text-2xl font-extrabold text-white">--</span>
          </div>
          <span class="text-[11px] text-amber-400 mt-1">Voice Streams</span>
        </div>
      </div>

      <!-- Resource Utilization & Live Music Snapshot -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <!-- System Hardware Gauges -->
        <div class="glass-panel rounded-2xl p-5 space-y-4">
          <h3 class="text-sm font-semibold text-white flex items-center gap-2">
            <i data-lucide="cpu" class="w-4 h-4 text-brand-400"></i> Container Health & Resources
          </h3>
          <div class="space-y-3.5">
            <div>
              <div class="flex justify-between text-xs text-zinc-400 mb-1">
                <span>CPU Load</span>
                <span id="cpu-percent" class="font-mono text-white font-semibold">--%</span>
              </div>
              <div class="w-full bg-zinc-800 rounded-full h-2 overflow-hidden">
                <div id="cpu-bar" class="bg-gradient-to-r from-brand-500 to-indigo-500 h-2 rounded-full transition-all duration-500" style="width: 15%"></div>
              </div>
            </div>
            <div>
              <div class="flex justify-between text-xs text-zinc-400 mb-1">
                <span>RAM Usage</span>
                <span id="ram-percent" class="font-mono text-white font-semibold">--%</span>
              </div>
              <div class="w-full bg-zinc-800 rounded-full h-2 overflow-hidden">
                <div id="ram-bar" class="bg-gradient-to-r from-emerald-500 to-sky-500 h-2 rounded-full transition-all duration-500" style="width: 35%"></div>
              </div>
            </div>
          </div>
          <div class="pt-2 border-t border-zinc-800/80 flex items-center justify-between text-xs text-zinc-400 font-mono">
            <span>RAM Used: <strong id="ram-used" class="text-zinc-200">-- MB</strong></span>
            <span>OS: <strong class="text-zinc-200">Linux / Render</strong></span>
          </div>
        </div>

        <!-- Live Music Stream Mini-Player -->
        <div class="glass-panel rounded-2xl p-5 lg:col-span-2 flex flex-col justify-between">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-white flex items-center gap-2">
              <i data-lucide="radio" class="w-4 h-4 text-pink-400"></i> Active Music Player Status
            </h3>
            <span id="music-indicator" class="text-xs px-2.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400 font-medium">Idle</span>
          </div>

          <div id="overview-music-content" class="bg-carbon-800/80 rounded-xl p-4 border border-zinc-800/80 flex flex-col sm:flex-row items-center gap-4">
            <div class="w-16 h-16 rounded-xl bg-zinc-800 flex items-center justify-center shrink-0 border border-zinc-700/50 overflow-hidden">
              <img id="nowplaying-thumb" src="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=150&q=80" alt="Track" class="w-full h-full object-cover">
            </div>
            <div class="flex-1 min-w-0 text-center sm:text-left">
              <h4 id="nowplaying-title" class="text-sm font-bold text-white truncate">No music actively playing in any server</h4>
              <p id="nowplaying-sub" class="text-xs text-zinc-400 mt-0.5">Use /play &lt;song&gt; in any Discord voice channel</p>
              <div class="flex items-center justify-center sm:justify-start gap-3 mt-2 text-xs text-zinc-500 font-mono">
                <span id="nowplaying-guild">Server: None</span> • <span id="nowplaying-vc">VC: None</span>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button onclick="switchTab('music')" class="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium transition flex items-center gap-1.5">
                <i data-lucide="sliders" class="w-3.5 h-3.5"></i> Open Music Station
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between text-xs text-zinc-400 mt-3 pt-2 border-t border-zinc-800/60">
            <span>24/7 High-Fidelity Audio Engine</span>
            <span class="flex items-center gap-1">
              <span class="equalizer-bar eq-1"></span>
              <span class="equalizer-bar eq-2"></span>
              <span class="equalizer-bar eq-3"></span>
              <span class="equalizer-bar eq-4"></span>
              <span class="ml-1 text-zinc-400 font-mono">384kbps DSP</span>
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 2: SERVER MESSENGER & DISCORD EMBED BUILDER
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-messenger" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            <i data-lucide="send" class="w-5 h-5 text-brand-400"></i> Speak as Sweety — Channel Messenger
          </h2>
          <p class="text-xs text-zinc-400 mt-0.5">Send custom chat messages or beautifully formatted Discord Rich Embeds directly from Sweety.</p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Message Composer Form (Left 7 Cols) -->
        <div class="lg:col-span-7 glass-panel rounded-2xl p-6 space-y-5">
          <!-- Server & Channel Selectors -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Target Server</label>
              <select id="msg-guild-select" onchange="loadGuildChannels(this.value, 'msg-channel-select')" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
                <option value="">Select a Discord Server...</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Target Channel</label>
              <select id="msg-channel-select" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
                <option value="">Select Channel...</option>
              </select>
            </div>
          </div>

          <!-- Plain Text / Content -->
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400">Message Content (Markdown)</label>
              <span class="text-[11px] text-zinc-500">Supports standard Discord bold, italic, lists</span>
            </div>
            <textarea id="msg-content" rows="3" oninput="updateEmbedPreview()" placeholder="Type what you want Sweety to say in the channel..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl p-3 text-xs text-zinc-100 focus:outline-none focus:border-brand-500 resize-y font-sans"></textarea>
          </div>

          <!-- Embed Details Accordion Toggle -->
          <div class="border-t border-zinc-800/80 pt-4 space-y-4">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <input type="checkbox" id="enable-embed-toggle" onchange="toggleEmbedFields()" class="rounded bg-zinc-800 border-zinc-700 text-brand-600 focus:ring-0">
                <label for="enable-embed-toggle" class="text-xs font-bold text-white cursor-pointer select-none">
                  Attach Discord Rich Embed
                </label>
              </div>
              <span class="text-[11px] text-brand-400 font-medium">Card Layout Preview &rarr;</span>
            </div>

            <!-- Embed Field Inputs (Collapsible) -->
            <div id="embed-fields-container" class="hidden space-y-3.5 bg-carbon-800/40 p-4 rounded-xl border border-zinc-800/80">
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div class="sm:col-span-2">
                  <label class="block text-[11px] text-zinc-400 mb-1">Embed Title</label>
                  <input type="text" id="embed-title" oninput="updateEmbedPreview()" placeholder="Official Server Announcement" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-lg px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
                </div>
                <div>
                  <label class="block text-[11px] text-zinc-400 mb-1">Accent Color</label>
                  <div class="flex items-center gap-2">
                    <input type="color" id="embed-color" value="#8b5cf6" oninput="updateEmbedPreview()" class="w-8 h-8 rounded border-0 bg-transparent cursor-pointer">
                    <input type="text" id="embed-color-hex" value="#8B5CF6" onchange="document.getElementById('embed-color').value = this.value; updateEmbedPreview()" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-lg px-2 py-1.5 text-xs text-zinc-300 font-mono uppercase">
                  </div>
                </div>
              </div>

              <div>
                <label class="block text-[11px] text-zinc-400 mb-1">Embed Description Body</label>
                <textarea id="embed-desc" rows="3" oninput="updateEmbedPreview()" placeholder="Write the main body of the rich card..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-lg p-2.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500"></textarea>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label class="block text-[11px] text-zinc-400 mb-1">Thumbnail URL (Top Right)</label>
                  <input type="url" id="embed-thumb" oninput="updateEmbedPreview()" placeholder="https://..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-lg px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
                </div>
                <div>
                  <label class="block text-[11px] text-zinc-400 mb-1">Large Banner Image URL</label>
                  <input type="url" id="embed-image" oninput="updateEmbedPreview()" placeholder="https://..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-lg px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label class="block text-[11px] text-zinc-400 mb-1">Author Line</label>
                  <input type="text" id="embed-author" oninput="updateEmbedPreview()" placeholder="Sweety Announcements" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-lg px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
                </div>
                <div>
                  <label class="block text-[11px] text-zinc-400 mb-1">Footer Text</label>
                  <input type="text" id="embed-footer" oninput="updateEmbedPreview()" placeholder="Official Notice • Powered by Sweety" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-lg px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
                </div>
              </div>
            </div>
          </div>

          <!-- Send Action Bar -->
          <div class="flex items-center justify-between pt-2">
            <span id="send-msg-status" class="text-xs text-zinc-400"></span>
            <button onclick="sendMessageToChannel()" id="btn-send-message" class="px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs transition flex items-center gap-2 shadow-lg shadow-brand-600/30">
              <i data-lucide="send" class="w-4 h-4"></i> Dispatch Message as Sweety
            </button>
          </div>
        </div>

        <!-- Live Discord Embed Preview (Right 5 Cols) -->
        <div class="lg:col-span-5 glass-panel rounded-2xl p-6 space-y-4 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
                <i data-lucide="eye" class="w-4 h-4 text-brand-400"></i> Discord Live Preview
              </span>
              <span class="text-[11px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">What users see</span>
            </div>

            <!-- Discord Mock Container -->
            <div class="bg-[#313338] p-4 rounded-xl border border-zinc-700/40 text-sm space-y-3">
              <!-- Bot Header in Chat -->
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-brand-600 overflow-hidden shrink-0">
                  <img src="https://cdn.discordapp.com/emojis/1154407886915784744.webp?size=96&quality=lossless" alt="Bot" class="w-full h-full object-cover">
                </div>
                <div>
                  <div class="flex items-center gap-1.5">
                    <span class="font-bold text-white text-sm">Sweety</span>
                    <span class="bg-[#5865F2] text-white text-[10px] font-bold px-1.5 py-0.2 rounded">BOT</span>
                    <span class="text-[11px] text-zinc-400">Today at 12:00 PM</span>
                  </div>
                  <div id="preview-raw-content" class="text-xs text-zinc-200 mt-1 whitespace-pre-wrap">Type a message or enable rich embed...</div>
                </div>
              </div>

              <!-- Embed Card -->
              <div id="preview-embed-box" class="discord-embed-preview p-3.5 ml-12 space-y-2.5" style="border-left-color: #8b5cf6;">
                <div id="preview-author" class="text-xs font-semibold text-zinc-300 hidden">Author Name</div>
                <div id="preview-title" class="font-bold text-white text-sm">Embed Title Preview</div>
                <div id="preview-desc" class="text-xs text-zinc-300 whitespace-pre-wrap">Your rich card description will appear formatted here exactly as it renders inside Discord channels.</div>
                <div id="preview-image-wrap" class="hidden rounded overflow-hidden max-h-48">
                  <img id="preview-image" src="" alt="Banner" class="w-full object-cover">
                </div>
                <div id="preview-footer" class="text-[10px] text-zinc-400 pt-1 border-t border-zinc-700/40 flex items-center justify-between">
                  <span>Official Notice • Powered by Sweety</span>
                  <span>Today at 12:00 PM</span>
                </div>
              </div>
            </div>
          </div>

          <div class="bg-carbon-800/60 p-3 rounded-xl border border-zinc-800 text-[11px] text-zinc-400 flex items-center gap-2">
            <i data-lucide="info" class="w-4 h-4 text-brand-400 shrink-0"></i>
            <span>Messages are sent directly through Discord's official Gateway using Sweety's authenticated client session.</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 3: DIRECT MESSAGES & USER ANNOUNCEMENTS
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-announcements" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            <i data-lucide="mail" class="w-5 h-5 text-sky-400"></i> Direct Message (DM) & Announcements Center
          </h2>
          <p class="text-xs text-zinc-400 mt-0.5">Send a personalized private message to an individual Discord user, or broadcast an announcement to server members.</p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- DM Form (Left 8) -->
        <div class="lg:col-span-8 glass-panel rounded-2xl p-6 space-y-5">
          <!-- Target Mode Selector -->
          <div class="flex p-1 bg-carbon-800 rounded-xl border border-zinc-800 max-w-md">
            <button onclick="setDmTargetMode('user')" id="btn-dm-mode-user" class="flex-1 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 text-white transition flex items-center justify-center gap-2">
              <i data-lucide="user" class="w-3.5 h-3.5"></i> Single User by ID
            </button>
            <button onclick="setDmTargetMode('guild')" id="btn-dm-mode-guild" class="flex-1 py-1.5 text-xs font-semibold rounded-lg text-zinc-400 hover:text-white transition flex items-center justify-center gap-2">
              <i data-lucide="users" class="w-3.5 h-3.5"></i> Server Member Broadcast
            </button>
          </div>

          <!-- Target User Fields -->
          <div id="dm-user-target-fields" class="space-y-3">
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400">Recipient Discord User ID</label>
            <div class="flex items-center gap-2">
              <input type="text" id="dm-target-user-id" placeholder="e.g. 719932313919684670 (Right-click user in Discord -> Copy User ID)" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 font-mono focus:outline-none focus:border-sky-500">
              <button onclick="fillNaraitoId()" class="px-3 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-300 font-medium whitespace-nowrap border border-zinc-700">
                Master Naraito
              </button>
            </div>
            <p class="text-[11px] text-zinc-500">The recipient must share at least one mutual server with Sweety or have DMs enabled.</p>
          </div>

          <!-- Target Server Broadcast Fields (Hidden by default) -->
          <div id="dm-guild-target-fields" class="hidden space-y-3">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Select Server Audience</label>
                <select id="dm-guild-select" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-sky-500">
                  <option value="">Select Discord Server...</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Max Member Limit</label>
                <input type="number" id="dm-guild-limit" value="25" min="1" max="100" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-sky-500">
              </div>
            </div>
            <div class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-300 flex items-start gap-2">
              <i data-lucide="alert-triangle" class="w-4 h-4 text-amber-400 shrink-0 mt-0.5"></i>
              <span>Broadcasts automatically skip bots and apply adaptive rate limiting (0.5s pause) to strictly respect Discord API terms.</span>
            </div>
          </div>

          <!-- Content Inputs -->
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Announcement Title / Subject</label>
            <input type="text" id="dm-title" placeholder="Important Announcement from Sweety" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-sky-500">
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Direct Message Body</label>
            <textarea id="dm-message" rows="5" placeholder="Write your personalized message or announcement details..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl p-3 text-xs text-zinc-100 focus:outline-none focus:border-sky-500 resize-y"></textarea>
          </div>

          <!-- Send Action Bar -->
          <div class="flex items-center justify-between pt-2">
            <span id="dm-send-status" class="text-xs text-zinc-400"></span>
            <button onclick="sendDirectMessage()" id="btn-send-dm" class="px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs transition flex items-center gap-2 shadow-lg shadow-sky-600/30">
              <i data-lucide="mail-check" class="w-4 h-4"></i> Send Direct Message
            </button>
          </div>
        </div>

        <!-- DM Tips & Guidance (Right 4) -->
        <div class="lg:col-span-4 glass-panel rounded-2xl p-6 space-y-4 flex flex-col justify-between">
          <div class="space-y-4">
            <h3 class="text-sm font-bold text-white flex items-center gap-2">
              <i data-lucide="shield-check" class="w-4 h-4 text-sky-400"></i> DM Delivery Rules & Best Practices
            </h3>
            <ul class="text-xs text-zinc-300 space-y-2.5 leading-relaxed">
              <li class="flex items-start gap-2">
                <i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0"></i>
                <span><strong>Mutual Server Required:</strong> Discord requires bots and users to share at least 1 server.</span>
              </li>
              <li class="flex items-start gap-2">
                <i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0"></i>
                <span><strong>User Privacy Settings:</strong> If a member has "Allow direct messages from server members" turned off, delivery gracefully notes failed status.</span>
              </li>
              <li class="flex items-start gap-2">
                <i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0"></i>
                <span><strong>Rate Limiting Safe:</strong> Bulk announcements automatically throttle to prevent gateway flags.</span>
              </li>
            </ul>
          </div>

          <div class="p-4 rounded-xl bg-carbon-800 border border-zinc-700/50 space-y-2">
            <span class="text-xs font-semibold text-zinc-200">Quick Test to Yourself:</span>
            <p class="text-[11px] text-zinc-400">Click below to automatically fill in Master Naraito's User ID and send a test DM!</p>
            <button onclick="fillNaraitoId(); document.getElementById('dm-title').value='Hello Master Naraito ❤️'; document.getElementById('dm-message').value='This is a live test from your new Sweety Web Dashboard! Everything is working flawlessly! ✨';" class="w-full py-2 bg-zinc-800 hover:bg-zinc-700 text-brand-300 rounded-lg text-xs font-semibold transition border border-brand-500/30">
              Load Master DM Template
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 4: MODERATION CONTROL CENTER
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-moderation" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            <i data-lucide="shield" class="w-5 h-5 text-red-400"></i> Moderation Command Center
          </h2>
          <p class="text-xs text-zinc-400 mt-0.5">Execute server enforcement actions: Kick, Ban, Unban, Timeout/Mute, Warn, Purge Messages, and Freeze Channels.</p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Moderation Actions Palette (Left 8) -->
        <div class="lg:col-span-8 glass-panel rounded-2xl p-6 space-y-5">
          <!-- Server & Target Picker -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Target Discord Server</label>
              <select id="mod-guild-select" onchange="loadGuildChannels(this.value, 'mod-channel-select')" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-red-500">
                <option value="">Select a Server...</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Target Member / User ID</label>
              <input type="text" id="mod-user-id" placeholder="Enter Discord User ID..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 font-mono focus:outline-none focus:border-red-500">
            </div>
          </div>

          <!-- Moderation Reason -->
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Infraction / Action Reason</label>
            <input type="text" id="mod-reason" value="Violation of server rules" placeholder="Reason displayed in audit log..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-red-500">
          </div>

          <!-- Action Grid Buttons -->
          <div class="space-y-3 pt-2 border-t border-zinc-800/80">
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400">Select Moderation Action</label>

            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <!-- Warn Button -->
              <button onclick="executeModAction('warn')" class="p-3 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 font-semibold text-xs transition flex flex-col items-center justify-center gap-1.5">
                <i data-lucide="alert-triangle" class="w-5 h-5 text-amber-400"></i> Issue Warning
              </button>

              <!-- Timeout / Mute -->
              <button onclick="executeModAction('timeout')" class="p-3 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold text-xs transition flex flex-col items-center justify-center gap-1.5">
                <i data-lucide="clock" class="w-5 h-5 text-purple-400"></i> Timeout (Mute)
              </button>

              <!-- Untimeout -->
              <button onclick="executeModAction('untimeout')" class="p-3 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold text-xs transition flex flex-col items-center justify-center gap-1.5">
                <i data-lucide="volume-2" class="w-5 h-5 text-emerald-400"></i> Remove Timeout
              </button>

              <!-- Kick Member -->
              <button onclick="executeModAction('kick')" class="p-3 rounded-xl bg-orange-500/10 hover:bg-orange-500/20 text-orange-300 border border-orange-500/30 font-semibold text-xs transition flex flex-col items-center justify-center gap-1.5">
                <i data-lucide="user-x" class="w-5 h-5 text-orange-400"></i> Kick Member
              </button>
            </div>

            <!-- Ban and Unban Row -->
            <div class="grid grid-cols-2 gap-2.5 pt-1">
              <button onclick="executeModAction('ban')" class="p-3 rounded-xl bg-red-600/20 hover:bg-red-600/30 text-red-200 border border-red-500/40 font-semibold text-xs transition flex items-center justify-center gap-2">
                <i data-lucide="ban" class="w-4 h-4 text-red-400"></i> Ban Member from Server
              </button>
              <button onclick="executeModAction('unban')" class="p-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 font-semibold text-xs transition flex items-center justify-center gap-2">
                <i data-lucide="user-check" class="w-4 h-4 text-emerald-400"></i> Unban Member by ID
              </button>
            </div>

            <!-- Timeout Duration Options -->
            <div class="bg-carbon-800/60 p-3 rounded-xl border border-zinc-800 flex flex-wrap items-center justify-between gap-2 text-xs">
              <span class="text-zinc-400 font-medium">Timeout Duration:</span>
              <div class="flex items-center gap-1.5">
                <button onclick="setDuration(60)" class="duration-chip px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300">1m</button>
                <button onclick="setDuration(300)" class="duration-chip px-2.5 py-1 rounded bg-brand-600 text-white font-semibold">5m</button>
                <button onclick="setDuration(600)" class="duration-chip px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300">10m</button>
                <button onclick="setDuration(3600)" class="duration-chip px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300">1h</button>
                <button onclick="setDuration(86400)" class="duration-chip px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300">1d</button>
                <button onclick="setDuration(604800)" class="duration-chip px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300">1w</button>
              </div>
            </div>
          </div>

          <!-- Channel Moderation (Purge & Lockdown) -->
          <div class="border-t border-zinc-800/80 pt-4 space-y-3">
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400">Channel Management & Message Purging</label>
            <div class="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
              <div class="sm:col-span-5">
                <label class="block text-[11px] text-zinc-400 mb-1">Target Channel</label>
                <select id="mod-channel-select" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3 py-2 text-xs text-zinc-100 focus:outline-none">
                  <option value="">Select Channel...</option>
                </select>
              </div>
              <div class="sm:col-span-3">
                <label class="block text-[11px] text-zinc-400 mb-1">Purge Amount (1-100)</label>
                <input type="number" id="mod-purge-count" value="25" min="1" max="100" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3 py-2 text-xs text-zinc-100">
              </div>
              <div class="sm:col-span-4 flex items-center gap-2">
                <button onclick="executeModAction('purge')" class="flex-1 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 text-xs font-semibold transition flex items-center justify-center gap-1.5">
                  <i data-lucide="trash-2" class="w-3.5 h-3.5 text-red-400"></i> Purge
                </button>
                <button onclick="executeModAction('lock')" class="py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 text-xs font-semibold transition" title="Freeze Channel">
                  <i data-lucide="lock" class="w-3.5 h-3.5 text-amber-400"></i>
                </button>
                <button onclick="executeModAction('unlock')" class="py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 text-xs font-semibold transition" title="Unfreeze Channel">
                  <i data-lucide="unlock" class="w-3.5 h-3.5 text-emerald-400"></i>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Live Server Audit Log Viewer (Right 4) -->
        <div class="lg:col-span-4 glass-panel rounded-2xl p-6 space-y-4 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-sm font-bold text-white flex items-center gap-2">
                <i data-lucide="history" class="w-4 h-4 text-red-400"></i> Recent Infractions Log
              </h3>
              <button onclick="refreshModLogs()" class="text-xs text-brand-400 hover:underline">Refresh</button>
            </div>
            <div id="mod-logs-container" class="space-y-2 max-h-96 overflow-y-auto pr-1">
              <div class="text-center py-8 text-zinc-500 text-xs">
                Select a server above to inspect recent moderation infractions and warnings.
              </div>
            </div>
          </div>

          <div class="p-3.5 rounded-xl bg-carbon-800 border border-zinc-800 text-[11px] text-zinc-400">
            <span>All actions are signed with Sweety's executor authorization and logged to the server database.</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 5: SWEETY AI PLAYGROUND ("stcccc")
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-ai" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            <i data-lucide="sparkles" class="w-5 h-5 text-pink-400"></i> Sweety AI Live Chat Playground
          </h2>
          <p class="text-xs text-zinc-400 mt-0.5">Direct web dialogue with Sweety! Test prompts, Cristiano Ronaldo debates, roasts, vision analysis, and memory recall.</p>
        </div>
        <div class="hidden sm:flex items-center gap-2">
          <span class="text-xs px-2.5 py-1 rounded-full bg-pink-500/10 text-pink-300 font-semibold border border-pink-500/20">
            Gemini 2.5 Flash
          </span>
          <span class="text-xs px-2.5 py-1 rounded-full bg-brand-500/10 text-brand-300 font-semibold border border-brand-500/20">
            Groq Llama-3.3 Failover
          </span>
        </div>
      </div>

      <!-- Interactive Chat Interface Container -->
      <div class="glass-panel rounded-2xl flex flex-col h-[650px] overflow-hidden border border-brand-500/20">
        <!-- Chat Header -->
        <div class="p-4 border-b border-zinc-800/80 bg-carbon-800/60 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-brand-600 to-pink-500 overflow-hidden flex items-center justify-center border border-white/20">
              <img src="https://cdn.discordapp.com/emojis/1154407886915784744.webp?size=96&quality=lossless" alt="Sweety" class="w-full h-full object-cover">
            </div>
            <div>
              <h4 class="text-xs font-bold text-white flex items-center gap-1.5">
                Sweety <span class="bg-[#5865F2] text-white text-[9px] font-bold px-1.5 py-0.2 rounded">BOT</span>
              </h4>
              <p class="text-[11px] text-zinc-400">Devoted to Master Naraito • CR7 Loyal Fan • Smart Chat Active</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="clearAiChat()" class="px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white text-xs transition">
              Clear Chat
            </button>
          </div>
        </div>

        <!-- Chat Messages Scroll Area -->
        <div id="ai-chat-messages" class="flex-1 p-5 overflow-y-auto space-y-4">
          <!-- Initial Bot Greeting -->
          <div class="flex items-start gap-3 max-w-2xl">
            <div class="w-8 h-8 rounded-full bg-brand-600 overflow-hidden shrink-0 mt-0.5">
              <img src="https://cdn.discordapp.com/emojis/1154407886915784744.webp?size=96&quality=lossless" alt="Sweety" class="w-full h-full object-cover">
            </div>
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <span class="text-xs font-bold text-white">Sweety</span>
                <span class="text-[10px] text-zinc-500">Live Web AI</span>
              </div>
              <div class="bg-carbon-800 border border-zinc-700/60 rounded-2xl rounded-tl-sm p-3.5 text-xs text-zinc-200 leading-relaxed">
                Naraito! ❤️ Welcome to my new command center! I'm right here with you. What would you like to discuss today? Whether you want to test my smart room awareness or talk about why Ronaldo is the undisputed G.O.A.T., I'm all ears! ✨💅
              </div>
            </div>
          </div>
        </div>

        <!-- Suggestion Chips -->
        <div class="px-4 py-2 bg-carbon-800/40 border-t border-zinc-800/60 flex items-center gap-2 overflow-x-auto text-[11px]">
          <span class="text-zinc-500 whitespace-nowrap">Suggested:</span>
          <button onclick="sendQuickPrompt('Who is the true football G.O.A.T.?')" class="px-2.5 py-1 rounded-full bg-zinc-800 hover:bg-zinc-700 text-zinc-300 whitespace-nowrap transition">
            ⚽ Who is the football G.O.A.T.?
          </button>
          <button onclick="sendQuickPrompt('Why do you love Naraito so much?')" class="px-2.5 py-1 rounded-full bg-zinc-800 hover:bg-zinc-700 text-pink-300 whitespace-nowrap transition">
            ❤️ Why do you love Naraito?
          </button>
          <button onclick="sendQuickPrompt('Someone just said Messi is better than Ronaldo. Thoughts?')" class="px-2.5 py-1 rounded-full bg-zinc-800 hover:bg-zinc-700 text-amber-300 whitespace-nowrap transition">
            🔥 Roast Messi fans
          </button>
          <button onclick="sendQuickPrompt('Give me a quick 3-bullet executive summary of your capabilities.')" class="px-2.5 py-1 rounded-full bg-zinc-800 hover:bg-zinc-700 text-brand-300 whitespace-nowrap transition">
            📋 What can you do?
          </button>
        </div>

        <!-- Chat Input Bar -->
        <div class="p-4 border-t border-zinc-800/80 bg-carbon-800/70">
          <form onsubmit="handleAiSubmit(event)" class="flex items-center gap-2">
            <input type="text" id="ai-input" placeholder="Type a message or prompt for Sweety..." class="flex-1 bg-carbon-900 border border-zinc-700/80 rounded-xl px-4 py-3 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-pink-500">
            <button type="submit" id="btn-ai-send" class="px-5 py-3 rounded-xl bg-gradient-to-r from-brand-600 to-pink-600 hover:from-brand-500 hover:to-pink-500 text-white font-semibold text-xs transition flex items-center gap-2 shadow-lg shadow-pink-600/20">
              <i data-lucide="send" class="w-4 h-4"></i> Send
            </button>
          </form>
          <div class="flex items-center justify-between mt-2 text-[10px] text-zinc-500">
            <span>Powered by Gemini 2.5 Flash & Groq Dual-Failover</span>
            <span id="ai-latency-stat">Ready for input</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 6: MUSIC STATION CONTROLLER
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-music" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            <i data-lucide="music" class="w-5 h-5 text-indigo-400"></i> Spotify-Style Music Control Station
          </h2>
          <p class="text-xs text-zinc-400 mt-0.5">Control live music playback, skip tracks, adjust volume, and inspect 24/7 audio queues across any connected server.</p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Active Voice Player (Left 8) -->
        <div class="lg:col-span-8 glass-panel rounded-2xl p-6 space-y-5">
          <div class="flex items-center justify-between">
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400">Select Server Voice Client</label>
            <button onclick="fetchBotStats(true)" class="text-xs text-brand-400 hover:underline">Refresh Players</button>
          </div>

          <select id="music-guild-select" onchange="loadMusicPlayerDetails(this.value)" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500">
            <option value="">Select a server currently in voice...</option>
          </select>

          <!-- Player Display Card -->
          <div class="bg-gradient-to-br from-carbon-800 to-carbon-900 rounded-2xl p-6 border border-zinc-700/60 space-y-5">
            <div class="flex flex-col sm:flex-row items-center gap-5">
              <div class="w-24 h-24 rounded-2xl bg-zinc-800 overflow-hidden shrink-0 shadow-2xl border border-white/10">
                <img id="music-card-thumb" src="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=300&q=80" alt="Album Cover" class="w-full h-full object-cover">
              </div>
              <div class="flex-1 min-w-0 text-center sm:text-left space-y-1">
                <span class="text-[10px] font-bold uppercase tracking-wider text-indigo-400 px-2 py-0.5 bg-indigo-500/10 rounded-full border border-indigo-500/20">Now Streaming</span>
                <h3 id="music-card-title" class="text-base font-bold text-white truncate">No Active Playback</h3>
                <p id="music-card-artist" class="text-xs text-zinc-400 truncate">Queue is empty or bot is disconnected</p>
                <div class="flex items-center justify-center sm:justify-start gap-3 pt-1 text-xs text-zinc-500 font-mono">
                  <span id="music-card-requester">Requester: --</span> • <span id="music-card-duration">Duration: 00:00</span>
                </div>
              </div>
            </div>

            <!-- Playback Control Buttons -->
            <div class="flex flex-wrap items-center justify-center gap-3 pt-2">
              <button onclick="sendMusicAction('pause')" class="p-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition" title="Pause">
                <i data-lucide="pause" class="w-5 h-5"></i>
              </button>
              <button onclick="sendMusicAction('resume')" class="p-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition" title="Resume">
                <i data-lucide="play" class="w-5 h-5"></i>
              </button>
              <button onclick="sendMusicAction('skip')" class="p-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition" title="Skip Track">
                <i data-lucide="skip-forward" class="w-5 h-5"></i>
              </button>
              <button onclick="sendMusicAction('stop')" class="p-3 rounded-xl bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-500/30 transition" title="Stop & Leave">
                <i data-lucide="square" class="w-5 h-5"></i>
              </button>
            </div>
          </div>
        </div>

        <!-- Audio Features Snapshot (Right 4) -->
        <div class="lg:col-span-4 glass-panel rounded-2xl p-6 space-y-4">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <i data-lucide="radio" class="w-4 h-4 text-indigo-400"></i> Studio Sound Features
          </h3>
          <div class="space-y-3 text-xs text-zinc-300">
            <div class="p-3 rounded-xl bg-carbon-800/80 border border-zinc-800">
              <span class="font-bold text-white block mb-0.5">24/7 Voice Persistence</span>
              <span class="text-zinc-400">Sweety automatically reconnects and stays alive in voice channels indefinitely with /247.</span>
            </div>
            <div class="p-3 rounded-xl bg-carbon-800/80 border border-zinc-800">
              <span class="font-bold text-white block mb-0.5">Real-Time DSP Audio Filters</span>
              <span class="text-zinc-400">Supports Nightcore, Bassboost, 8D Audio, and Vaporwave on-the-fly via FFmpeg.</span>
            </div>
            <div class="p-3 rounded-xl bg-carbon-800/80 border border-zinc-800">
              <span class="font-bold text-white block mb-0.5">Live Synced Karaoke Lyrics</span>
              <span class="text-zinc-400">Teleprompter synced lyrics with live community voice judging buttons.</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 7: SERVERS & SWEETY MODE MANAGER
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-servers" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            <i data-lucide="server" class="w-5 h-5 text-amber-400"></i> Connected Servers & Chat Mode Controller
          </h2>
          <p class="text-xs text-zinc-400 mt-0.5">Configure Sweety's participation mode: Pings Only (Default), Smart Chat (Reads the Room), or Completely Off.</p>
        </div>
      </div>

      <!-- Guild Cards Container -->
      <div id="guilds-cards-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div class="text-center py-12 text-zinc-500 text-xs col-span-full">
          Loading connected Discord servers...
        </div>
      </div>
    </section>

    <!-- ───────────────────────────────────────────────────────────────────────────
         TAB 8: LIVE CONSOLE LOGS
         ─────────────────────────────────────────────────────────────────────────── -->
    <section id="tab-console" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            <i data-lucide="terminal" class="w-5 h-5 text-emerald-400"></i> Live Bot Console & Event Stream
          </h2>
          <p class="text-xs text-zinc-400 mt-0.5">Live WebSocket stream of bot internal events, commands, AI calls, and moderation triggers.</p>
        </div>
        <div class="flex items-center gap-2">
          <button onclick="clearConsoleLog()" class="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-300 transition">
            Clear Terminal
          </button>
        </div>
      </div>

      <!-- Terminal Window -->
      <div class="glass-panel rounded-2xl overflow-hidden border border-zinc-800">
        <div class="bg-carbon-800/80 px-4 py-2.5 border-b border-zinc-800/80 flex items-center justify-between text-xs text-zinc-400 font-mono">
          <div class="flex items-center gap-2">
            <span class="w-3 h-3 rounded-full bg-red-500/80"></span>
            <span class="w-3 h-3 rounded-full bg-amber-500/80"></span>
            <span class="w-3 h-3 rounded-full bg-emerald-500/80"></span>
            <span class="ml-2 text-zinc-300">sweety@render-container:~# logs -f</span>
          </div>
          <span id="ws-console-status" class="text-emerald-400 flex items-center gap-1">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Connected
          </span>
        </div>
        <div id="terminal-content" class="p-4 bg-carbon-900 font-mono text-xs text-zinc-300 h-96 overflow-y-auto space-y-1">
          <div class="text-zinc-500">[SYSTEM] Live terminal logging session initiated.</div>
        </div>
      </div>
    </section>

  </main>

  <!-- AUTHENTICATION MODAL -->
  <div id="auth-modal" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden items-center justify-center p-4">
    <div class="glass-panel-elevated rounded-2xl max-w-md w-full p-6 space-y-5 border border-brand-500/30">
      <div class="flex items-center justify-between">
        <h3 class="text-base font-bold text-white flex items-center gap-2">
          <i data-lucide="lock" class="w-4 h-4 text-brand-400"></i> Master Naraito Dashboard Access
        </h3>
        <button onclick="closeAuthModal()" class="text-zinc-400 hover:text-white">
          <i data-lucide="x" class="w-5 h-5"></i>
        </button>
      </div>

      <p class="text-xs text-zinc-400">
        Enter your Admin API Key or connect directly with Master Naraito's verified identity to unlock all controls.
      </p>

      <form onsubmit="handleAdminLogin(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Master / Admin API Key</label>
          <input type="password" id="modal-admin-key" placeholder="Enter ADMIN_API_KEY from environment..." class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 focus:outline-none focus:border-brand-500">
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Discord User ID</label>
          <input type="text" id="modal-user-id" value="719932313919684670" class="w-full bg-carbon-800 border border-zinc-700/80 rounded-xl px-3.5 py-2.5 text-xs text-zinc-100 font-mono focus:outline-none focus:border-brand-500">
        </div>

        <div class="flex items-center gap-2 pt-2">
          <button type="submit" class="flex-1 py-2.5 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-xs font-semibold transition shadow-lg shadow-brand-600/30">
            Authenticate Session
          </button>
          <button type="button" onclick="closeAuthModal()" class="px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl text-xs font-semibold transition border border-zinc-700">
            Cancel
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- JAVASCRIPT APPLICATION CORE -->
  <script>
    // State Variables
    let currentTab = 'overview';
    let cachedGuilds = [];
    let authToken = localStorage.getItem('sweety_auth_token') || '';
    let currentDurationSeconds = 300;
    let dmTargetMode = 'user';
    let wsConsole = null;

    // Initialize on Load
    document.addEventListener('DOMContentLoaded', () => {
      lucide.createIcons();
      checkAuthStatus();
      fetchBotStats();
      fetchGuildsList();
      connectConsoleWebSocket();
      setInterval(() => fetchBotStats(false), 8000); // Poll every 8s
    });

    // Toast Notification Utility
    function showToast(message, type = 'success') {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      const bg = type === 'success' ? 'bg-emerald-600' : (type === 'error' ? 'bg-red-600' : 'bg-brand-600');
      toast.className = `${bg} text-white text-xs font-medium px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2 pointer-events-auto transform transition-all duration-300 translate-y-2 opacity-0`;
      toast.innerHTML = `<span>${message}</span>`;
      container.appendChild(toast);
      setTimeout(() => { toast.classList.remove('translate-y-2', 'opacity-0'); }, 10);
      setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
      }, 4000);
    }

    // Tab Switching Logic
    function switchTab(tabId) {
      currentTab = tabId;
      document.querySelectorAll('main > section').forEach(sec => sec.classList.add('hidden'));
      const activeSection = document.getElementById(`tab-${tabId}`);
      if (activeSection) activeSection.classList.remove('hidden');

      document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.getAttribute('data-tab') === tabId) {
          btn.className = "tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-white bg-brand-600 shadow";
        } else {
          btn.className = "tab-btn px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition text-zinc-400 hover:text-white hover:bg-zinc-800/60";
        }
      });
      lucide.createIcons();
    }

    function toggleMobileMenu() {
      const menu = document.getElementById('mobile-menu');
      menu.classList.toggle('hidden');
    }

    // Modal Control
    function openAuthModal() {
      document.getElementById('auth-modal').classList.remove('hidden');
      document.getElementById('auth-modal').classList.add('flex');
    }
    function closeAuthModal() {
      document.getElementById('auth-modal').classList.add('hidden');
      document.getElementById('auth-modal').classList.remove('flex');
    }

    // Auth State Check
    function checkAuthStatus() {
      const container = document.getElementById('auth-status-container');
      if (authToken) {
        container.innerHTML = `
          <div class="flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 px-3 py-1.5 rounded-xl">
            <span class="text-xs text-brand-300 font-semibold flex items-center gap-1">
              <i data-lucide="crown" class="w-3.5 h-3.5 text-amber-400"></i> Master Naraito
            </span>
            <button onclick="logout()" class="text-[11px] text-zinc-400 hover:text-red-400 ml-1">Logout</button>
          </div>
        `;
      } else {
        container.innerHTML = `
          <button onclick="openAuthModal()" class="px-3 py-1.5 text-xs font-semibold rounded-xl bg-brand-600 hover:bg-brand-500 text-white transition flex items-center gap-1.5 shadow-lg shadow-brand-600/20">
            <i data-lucide="key" class="w-3.5 h-3.5"></i> Master Connect
          </button>
        `;
      }
      lucide.createIcons();
    }

    async function handleAdminLogin(e) {
      e.preventDefault();
      const adminKey = document.getElementById('modal-admin-key').value.trim();
      const userId = document.getElementById('modal-user-id').value.trim();

      try {
        const res = await fetch('/api/auth/admin-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ admin_key: adminKey, user_id: userId })
        });
        const data = await res.json();
        if (data.token) {
          authToken = data.token;
          localStorage.setItem('sweety_auth_token', authToken);
          showToast('Authenticated as Master Naraito! 👑');
          closeAuthModal();
          checkAuthStatus();
          fetchBotStats(true);
          fetchGuildsList();
        } else {
          showToast(data.detail || 'Authentication failed', 'error');
        }
      } catch (err) {
        showToast('Error connecting to auth service', 'error');
      }
    }

    function logout() {
      authToken = '';
      localStorage.removeItem('sweety_auth_token');
      checkAuthStatus();
      showToast('Logged out of dashboard session');
    }

    function getAuthHeaders() {
      const headers = { 'Content-Type': 'application/json' };
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
      return headers;
    }

    // ── DATA FETCHING ────────────────────────────────────────────────────────────

    async function fetchBotStats(manual = false) {
      const refreshIcon = document.getElementById('refresh-icon');
      if (manual && refreshIcon) refreshIcon.classList.add('animate-spin');

      try {
        const res = await fetch('/api/bot/overview', { headers: getAuthHeaders() });
        if (!res.ok) throw new Error('Stats fetch error');
        const data = await res.json();

        // Update Header & Metrics
        document.getElementById('header-latency').innerText = `Ping: ${data.latency || 0} ms`;
        document.getElementById('header-uptime').innerText = `Uptime: ${data.uptime_str || '--'}`;
        document.getElementById('metric-latency').innerText = data.latency || 0;
        document.getElementById('metric-uptime').innerText = data.uptime_str || '--';
        document.getElementById('metric-guilds').innerText = data.guilds_count || 0;
        document.getElementById('metric-members').innerText = (data.users_count || 0).toLocaleString();
        document.getElementById('metric-ai-reqs').innerText = (data.ai_requests_today || 0).toLocaleString();
        document.getElementById('metric-voice').innerText = data.voice_connections_count || 0;

        // Update Hardware
        document.getElementById('cpu-percent').innerText = `${data.cpu || 0}%`;
        document.getElementById('cpu-bar').style.width = `${Math.min(100, Math.max(5, data.cpu || 0))}%`;
        document.getElementById('ram-percent').innerText = `${data.ram || 0}%`;
        document.getElementById('ram-bar').style.width = `${Math.min(100, Math.max(5, data.ram || 0))}%`;
        document.getElementById('ram-used').innerText = `${data.ram_used_mb || 0} MB`;

        // Update Bot Avatar if provided
        if (data.bot_user && data.bot_user.avatar) {
          document.getElementById('bot-avatar').src = data.bot_user.avatar;
        }

        // Update Music snapshot
        if (data.active_music_streams && data.active_music_streams.length > 0) {
          const track = data.active_music_streams[0];
          document.getElementById('music-indicator').innerText = 'Streaming';
          document.getElementById('music-indicator').className = 'text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium';
          document.getElementById('nowplaying-title').innerText = track.title || 'Live Stream';
          document.getElementById('nowplaying-sub').innerText = `Playing in ${track.guild_name} (${track.duration || 'Live'})`;
          document.getElementById('nowplaying-guild').innerText = `Server: ${track.guild_name}`;
          document.getElementById('nowplaying-vc').innerText = `Channel: ${track.voice_channel || 'VC'}`;
          if (track.thumbnail) document.getElementById('nowplaying-thumb').src = track.thumbnail;
        } else {
          document.getElementById('music-indicator').innerText = 'Idle';
          document.getElementById('music-indicator').className = 'text-xs px-2.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400 font-medium';
          document.getElementById('nowplaying-title').innerText = 'No music actively playing in any server';
          document.getElementById('nowplaying-sub').innerText = 'Use /play <song> in any Discord voice channel';
        }

        if (manual) showToast('Telemetry refreshed successfully');
      } catch (err) {
        console.error('Failed to fetch bot stats:', err);
      } finally {
        if (refreshIcon) refreshIcon.classList.remove('animate-spin');
      }
    }

    async function fetchGuildsList() {
      try {
        const res = await fetch('/api/guilds/list', { headers: getAuthHeaders() });
        if (!res.ok) return;
        cachedGuilds = await res.json();

        // Populate Guild Selectors
        const msgSelect = document.getElementById('msg-guild-select');
        const dmSelect = document.getElementById('dm-guild-select');
        const modSelect = document.getElementById('mod-guild-select');
        const musicSelect = document.getElementById('music-guild-select');

        const optionsHtml = '<option value="">Select a Discord Server...</option>' + 
          cachedGuilds.map(g => `<option value="${g.id}">${g.name} (${g.member_count} members)</option>`).join('');

        if (msgSelect) msgSelect.innerHTML = optionsHtml;
        if (dmSelect) dmSelect.innerHTML = optionsHtml;
        if (modSelect) modSelect.innerHTML = optionsHtml;
        if (musicSelect) musicSelect.innerHTML = optionsHtml;

        renderGuildCards();
      } catch (err) {
        console.error('Failed to load guilds:', err);
      }
    }

    async function loadGuildChannels(guildId, targetSelectId) {
      if (!guildId) return;
      const select = document.getElementById(targetSelectId);
      select.innerHTML = '<option value="">Loading channels...</option>';

      try {
        const res = await fetch(`/api/guilds/${guildId}/channels`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.channels) {
          select.innerHTML = '<option value="">Select Channel...</option>' + 
            data.channels.filter(c => c.type === 'text' || c.type === 'news').map(c => 
              `<option value="${c.id}"># ${c.name} (${c.category || 'General'})</option>`
            ).join('');
        }
      } catch (err) {
        select.innerHTML = '<option value="">Error loading channels</option>';
      }
    }

    function renderGuildCards() {
      const container = document.getElementById('guilds-cards-grid');
      if (!container) return;

      if (!cachedGuilds || cachedGuilds.length === 0) {
        container.innerHTML = '<div class="text-center py-12 text-zinc-500 text-xs col-span-full">No connected servers found.</div>';
        return;
      }

      container.innerHTML = cachedGuilds.map(g => `
        <div class="glass-panel rounded-2xl p-5 space-y-4 hover:border-brand-500/30 transition">
          <div class="flex items-center gap-3">
            <div class="w-12 h-12 rounded-2xl bg-zinc-800 overflow-hidden shrink-0 border border-white/10">
              <img src="${g.icon || 'https://cdn.discordapp.com/embed/avatars/0.png'}" alt="${g.name}" class="w-full h-full object-cover">
            </div>
            <div class="min-w-0 flex-1">
              <h4 class="text-sm font-bold text-white truncate">${g.name}</h4>
              <p class="text-xs text-zinc-400 font-mono">${g.member_count} members • ${g.channels_count} channels</p>
            </div>
          </div>

          <div class="pt-2 border-t border-zinc-800 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="text-zinc-400">Sweety Chat Mode:</span>
              <span class="font-bold text-brand-300 font-mono">${g.sweety_mode || 'pings_only'}</span>
            </div>
            <div class="grid grid-cols-3 gap-1 pt-1">
              <button onclick="setGuildSweetyMode('${g.id}', 'pings_only')" class="py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px] text-zinc-300 transition ${g.sweety_mode === 'pings_only' ? '!bg-brand-600 text-white font-bold' : ''}">
                🔔 Pings
              </button>
              <button onclick="setGuildSweetyMode('${g.id}', 'smart_chat')" class="py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px] text-zinc-300 transition ${g.sweety_mode === 'smart_chat' ? '!bg-brand-600 text-white font-bold' : ''}">
                🧠 Smart
              </button>
              <button onclick="setGuildSweetyMode('${g.id}', 'off')" class="py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px] text-zinc-300 transition ${g.sweety_mode === 'off' ? '!bg-red-600 text-white font-bold' : ''}">
                🚫 Off
              </button>
            </div>
          </div>
        </div>
      `).join('');
    }

    async function setGuildSweetyMode(guildId, mode) {
      try {
        const res = await fetch(`/api/guilds/${guildId}/mode`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ mode: mode })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Sweety mode set to ${mode}!`);
          fetchGuildsList();
        } else {
          showToast(data.detail || 'Failed to update mode', 'error');
        }
      } catch (err) {
        showToast('Error updating Sweety mode', 'error');
      }
    }

    // ── SERVER MESSENGER & EMBED PREVIEW ─────────────────────────────────────────

    function toggleEmbedFields() {
      const enabled = document.getElementById('enable-embed-toggle').checked;
      const fields = document.getElementById('embed-fields-container');
      const previewBox = document.getElementById('preview-embed-box');
      if (enabled) {
        fields.classList.remove('hidden');
        previewBox.classList.remove('hidden');
      } else {
        fields.classList.add('hidden');
        previewBox.classList.add('hidden');
      }
      updateEmbedPreview();
    }

    function updateEmbedPreview() {
      const rawContent = document.getElementById('msg-content').value;
      const previewRaw = document.getElementById('preview-raw-content');
      previewRaw.innerText = rawContent || 'Type a message...';

      const title = document.getElementById('embed-title').value;
      const desc = document.getElementById('embed-desc').value;
      const color = document.getElementById('embed-color').value;
      const author = document.getElementById('embed-author').value;
      const footer = document.getElementById('embed-footer').value;
      const image = document.getElementById('embed-image').value;

      document.getElementById('preview-title').innerText = title || 'Embed Title Preview';
      document.getElementById('preview-desc').innerText = desc || 'Your rich card description will appear formatted here...';
      document.getElementById('preview-embed-box').style.borderLeftColor = color || '#8b5cf6';

      const authorEl = document.getElementById('preview-author');
      if (author) {
        authorEl.innerText = author;
        authorEl.classList.remove('hidden');
      } else {
        authorEl.classList.add('hidden');
      }

      const footerEl = document.getElementById('preview-footer');
      if (footer) footerEl.firstElementChild.innerText = footer;

      const imgWrap = document.getElementById('preview-image-wrap');
      const imgEl = document.getElementById('preview-image');
      if (image) {
        imgEl.src = image;
        imgWrap.classList.remove('hidden');
      } else {
        imgWrap.classList.add('hidden');
      }
    }

    async function sendMessageToChannel() {
      const guildId = document.getElementById('msg-guild-select').value;
      const channelId = document.getElementById('msg-channel-select').value;
      const content = document.getElementById('msg-content').value;
      const embedEnabled = document.getElementById('enable-embed-toggle').checked;
      const statusEl = document.getElementById('send-msg-status');
      const btn = document.getElementById('btn-send-message');

      if (!guildId || !channelId) {
        showToast('Please select both a server and a channel', 'error');
        return;
      }
      if (!content && !embedEnabled) {
        showToast('Please type a message or enable a rich embed', 'error');
        return;
      }

      let embedData = null;
      if (embedEnabled) {
        embedData = {
          title: document.getElementById('embed-title').value,
          description: document.getElementById('embed-desc').value,
          color: document.getElementById('embed-color').value,
          author: document.getElementById('embed-author').value,
          footer: document.getElementById('embed-footer').value,
          image_url: document.getElementById('embed-image').value,
          thumbnail_url: document.getElementById('embed-thumb').value,
        };
      }

      btn.disabled = true;
      statusEl.innerText = 'Dispatching message to Discord...';

      try {
        const res = await fetch('/api/messages/send', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            guild_id: guildId,
            channel_id: channelId,
            content: content,
            embed: embedData
          })
        });
        const data = await res.json();
        if (data.success) {
          showToast('Message successfully posted by Sweety! ✨');
          statusEl.innerText = `Sent: Message ID ${data.message_id}`;
          document.getElementById('msg-content').value = '';
          updateEmbedPreview();
        } else {
          showToast(data.detail || 'Failed to dispatch message', 'error');
          statusEl.innerText = 'Dispatch failed';
        }
      } catch (err) {
        showToast('Error communicating with Discord gateway', 'error');
        statusEl.innerText = 'Error occurred';
      } finally {
        btn.disabled = false;
      }
    }

    // ── DIRECT MESSAGES & ANNOUNCEMENTS ──────────────────────────────────────────

    function setDmTargetMode(mode) {
      dmTargetMode = mode;
      const userBtn = document.getElementById('btn-dm-mode-user');
      const guildBtn = document.getElementById('btn-dm-mode-guild');
      const userFields = document.getElementById('dm-user-target-fields');
      const guildFields = document.getElementById('dm-guild-target-fields');

      if (mode === 'user') {
        userBtn.className = "flex-1 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 text-white transition flex items-center justify-center gap-2";
        guildBtn.className = "flex-1 py-1.5 text-xs font-semibold rounded-lg text-zinc-400 hover:text-white transition flex items-center justify-center gap-2";
        userFields.classList.remove('hidden');
        guildFields.classList.add('hidden');
      } else {
        guildBtn.className = "flex-1 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 text-white transition flex items-center justify-center gap-2";
        userBtn.className = "flex-1 py-1.5 text-xs font-semibold rounded-lg text-zinc-400 hover:text-white transition flex items-center justify-center gap-2";
        guildFields.classList.remove('hidden');
        userFields.classList.add('hidden');
      }
    }

    function fillNaraitoId() {
      document.getElementById('dm-target-user-id').value = '719932313919684670';
    }

    async function sendDirectMessage() {
      const btn = document.getElementById('btn-send-dm');
      const statusEl = document.getElementById('dm-send-status');
      const title = document.getElementById('dm-title').value;
      const message = document.getElementById('dm-message').value;

      if (!message) {
        showToast('Please type a message body', 'error');
        return;
      }

      let payload = {
        target_type: dmTargetMode,
        content: message,
        title: title
      };

      if (dmTargetMode === 'user') {
        const userId = document.getElementById('dm-target-user-id').value.trim();
        if (!userId) {
          showToast('Please specify a Discord User ID', 'error');
          return;
        }
        payload.target_id = userId;
      } else {
        const guildId = document.getElementById('dm-guild-select').value;
        const limit = parseInt(document.getElementById('dm-guild-limit').value) || 25;
        if (!guildId) {
          showToast('Please select a target server for broadcast', 'error');
          return;
        }
        payload.target_id = guildId;
        payload.guild_id = guildId;
        payload.limit = limit;
      }

      btn.disabled = true;
      statusEl.innerText = 'Dispatching Direct Message(s)...';

      try {
        const res = await fetch('/api/announcements/dm', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || 'Direct message(s) delivered! ✨');
          statusEl.innerText = `Delivered to: ${data.sent || 1} recipient(s)`;
        } else {
          showToast(data.detail || 'DM dispatch failed', 'error');
          statusEl.innerText = 'Delivery failed';
        }
      } catch (err) {
        showToast('Error communicating with DM service', 'error');
        statusEl.innerText = 'Error occurred';
      } finally {
        btn.disabled = false;
      }
    }

    // ── MODERATION CONTROLLER ───────────────────────────────────────────────────

    function setDuration(sec) {
      currentDurationSeconds = sec;
      document.querySelectorAll('.duration-chip').forEach(btn => {
        btn.classList.remove('bg-brand-600', 'text-white', 'font-semibold');
        btn.classList.add('bg-zinc-800', 'text-zinc-300');
      });
      event.target.classList.add('bg-brand-600', 'text-white', 'font-semibold');
      event.target.classList.remove('bg-zinc-800', 'text-zinc-300');
    }

    async function executeModAction(action) {
      const guildId = document.getElementById('mod-guild-select').value;
      const userId = document.getElementById('mod-user-id').value.trim();
      const reason = document.getElementById('mod-reason').value.trim();
      const channelId = document.getElementById('mod-channel-select').value;
      const purgeCount = parseInt(document.getElementById('mod-purge-count').value) || 25;

      if (!guildId) {
        showToast('Please select a target server', 'error');
        return;
      }

      if (['warn', 'timeout', 'untimeout', 'kick', 'ban', 'unban'].includes(action) && !userId) {
        showToast('Please enter a target Member / User ID', 'error');
        return;
      }

      if (['purge', 'lock', 'unlock'].includes(action) && !channelId) {
        showToast('Please select a target channel', 'error');
        return;
      }

      if (!confirm(`Are you sure you want to execute action: ${action.toUpperCase()}?`)) return;

      try {
        const res = await fetch('/api/moderate/action', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            action: action,
            guild_id: guildId,
            user_id: userId,
            channel_id: channelId,
            reason: reason,
            duration_seconds: currentDurationSeconds,
            amount: purgeCount
          })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Action ${action.toUpperCase()} executed successfully! 🛡️`);
          refreshModLogs();
        } else {
          showToast(data.detail || `Failed to execute ${action}`, 'error');
        }
      } catch (err) {
        showToast('Error sending moderation command', 'error');
      }
    }

    async function refreshModLogs() {
      const guildId = document.getElementById('mod-guild-select').value;
      if (!guildId) return;
      const container = document.getElementById('mod-logs-container');

      try {
        const res = await fetch(`/api/guilds/${guildId}/moderation`, { headers: getAuthHeaders() });
        const data = await res.json();
        const items = [...(data.warnings || []), ...(data.timeouts || []), ...(data.bans || [])];

        if (items.length === 0) {
          container.innerHTML = '<div class="text-center py-6 text-zinc-500 text-xs">No recorded infractions for this server.</div>';
          return;
        }

        container.innerHTML = items.slice(0, 15).map(item => `
          <div class="p-2.5 rounded-xl bg-carbon-800/80 border border-zinc-800 flex items-center justify-between text-xs">
            <div>
              <span class="font-bold text-white block">User: ${item.user_id}</span>
              <span class="text-zinc-400 text-[11px]">${item.reason || 'No reason'}</span>
            </div>
            <span class="text-[10px] text-zinc-500 font-mono">${item.timestamp ? item.timestamp.split('T')[0] : 'Recent'}</span>
          </div>
        `).join('');
      } catch (err) {
        container.innerHTML = '<div class="text-center py-6 text-zinc-500 text-xs">Error loading logs</div>';
      }
    }

    // ── AI PLAYGROUND ("stcccc") ────────────────────────────────────────────────

    async function handleAiSubmit(e) {
      e.preventDefault();
      const input = document.getElementById('ai-input');
      const text = input.value.trim();
      if (!text) return;

      appendAiMessage('user', text);
      input.value = '';
      const btn = document.getElementById('btn-ai-send');
      btn.disabled = true;
      document.getElementById('ai-latency-stat').innerText = 'Generating Sweety response...';

      try {
        const start = performance.now();
        const res = await fetch('/api/ai/playground', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ prompt: text, author_name: 'Naraito' })
        });
        const latency = Math.round(performance.now() - start);
        const data = await res.json();

        if (data.reply) {
          appendAiMessage('sweety', data.reply);
          document.getElementById('ai-latency-stat').innerText = `Model: ${data.model || 'Gemini 2.5'} • Latency: ${latency} ms`;
        } else {
          appendAiMessage('sweety', `❌ Error: ${data.detail || 'Could not reach model'}`);
        }
      } catch (err) {
        appendAiMessage('sweety', '❌ Network error connecting to Sweety AI service.');
      } finally {
        btn.disabled = false;
      }
    }

    function sendQuickPrompt(promptText) {
      document.getElementById('ai-input').value = promptText;
      handleAiSubmit(new Event('submit'));
    }

    function appendAiMessage(sender, text) {
      const container = document.getElementById('ai-chat-messages');
      const msg = document.createElement('div');
      msg.className = 'flex items-start gap-3 max-w-2xl';

      if (sender === 'user') {
        msg.className += ' ml-auto justify-end';
        msg.innerHTML = `
          <div class="space-y-1 text-right">
            <span class="text-xs font-bold text-brand-300">Naraito</span>
            <div class="bg-brand-600 text-white rounded-2xl rounded-tr-sm p-3.5 text-xs leading-relaxed text-left">
              ${text.replace(/\\n/g, '<br>')}
            </div>
          </div>
        `;
      } else {
        msg.innerHTML = `
          <div class="w-8 h-8 rounded-full bg-brand-600 overflow-hidden shrink-0 mt-0.5">
            <img src="https://cdn.discordapp.com/emojis/1154407886915784744.webp?size=96&quality=lossless" alt="Sweety" class="w-full h-full object-cover">
          </div>
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <span class="text-xs font-bold text-white">Sweety</span>
              <span class="text-[10px] text-zinc-500">Live AI</span>
            </div>
            <div class="bg-carbon-800 border border-zinc-700/60 rounded-2xl rounded-tl-sm p-3.5 text-xs text-zinc-200 leading-relaxed">
              ${text.replace(/\\n/g, '<br>')}
            </div>
          </div>
        `;
      }

      container.appendChild(msg);
      container.scrollTop = container.scrollHeight;
    }

    function clearAiChat() {
      document.getElementById('ai-chat-messages').innerHTML = '';
      showToast('AI Chat history cleared');
    }

    // ── MUSIC CONTROL ───────────────────────────────────────────────────────────

    async function sendMusicAction(action) {
      const guildId = document.getElementById('music-guild-select').value;
      if (!guildId) {
        showToast('Please select a server voice client first', 'error');
        return;
      }

      try {
        const res = await fetch('/api/music/control', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ guild_id: guildId, action: action })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Music action ${action.toUpperCase()} completed!`);
          fetchBotStats(true);
        } else {
          showToast(data.detail || `Action ${action} failed`, 'error');
        }
      } catch (err) {
        showToast('Error communicating with music engine', 'error');
      }
    }

    // ── LIVE CONSOLE WEBSOCKET ──────────────────────────────────────────────────

    function connectConsoleWebSocket() {
      const term = document.getElementById('terminal-content');
      const statusEl = document.getElementById('ws-console-status');
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/ws/console?key=${authToken}`;

      try {
        wsConsole = new WebSocket(wsUrl);

        wsConsole.onopen = () => {
          if (statusEl) statusEl.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Connected';
        };

        wsConsole.onmessage = (event) => {
          const line = document.createElement('div');
          line.className = 'font-mono text-zinc-300';
          line.innerText = event.data;
          term.appendChild(line);
          term.scrollTop = term.scrollHeight;
        };

        wsConsole.onclose = () => {
          if (statusEl) statusEl.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> Polling Mode';
        };

        wsConsole.onerror = () => {
          if (statusEl) statusEl.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-zinc-500"></span> Standby';
        };
      } catch (e) {
        console.warn('WebSocket console connection skipped:', e);
      }
    }

    function clearConsoleLog() {
      document.getElementById('terminal-content').innerHTML = '<div class="text-zinc-500">[SYSTEM] Terminal buffer cleared.</div>';
    }

    async function triggerGlobalSync() {
      try {
        showToast('Triggering global command sync...');
        const res = await fetch('/api/sync', { headers: getAuthHeaders() });
        const data = await res.json();
        showToast('Slash commands synced across all guilds! ⚡');
      } catch (err) {
        showToast('Error triggering sync', 'error');
      }
    }
  </script>
</body>
</html>
"""
