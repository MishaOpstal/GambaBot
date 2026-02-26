from flask import Flask, jsonify, render_template_string, abort, request, redirect, url_for
from flask_sock import Sock
from datetime import datetime
import json
import time
import asyncio
from database import db
import discord
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
sock = Sock(app)

bot_instance = None


def init_web_server(bot):
    global bot_instance
    bot_instance = bot
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# ─────────────────────────────────────────────────────────────────────────────
#  TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prediction Bot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0a0f;--surface:#13131a;--border:#222230;
  --accent:#e8ff47;--accent2:#ff6b6b;
  --text:#f0f0f8;--muted:#666680;
  --font:'Syne',sans-serif;--mono:'DM Mono',monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px 20px;overflow-x:hidden}
.noise{position:fixed;inset:0;opacity:.03;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");pointer-events:none;z-index:0}
.wrap{position:relative;z-index:1;max-width:600px;width:100%}
.badge{display:inline-block;background:var(--accent);color:#000;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;border-radius:2px;margin-bottom:32px;font-family:var(--mono)}
h1{font-size:clamp(42px,8vw,72px);font-weight:800;line-height:.95;margin-bottom:24px;letter-spacing:-.03em}
h1 span{color:var(--accent)}
.sub{color:var(--muted);font-size:18px;line-height:1.6;margin-bottom:56px;max-width:480px}
.steps{display:flex;flex-direction:column;gap:1px;border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:40px}
.step{background:var(--surface);padding:28px 32px;display:flex;gap:20px;align-items:flex-start;border-bottom:1px solid var(--border)}
.step:last-child{border-bottom:none}
.step-n{width:36px;height:36px;border-radius:50%;border:2px solid var(--accent);color:var(--accent);font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-family:var(--mono)}
.step-body h3{font-size:16px;font-weight:700;margin-bottom:6px}
.step-body p{color:var(--muted);font-size:14px;line-height:1.6}
code{background:#1e1e2e;color:var(--accent);padding:2px 8px;border-radius:4px;font-family:var(--mono);font-size:13px}
.note{border:1px solid var(--border);border-left:3px solid var(--accent2);padding:16px 20px;border-radius:0 8px 8px 0;font-size:13px;color:var(--muted);line-height:1.6}
.note strong{color:var(--accent2)}
</style>
</head>
<body>
<div class="noise"></div>
<div class="wrap">
  <div class="badge">Prediction Bot &mdash; Web UI</div>
  <h1>Real‑time<br><span>Predictions</span></h1>
  <p class="sub">Live overlays and interactive betting panels for your Discord streams.</p>
  <div class="steps">
    <div class="step"><div class="step-n">1</div><div class="step-body"><h3>Generate your auth token</h3><p>In Discord run <code>/authtoken refresh</code> — the bot will DM you a secure token.</p></div></div>
    <div class="step"><div class="step-n">2</div><div class="step-body"><h3>Get your server link</h3><p>Run <code>/webui</code> in your server to get a direct link to your prediction dashboard.</p></div></div>
    <div class="step"><div class="step-n">3</div><div class="step-body"><h3>Go live</h3><p>Visit the link, enter your token, and access live predictions with overlay and interactive modes.</p></div></div>
  </div>
  <div class="note"><strong>Security:</strong> Never share your auth token. Treat it like a password — it grants access to your prediction panel.</div>
</div>
</body>
</html>"""


GUILD_TOKEN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in — {{ guild_name }}</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a0a0f;--surface:#13131a;--border:#222230;--accent:#e8ff47;--accent2:#ff6b6b;--text:#f0f0f8;--muted:#666680;--font:'Syne',sans-serif;--mono:'DM Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.noise{position:fixed;inset:0;opacity:.03;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");pointer-events:none;z-index:0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:48px;max-width:480px;width:100%;position:relative;z-index:1}
.server-label{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:12px}
h1{font-size:36px;font-weight:800;letter-spacing:-.03em;margin-bottom:32px;line-height:1.1}
h1 span{color:var(--accent)}
label{display:block;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:8px;font-family:var(--mono)}
input[type=password]{width:100%;background:#0a0a0f;border:1px solid var(--border);color:var(--text);padding:14px 16px;border-radius:8px;font-family:var(--mono);font-size:14px;outline:none;transition:border-color .2s}
input[type=password]:focus{border-color:var(--accent)}
.btn{width:100%;margin-top:16px;background:var(--accent);color:#000;border:none;padding:14px;border-radius:8px;font-family:var(--font);font-size:15px;font-weight:700;cursor:pointer;letter-spacing:-.01em;transition:opacity .2s}
.btn:hover{opacity:.85}
.error{background:#2a1515;border:1px solid #4a2020;color:#ff9999;padding:12px 16px;border-radius:8px;margin-bottom:20px;font-size:13px}
.hint{margin-top:24px;padding-top:24px;border-top:1px solid var(--border);font-size:12px;color:var(--muted);line-height:1.6}
code{color:var(--accent);font-family:var(--mono)}
</style>
</head>
<body>
<div class="noise"></div>
<div class="card">
  <div class="server-label">{{ guild_name }}</div>
  <h1>Enter your<br><span>Auth Token</span></h1>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST" action="{{ url_for('guild_token_submit', guild_id=guild_id) }}">
    <label for="token">Token</label>
    <input type="password" id="token" name="token" placeholder="Paste your token here…" required autocomplete="off">
    <button type="submit" class="btn">Access Dashboard →</button>
  </form>
  <p class="hint">Don't have a token? Run <code>/authtoken refresh</code> in Discord — the bot will DM it to you.</p>
</div>
</body>
</html>"""


ERROR_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ error_code }} Error</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#f0f0f8;font-family:'Syne',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;padding:20px}
.code{font-size:120px;font-weight:800;color:#e8ff47;line-height:1}
h1{font-size:28px;margin:16px 0 12px;letter-spacing:-.03em}
p{color:#666680;max-width:420px;line-height:1.6;margin-bottom:32px}
a{display:inline-block;background:#e8ff47;color:#000;padding:12px 32px;border-radius:8px;font-weight:700;text-decoration:none}
</style>
</head>
<body>
<div><div class="code">{{ error_code }}</div><h1>{{ error_title }}</h1><p>{{ error_message }}</p><a href="/">← Go Home</a></div>
</body>
</html>"""


MAIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ guild_name }} — Predictions</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0a0f;--surface:#13131a;--surface2:#1a1a24;
  --border:#1e1e2e;--border2:#2a2a3e;
  --accent:#e8ff47;--accent2:#ff6b6b;--accent3:#6bffb8;--accent4:#6b9fff;
  --text:#f0f0f8;--text2:#b0b0c8;--muted:#555568;
  --font:'Syne',sans-serif;--mono:'DM Mono',monospace;
  --radius:12px;
}
*{margin:0;padding:0;box-sizing:border-box}
html{color-scheme:dark}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;overflow-x:hidden}
.noise{position:fixed;inset:0;opacity:.025;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");pointer-events:none;z-index:9999}

/* ── Layout ── */
.app{display:flex;flex-direction:column;min-height:100vh;max-width:1100px;margin:0 auto;padding:0 24px}
header{padding:28px 0 0;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:20px;gap:16px;flex-wrap:wrap}
.logo{display:flex;align-items:center;gap:12px}
.logo-mark{width:36px;height:36px;background:var(--accent);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.logo-text{font-weight:800;font-size:20px;letter-spacing:-.03em}
.logo-server{font-size:12px;color:var(--muted);font-family:var(--mono);margin-top:1px}
.header-actions{display:flex;gap:8px;align-items:center;flex-shrink:0}
.pill-btn{background:var(--surface);border:1px solid var(--border2);color:var(--text2);padding:7px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;letter-spacing:.01em;transition:all .2s;font-family:var(--font)}
.pill-btn:hover{border-color:var(--accent);color:var(--accent)}
.pill-btn.active{background:var(--accent);color:#000;border-color:var(--accent)}

/* ── Tabs ── */
nav.tabs{display:flex;gap:2px;padding:20px 0 0;border-bottom:1px solid var(--border);overflow-x:auto;scrollbar-width:none;flex-shrink:0}
nav.tabs::-webkit-scrollbar{display:none}
.tab{padding:10px 18px;border-radius:8px 8px 0 0;font-size:13px;font-weight:700;cursor:pointer;color:var(--muted);border:1px solid transparent;border-bottom:none;transition:all .15s;white-space:nowrap;letter-spacing:.01em;position:relative;bottom:-1px;background:transparent;font-family:var(--font)}
.tab:hover{color:var(--text2)}
.tab.active{background:var(--surface);border-color:var(--border);color:var(--text);border-bottom-color:var(--surface)}
.tab .count{display:inline-block;background:var(--border2);color:var(--muted);border-radius:10px;padding:1px 7px;font-size:11px;margin-left:6px;font-family:var(--mono)}
.tab.active .count{background:var(--accent);color:#000}

/* ── Main content ── */
main{flex:1;padding:28px 0 48px}
.tab-panel{display:none}
.tab-panel.active{display:block}

/* ── Prediction Cards ── */
.predictions-grid{display:flex;flex-direction:column;gap:16px}
.pred-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;transition:border-color .2s}
.pred-card:hover{border-color:var(--border2)}
.pred-header{padding:20px 24px 16px;display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.pred-question{font-size:18px;font-weight:700;line-height:1.3;letter-spacing:-.02em;flex:1}
.pred-meta{display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0}
.status-badge{font-family:var(--mono);font-size:11px;font-weight:500;padding:4px 10px;border-radius:20px;letter-spacing:.05em;text-transform:uppercase}
.status-live{background:#1a2a15;color:var(--accent3);border:1px solid #2a4a25}
.status-closed{background:#2a1a1a;color:#ff9a6b;border:1px solid #3a2a1a}
.status-resolved{background:#1a1a2a;color:var(--accent4);border:1px solid #252540}
.status-cancelled{background:#1e1e1e;color:var(--muted);border:1px solid var(--border)}
.pred-id{font-family:var(--mono);font-size:11px;color:var(--muted)}
.pred-timer{font-family:var(--mono);font-size:13px;color:var(--accent);font-weight:500}

.pred-body{padding:0 24px 20px}
.sides{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
.side-box{border-radius:8px;padding:12px 14px}
.side-b{background:rgba(107,159,255,.08);border:1px solid rgba(107,159,255,.2)}
.side-d{background:rgba(255,107,107,.08);border:1px solid rgba(255,107,107,.2)}
.side-label{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;font-family:var(--mono)}
.side-b .side-label{color:var(--accent4)}
.side-d .side-label{color:var(--accent2)}
.side-text{font-size:15px;font-weight:700;letter-spacing:-.01em}

.bar-wrap{height:10px;background:var(--border);border-radius:99px;overflow:hidden;margin-bottom:12px;display:flex}
.bar-b{height:100%;background:var(--accent4);border-radius:99px 0 0 99px;transition:width .5s ease}
.bar-d{height:100%;background:var(--accent2);border-radius:0 99px 99px 0;transition:width .5s ease}

.stats-row{display:flex;gap:20px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column}
.stat-label{font-size:11px;color:var(--muted);font-family:var(--mono);letter-spacing:.05em;text-transform:uppercase;margin-bottom:2px}
.stat-val{font-size:20px;font-weight:800;letter-spacing:-.03em}
.stat-val.blue{color:var(--accent4)}
.stat-val.red{color:var(--accent2)}
.stat-val.gold{color:var(--accent)}
.pct-row{display:flex;justify-content:space-between;font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:6px}
.pct-row span:first-child{color:var(--accent4)}
.pct-row span:last-child{color:var(--accent2)}

/* Resolved winner banner */
.winner-banner{margin-bottom:16px;background:rgba(232,255,71,.07);border:1px solid rgba(232,255,71,.2);border-radius:8px;padding:14px 16px;display:flex;align-items:center;gap:10px}
.winner-banner .trophy{font-size:20px}
.winner-banner .winner-text{font-size:14px;font-weight:600;color:var(--accent)}
.winner-banner .winner-sub{font-size:12px;color:var(--muted);margin-top:2px;font-family:var(--mono)}

/* ── My Bets Table ── */
.bets-table{width:100%;border-collapse:collapse}
.bets-table th{text-align:left;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);padding:10px 16px;border-bottom:1px solid var(--border)}
.bets-table td{padding:14px 16px;border-bottom:1px solid var(--border);font-size:14px;vertical-align:middle}
.bets-table tr:last-child td{border-bottom:none}
.bets-table tr:hover td{background:var(--surface2)}
.bet-side-b{color:var(--accent4);font-weight:700;font-family:var(--mono);font-size:12px}
.bet-side-d{color:var(--accent2);font-weight:700;font-family:var(--mono);font-size:12px}
.bet-amount{font-family:var(--mono);font-weight:500;color:var(--accent)}
.bet-status-win{color:var(--accent3);font-weight:700;font-family:var(--mono);font-size:12px}
.bet-status-loss{color:var(--accent2);font-family:var(--mono);font-size:12px}
.bet-status-pending{color:var(--muted);font-family:var(--mono);font-size:12px}
.table-wrap{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}

/* ── Start Prediction Form ── */
.form-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:32px}
.form-title{font-size:22px;font-weight:800;letter-spacing:-.03em;margin-bottom:24px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:600px){.form-grid{grid-template-columns:1fr}}
.form-group{display:flex;flex-direction:column;gap:6px}
.form-group.full{grid-column:1/-1}
label.fl{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-family:var(--mono)}
input.fi,select.fi,textarea.fi{background:#0a0a0f;border:1px solid var(--border2);color:var(--text);padding:11px 14px;border-radius:8px;font-family:var(--mono);font-size:13px;outline:none;transition:border-color .2s;resize:vertical}
input.fi:focus,select.fi:focus,textarea.fi:focus{border-color:var(--accent)}
select.fi option{background:#13131a}
.submit-btn{background:var(--accent);color:#000;border:none;padding:13px 28px;border-radius:8px;font-family:var(--font);font-size:15px;font-weight:700;cursor:pointer;letter-spacing:-.01em;transition:opacity .2s;margin-top:8px}
.submit-btn:hover{opacity:.85}
.submit-btn:disabled{opacity:.4;cursor:not-allowed}

/* ── Inline bet row ── */
.bet-row{padding:16px 24px;background:var(--surface2);border-top:1px solid var(--border);display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.bet-row input{flex:1;min-width:120px;background:var(--bg);border:1px solid var(--border2);color:var(--text);padding:9px 12px;border-radius:6px;font-family:var(--mono);font-size:13px;outline:none}
.bet-row input:focus{border-color:var(--accent)}
.bet-b-btn,.bet-d-btn{padding:9px 18px;border:none;border-radius:6px;font-family:var(--font);font-size:13px;font-weight:700;cursor:pointer;transition:opacity .2s}
.bet-b-btn{background:var(--accent4);color:#000}
.bet-d-btn{background:var(--accent2);color:#000}
.bet-b-btn:hover,.bet-d-btn:hover{opacity:.8}
.bet-row .points-info{font-size:12px;color:var(--muted);font-family:var(--mono)}

/* ── Empty state ── */
.empty{text-align:center;padding:80px 20px;color:var(--muted)}
.empty-icon{font-size:48px;margin-bottom:16px;opacity:.4}
.empty h3{font-size:18px;font-weight:700;color:var(--text2);margin-bottom:8px}
.empty p{font-size:14px;line-height:1.6}

/* ── Toast ── */
#toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(80px);padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;z-index:10000;opacity:0;transition:all .3s;pointer-events:none;font-family:var(--font)}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#toast.ok{background:var(--accent3);color:#000}
#toast.err{background:var(--accent2);color:#000}

/* ── Overlay mode ── */
body.overlay-mode{background:transparent!important}
body.overlay-mode .noise,body.overlay-mode header,body.overlay-mode nav.tabs,body.overlay-mode .non-overlay{display:none!important}
body.overlay-mode main{padding-top:0}
body.overlay-mode .pred-card{background:rgba(0,0,0,.82);backdrop-filter:blur(8px);border-color:rgba(255,255,255,.1)}
body.overlay-mode .overlay-exit{display:flex!important}
.overlay-exit{display:none;position:fixed;top:12px;right:12px;z-index:10000;background:rgba(0,0,0,.7);border:1px solid rgba(255,255,255,.15);color:rgba(255,255,255,.6);padding:6px 14px;border-radius:20px;font-size:11px;font-weight:600;text-decoration:none;letter-spacing:.05em;font-family:var(--mono);backdrop-filter:blur(8px);transition:all .2s;align-items:center;gap:6px}
.overlay-exit:hover{background:rgba(0,0,0,.9);color:#fff;border-color:rgba(255,255,255,.3)}

/* ── Filters ── */
.filter-bar{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap;align-items:center}
.filter-chip{background:var(--surface);border:1px solid var(--border2);color:var(--muted);padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;font-family:var(--font)}
.filter-chip:hover,.filter-chip.active{background:var(--surface2);border-color:var(--accent);color:var(--accent)}
.filter-label{font-size:12px;color:var(--muted);font-family:var(--mono);margin-right:4px}
.filter-bar-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.filter-bar-row+.filter-bar-row{margin-top:8px}
.filter-sep{width:100%;height:1px;background:var(--border);margin:4px 0}
.streamer-chip-filter{display:flex;align-items:center;gap:6px;background:var(--surface);border:1px solid var(--border2);color:var(--muted);padding:5px 12px 5px 6px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;font-family:var(--font)}
.streamer-chip-filter:hover,.streamer-chip-filter.active{background:var(--surface2);border-color:var(--accent);color:var(--accent)}
.streamer-chip-filter img{width:18px;height:18px;border-radius:50%;object-fit:cover}
.streamer-chip-filter .scf-initial{width:18px;height:18px;border-radius:50%;background:var(--border2);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:var(--muted);flex-shrink:0}

/* ── Streamer chip ── */
.streamer-chip{display:flex;align-items:center;gap:8px;margin-bottom:14px;padding:8px 12px;background:var(--surface2);border:1px solid var(--border2);border-radius:8px;width:fit-content}
.streamer-avatar{width:24px;height:24px;border-radius:50%;object-fit:cover;flex-shrink:0;background:var(--border2)}
.streamer-avatar-placeholder{width:24px;height:24px;border-radius:50%;background:var(--border2);display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--muted);flex-shrink:0}
.streamer-label{font-size:11px;color:var(--muted);font-family:var(--mono);letter-spacing:.05em;text-transform:uppercase;margin-right:2px}
.streamer-name{font-size:13px;font-weight:700;color:var(--text2)}

/* ── Manage actions row ── */
.manage-row{padding:12px 24px;background:var(--bg);border-top:1px solid var(--border);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.manage-row .manage-label{font-size:11px;color:var(--muted);font-family:var(--mono);letter-spacing:.05em;text-transform:uppercase;margin-right:4px}
.mgmt-btn{padding:7px 14px;border:1px solid var(--border2);border-radius:6px;font-family:var(--font);font-size:12px;font-weight:700;cursor:pointer;transition:all .2s;background:var(--surface)}
.mgmt-btn-believe{color:var(--accent4);border-color:rgba(107,159,255,.3)}
.mgmt-btn-believe:hover{background:rgba(107,159,255,.15);border-color:var(--accent4)}
.mgmt-btn-doubt{color:var(--accent2);border-color:rgba(255,107,107,.3)}
.mgmt-btn-doubt:hover{background:rgba(255,107,107,.15);border-color:var(--accent2)}
.mgmt-btn-refund{color:var(--muted);border-color:var(--border2)}
.mgmt-btn-refund:hover{background:var(--surface2);color:var(--text2)}

/* ── Confirm overlay ── */
.confirm-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);z-index:20000;align-items:center;justify-content:center;padding:20px}
.confirm-overlay.show{display:flex}
.confirm-box{background:var(--surface);border:1px solid var(--border2);border-radius:16px;padding:32px;max-width:400px;width:100%;text-align:center}
.confirm-box h3{font-size:20px;font-weight:800;letter-spacing:-.03em;margin-bottom:8px}
.confirm-box p{font-size:14px;color:var(--muted);line-height:1.6;margin-bottom:24px}
.confirm-actions{display:flex;gap:10px;justify-content:center}
.confirm-yes{background:var(--accent);color:#000;border:none;padding:10px 24px;border-radius:8px;font-weight:700;font-size:14px;cursor:pointer;font-family:var(--font)}
.confirm-yes.danger{background:var(--accent2);color:#000}
.confirm-no{background:var(--surface2);color:var(--text2);border:1px solid var(--border2);padding:10px 24px;border-radius:8px;font-weight:700;font-size:14px;cursor:pointer;font-family:var(--font)}
.confirm-no:hover{border-color:var(--text2)}

/* Scrollbar */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}
</style>
</head>
<body class="{{ 'overlay-mode' if overlay else '' }}">

{# ── Macros must be defined before use in Jinja2 ── #}
{% macro render_running_card(pred_id, pred) %}
<div class="pred-card" id="card-{{ pred_id }}" data-status="{{ 'closed' if pred.closed else 'open' }}" data-streamer="{{ pred.streamer_name }}">
  <div class="pred-header">
    <div class="pred-question" id="q-{{ pred_id }}">{{ pred.question }}</div>
    <div class="pred-meta">
      {% if pred.closed %}
        <span class="status-badge status-closed">Betting Closed</span>
      {% else %}
        <span class="status-badge status-live">● Live</span>
      {% endif %}
      <span class="pred-id">{{ pred_id }}</span>
      {% if not pred.closed %}
        <span class="pred-timer" id="timer-{{ pred_id }}" data-end="{{ pred.ending_timestamp }}">⏰ …</span>
      {% endif %}
    </div>
  </div>
  <div class="pred-body">
    <div class="streamer-chip">
      {% if pred.streamer_avatar %}
        <img class="streamer-avatar" src="{{ pred.streamer_avatar }}" alt="{{ pred.streamer_name }}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
        <div class="streamer-avatar-placeholder" style="display:none">{{ pred.streamer_name[0] | upper }}</div>
      {% else %}
        <div class="streamer-avatar-placeholder">{{ pred.streamer_name[0] | upper }}</div>
      {% endif %}
      <span class="streamer-label">for</span>
      <span class="streamer-name">{{ pred.streamer_name }}</span>
    </div>
    <div class="sides">
      <div class="side-box side-b">
        <div class="side-label">✅ Believe</div>
        <div class="side-text" id="ba-{{ pred_id }}">{{ pred.believe_answer }}</div>
      </div>
      <div class="side-box side-d">
        <div class="side-label">❌ Doubt</div>
        <div class="side-text" id="da-{{ pred_id }}">{{ pred.doubt_answer }}</div>
      </div>
    </div>
    <div class="pct-row">
      <span id="bpct-{{ pred_id }}">{{ pred.believe_percentage }}%</span>
      <span id="dpct-{{ pred_id }}">{{ pred.doubt_percentage }}%</span>
    </div>
    <div class="bar-wrap">
      <div class="bar-b" id="bbar-{{ pred_id }}" style="width:{{ pred.believe_percentage }}%"></div>
      <div class="bar-d" id="dbar-{{ pred_id }}" style="width:{{ pred.doubt_percentage }}%"></div>
    </div>
    <div class="stats-row">
      <div class="stat"><div class="stat-label">Believe</div><div class="stat-val blue" id="bpts-{{ pred_id }}">{{ pred.believe_points }}</div></div>
      <div class="stat"><div class="stat-label">Doubt</div><div class="stat-val red" id="dpts-{{ pred_id }}">{{ pred.doubt_points }}</div></div>
      <div class="stat"><div class="stat-label">Bettors</div><div class="stat-val" id="btrs-{{ pred_id }}">{{ pred.total_bettors }}</div></div>
      <div class="stat"><div class="stat-label">Currency</div><div class="stat-val gold" style="font-size:14px" id="pname-{{ pred_id }}">{{ pred.point_name }}</div></div>
    </div>
  </div>
  {% if not pred.closed and not overlay %}
  <div class="bet-row" id="betrow-{{ pred_id }}">
    <input type="number" id="amt-{{ pred_id }}" placeholder="Amount…" min="1" style="max-width:160px">
    <button class="bet-b-btn" onclick="placeBet('{{ pred_id }}','believe')">✅ {{ pred.believe_answer }}</button>
    <button class="bet-d-btn" onclick="placeBet('{{ pred_id }}','doubt')">❌ {{ pred.doubt_answer }}</button>
    <span class="points-info" id="pinfo-{{ pred_id }}"></span>
  </div>
  {% endif %}
  {% if pred.can_manage and not overlay %}
  <div class="manage-row">
    <span class="manage-label">Resolve as →</span>
    <button class="mgmt-btn mgmt-btn-believe" onclick="confirmAction('resolve','{{ pred_id }}','believe','{{ pred.believe_answer }}')">✅ {{ pred.believe_answer }}</button>
    <button class="mgmt-btn mgmt-btn-doubt" onclick="confirmAction('resolve','{{ pred_id }}','doubt','{{ pred.doubt_answer }}')">❌ {{ pred.doubt_answer }}</button>
    <button class="mgmt-btn mgmt-btn-refund" onclick="confirmAction('refund','{{ pred_id }}',null,'Refund all bets?')">↩ Refund & Cancel</button>
  </div>
  {% endif %}
</div>
{% endmacro %}

{% macro render_history_card(pred_id, pred, kind) %}
<div class="pred-card" data-streamer="{{ pred.streamer_name }}">
  <div class="pred-header">
    <div class="pred-question">{{ pred.question }}</div>
    <div class="pred-meta">
      {% if kind == 'resolved' %}
        <span class="status-badge status-resolved">Resolved</span>
      {% else %}
        <span class="status-badge status-cancelled">Cancelled</span>
      {% endif %}
      <span class="pred-id">{{ pred_id }}</span>
      {% if pred.resolved_at %}
        <span style="font-family:var(--mono);font-size:11px;color:var(--muted)">{{ pred.resolved_at }}</span>
      {% endif %}
    </div>
  </div>
  <div class="pred-body">
    <div class="streamer-chip">
      {% if pred.streamer_avatar %}
        <img class="streamer-avatar" src="{{ pred.streamer_avatar }}" alt="{{ pred.streamer_name }}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
        <div class="streamer-avatar-placeholder" style="display:none">{{ pred.streamer_name[0] | upper }}</div>
      {% else %}
        <div class="streamer-avatar-placeholder">{{ pred.streamer_name[0] | upper }}</div>
      {% endif %}
      <span class="streamer-label">for</span>
      <span class="streamer-name">{{ pred.streamer_name }}</span>
    </div>
    {% if kind == 'resolved' and pred.winner %}
    <div class="winner-banner">
      <span class="trophy">🏆</span>
      <div>
        <div class="winner-text">{{ pred.winner_answer }} won!</div>
        <div class="winner-sub">{{ pred.winner }} side — {{ pred.winning_pool }} points distributed</div>
      </div>
    </div>
    {% endif %}
    <div class="sides">
      <div class="side-box side-b">
        <div class="side-label">✅ Believe</div>
        <div class="side-text">{{ pred.believe_answer }}</div>
      </div>
      <div class="side-box side-d">
        <div class="side-label">❌ Doubt</div>
        <div class="side-text">{{ pred.doubt_answer }}</div>
      </div>
    </div>
    <div class="pct-row">
      <span>{{ pred.believe_percentage }}%</span>
      <span>{{ pred.doubt_percentage }}%</span>
    </div>
    <div class="bar-wrap">
      <div class="bar-b" style="width:{{ pred.believe_percentage }}%"></div>
      <div class="bar-d" style="width:{{ pred.doubt_percentage }}%"></div>
    </div>
    <div class="stats-row">
      <div class="stat"><div class="stat-label">Believe</div><div class="stat-val blue">{{ pred.believe_points }}</div></div>
      <div class="stat"><div class="stat-label">Doubt</div><div class="stat-val red">{{ pred.doubt_points }}</div></div>
      <div class="stat"><div class="stat-label">Bettors</div><div class="stat-val">{{ pred.total_bettors }}</div></div>
      <div class="stat"><div class="stat-label">Currency</div><div class="stat-val gold" style="font-size:14px">{{ pred.point_name }}</div></div>
    </div>
  </div>
</div>
{% endmacro %}

<div class="noise"></div>
<a href="?" class="overlay-exit">⚙️ Exit Overlay</a>
<div class="app">

  <header>
    <div class="logo">
      <div class="logo-mark">🎲</div>
      <div>
        <div class="logo-text">Predictions</div>
        <div class="logo-server">{{ guild_name }}</div>
      </div>
    </div>
    <div class="header-actions non-overlay">
      {% if not overlay %}
        <a href="?overlay=1" class="pill-btn">📺 Overlay</a>
        <a href="?overlay=0" class="pill-btn active">⚙️ Interactive</a>
      {% else %}
        <a href="?" class="pill-btn">⚙️ Interactive</a>
      {% endif %}
    </div>
  </header>

  <nav class="tabs non-overlay" id="main-tabs">
    <div class="tab active" data-tab="running" onclick="switchTab('running')">
      Live <span class="count" id="cnt-running">{{ running_count }}</span>
    </div>
    <div class="tab" data-tab="resolved" onclick="switchTab('resolved')">
      Resolved <span class="count" id="cnt-resolved">{{ resolved_count }}</span>
    </div>
    <div class="tab" data-tab="cancelled" onclick="switchTab('cancelled')">
      Cancelled <span class="count" id="cnt-cancelled">{{ cancelled_count }}</span>
    </div>
    <div class="tab" data-tab="mybets" onclick="switchTab('mybets')">
      My Bets <span class="count" id="cnt-mybets">{{ my_bets_count }}</span>
    </div>
    {% if can_start %}
    <div class="tab" data-tab="start" onclick="switchTab('start')">
      ➕ Start
    </div>
    {% endif %}
  </nav>

  <main>
    <!-- ── RUNNING TAB ── -->
    <div class="tab-panel active" id="tab-running">
      <div class="filter-bar" id="filter-bar-running">
        <div class="filter-bar-row">
          <span class="filter-label">Status:</span>
          <div class="filter-chip active" data-status-filter="all" onclick="setStatusFilter(this,'running')">All</div>
          <div class="filter-chip" data-status-filter="open" onclick="setStatusFilter(this,'running')">Open</div>
          <div class="filter-chip" data-status-filter="closed" onclick="setStatusFilter(this,'running')">Betting Closed</div>
        </div>
        {% if all_streamers | length > 1 %}
        <div class="filter-sep"></div>
        <div class="filter-bar-row">
          <span class="filter-label">Streamer:</span>
          <div class="streamer-chip-filter active" data-streamer-filter="all" onclick="setStreamerFilter(this,'running')">All</div>
          {% for s in all_streamers %}
          <div class="streamer-chip-filter" data-streamer-filter="{{ s.name }}" onclick="setStreamerFilter(this,'running')">
            {% if s.avatar %}<img src="{{ s.avatar }}" alt="{{ s.name }}" onerror="this.style.display='none'">{% else %}<span class="scf-initial">{{ s.name[0] | upper }}</span>{% endif %}
            {{ s.name }}
          </div>
          {% endfor %}
        </div>
        {% endif %}
      </div>
      <div class="predictions-grid" id="running-grid">
        {% if running_predictions %}
          {% for pred_id, pred in running_predictions.items() %}
            {{ render_running_card(pred_id, pred) }}
          {% endfor %}
        {% else %}
          <div class="empty"><div class="empty-icon">📡</div><h3>No live predictions</h3><p>Start one using the ➕ Start tab or the /prediction start command in Discord.</p></div>
        {% endif %}
      </div>
    </div>

    <!-- ── RESOLVED TAB ── -->
    <div class="tab-panel" id="tab-resolved">
      {% if all_streamers | length > 1 %}
      <div class="filter-bar" id="filter-bar-resolved">
        <div class="filter-bar-row">
          <span class="filter-label">Streamer:</span>
          <div class="streamer-chip-filter active" data-streamer-filter="all" onclick="setStreamerFilter(this,'resolved')">All</div>
          {% for s in all_streamers %}
          <div class="streamer-chip-filter" data-streamer-filter="{{ s.name }}" onclick="setStreamerFilter(this,'resolved')">
            {% if s.avatar %}<img src="{{ s.avatar }}" alt="{{ s.name }}" onerror="this.style.display='none'">{% else %}<span class="scf-initial">{{ s.name[0] | upper }}</span>{% endif %}
            {{ s.name }}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}
      <div class="predictions-grid" id="resolved-grid">
        {% if resolved_predictions %}
          {% for pred_id, pred in resolved_predictions.items() %}
            {{ render_history_card(pred_id, pred, 'resolved') }}
          {% endfor %}
        {% else %}
          <div class="empty"><div class="empty-icon">🏆</div><h3>No resolved predictions yet</h3><p>Resolved predictions will appear here once an admin declares a winner.</p></div>
        {% endif %}
      </div>
    </div>

    <!-- ── CANCELLED TAB ── -->
    <div class="tab-panel" id="tab-cancelled">
      {% if all_streamers | length > 1 %}
      <div class="filter-bar" id="filter-bar-cancelled">
        <div class="filter-bar-row">
          <span class="filter-label">Streamer:</span>
          <div class="streamer-chip-filter active" data-streamer-filter="all" onclick="setStreamerFilter(this,'cancelled')">All</div>
          {% for s in all_streamers %}
          <div class="streamer-chip-filter" data-streamer-filter="{{ s.name }}" onclick="setStreamerFilter(this,'cancelled')">
            {% if s.avatar %}<img src="{{ s.avatar }}" alt="{{ s.name }}" onerror="this.style.display='none'">{% else %}<span class="scf-initial">{{ s.name[0] | upper }}</span>{% endif %}
            {{ s.name }}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}
      <div class="predictions-grid" id="cancelled-grid">
        {% if cancelled_predictions %}
          {% for pred_id, pred in cancelled_predictions.items() %}
            {{ render_history_card(pred_id, pred, 'cancelled') }}
          {% endfor %}
        {% else %}
          <div class="empty"><div class="empty-icon">↩️</div><h3>No cancelled predictions</h3><p>Predictions that were refunded and cancelled will appear here.</p></div>
        {% endif %}
      </div>
    </div>

    <!-- ── MY BETS TAB ── -->
    <div class="tab-panel" id="tab-mybets">
      {% if my_bets %}
        <div class="table-wrap">
          <table class="bets-table">
            <thead><tr>
              <th>Question</th>
              <th>Side</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Result</th>
            </tr></thead>
            <tbody>
              {% for bet in my_bets %}
              <tr>
                <td style="max-width:300px">
                  <div style="font-weight:600;font-size:14px;letter-spacing:-.01em">{{ bet.question }}</div>
                  <div style="font-size:11px;color:var(--muted);font-family:var(--mono);margin-top:2px">{{ bet.pred_id }}</div>
                </td>
                <td>
                  {% if bet.side == 'believe' %}
                    <span class="bet-side-b">✅ BELIEVE</span>
                    <div style="font-size:11px;color:var(--muted);margin-top:2px">{{ bet.believe_answer }}</div>
                  {% else %}
                    <span class="bet-side-d">❌ DOUBT</span>
                    <div style="font-size:11px;color:var(--muted);margin-top:2px">{{ bet.doubt_answer }}</div>
                  {% endif %}
                </td>
                <td><span class="bet-amount">{{ bet.amount }}</span></td>
                <td>
                  {% if bet.pred_status == 'live' %}<span class="status-badge status-live">Live</span>
                  {% elif bet.pred_status == 'closed' %}<span class="status-badge status-closed">Closed</span>
                  {% elif bet.pred_status == 'resolved' %}<span class="status-badge status-resolved">Resolved</span>
                  {% elif bet.pred_status == 'cancelled' %}<span class="status-badge status-cancelled">Cancelled</span>
                  {% endif %}
                </td>
                <td>
                  {% if bet.pred_status == 'resolved' %}
                    {% if bet.won %}<span class="bet-status-win">+{{ bet.payout }} WON</span>
                    {% else %}<span class="bet-status-loss">LOST</span>{% endif %}
                  {% elif bet.pred_status == 'cancelled' %}
                    <span style="color:var(--muted);font-family:var(--mono);font-size:12px">REFUNDED</span>
                  {% else %}
                    <span class="bet-status-pending">PENDING</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      {% else %}
        <div class="empty"><div class="empty-icon">💸</div><h3>No bets placed yet</h3><p>Place bets on live predictions to see them here.</p></div>
      {% endif %}
    </div>

    <!-- ── START TAB ── -->
    {% if can_start %}
    <div class="tab-panel" id="tab-start">
      <div class="form-card">
        <div class="form-title">Start a New Prediction</div>
        <form id="start-form">
          <div class="form-grid">
            <div class="form-group">
              <label class="fl">Streamer</label>
              <select class="fi" id="f-streamer">
                {% for s in eligible_streamers %}
                <option value="{{ s.id }}">{{ s.name }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="form-group">
              <label class="fl">Post to Channel</label>
              <select class="fi" id="f-channel">
                {% for c in channels %}
                <option value="{{ c.id }}">#{{ c.name }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="form-group full">
              <label class="fl">Question</label>
              <input type="text" class="fi" id="f-question" placeholder="Will we win this match?" required>
            </div>
            <div class="form-group">
              <label class="fl">Believe Answer</label>
              <input type="text" class="fi" id="f-believe" value="Believe">
            </div>
            <div class="form-group">
              <label class="fl">Doubt Answer</label>
              <input type="text" class="fi" id="f-doubt" value="Doubt">
            </div>
            <div class="form-group">
              <label class="fl">Duration (seconds)</label>
              <input type="number" class="fi" id="f-time" value="300" min="10" max="3600">
            </div>
          </div>
          <button type="submit" class="submit-btn">🚀 Start Prediction</button>
        </form>
      </div>
    </div>
    {% endif %}
  </main>
</div>

<div id="toast"></div>

<!-- ── Confirm dialog ── -->
<div class="confirm-overlay" id="confirm-overlay">
  <div class="confirm-box">
    <h3 id="confirm-title">Are you sure?</h3>
    <p id="confirm-body">This action cannot be undone.</p>
    <div class="confirm-actions">
      <button class="confirm-yes" id="confirm-yes-btn" onclick="confirmExecute()">Confirm</button>
      <button class="confirm-no" onclick="closeConfirm()">Cancel</button>
    </div>
  </div>
</div>

<script>
const GUILD_ID = "{{ guild_id }}";
const TOKEN = "{{ token }}";
const OVERLAY = {{ 'true' if overlay else 'false' }};
let currentTab = 'running';

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  currentTab = name;
}

// Per-tab filter state: { status, streamer }
const tabFilters = {
  running:   { status: 'all', streamer: 'all' },
  resolved:  { status: 'all', streamer: 'all' },
  cancelled: { status: 'all', streamer: 'all' },
};

const gridId = { running: 'running-grid', resolved: 'resolved-grid', cancelled: 'cancelled-grid' };

function applyFilters(tab) {
  const { status, streamer } = tabFilters[tab];
  const grid = document.getElementById(gridId[tab]);
  if (!grid) return;
  grid.querySelectorAll('.pred-card').forEach(card => {
    const statusOk = status === 'all' || card.dataset.status === status;
    const streamerOk = streamer === 'all' || card.dataset.streamer === streamer;
    card.style.display = (statusOk && streamerOk) ? '' : 'none';
  });
}

function setStatusFilter(el, tab) {
  tabFilters[tab].status = el.dataset.statusFilter;
  const bar = document.getElementById('filter-bar-' + tab);
  if (bar) bar.querySelectorAll('[data-status-filter]').forEach(c => c.classList.toggle('active', c === el));
  applyFilters(tab);
}

function setStreamerFilter(el, tab) {
  tabFilters[tab].streamer = el.dataset.streamerFilter;
  const bar = document.getElementById('filter-bar-' + tab);
  if (bar) bar.querySelectorAll('[data-streamer-filter]').forEach(c => c.classList.toggle('active', c === el));
  applyFilters(tab);
}

// Legacy alias kept in case anything still calls it
function filterPreds(el, filter) { setStatusFilter(el, 'running'); }

function toast(msg, type='ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show ' + type;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = ''; }, 3000);
}

async function placeBet(predId, side) {
  const amount = document.getElementById('amt-' + predId)?.value;
  if (!amount || amount <= 0) { toast('Enter a valid amount', 'err'); return; }
  try {
    const r = await fetch(`/api/${GUILD_ID}/${TOKEN}/bet/place`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({prediction_id: predId, side, amount: parseInt(amount)})
    });
    const d = await r.json();
    if (d.success) { toast('Bet placed! 🎲'); document.getElementById('amt-'+predId).value=''; }
    else toast(d.error || 'Failed to place bet', 'err');
  } catch(e) { toast('Network error', 'err'); }
}

// Start prediction form
const startForm = document.getElementById('start-form');
if (startForm) {
  startForm.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = startForm.querySelector('.submit-btn');
    btn.disabled = true;
    try {
      const r = await fetch(`/api/${GUILD_ID}/${TOKEN}/prediction/start`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          streamer_id: document.getElementById('f-streamer').value,
          channel_id: document.getElementById('f-channel').value,
          question: document.getElementById('f-question').value,
          believe_answer: document.getElementById('f-believe').value,
          doubt_answer: document.getElementById('f-doubt').value,
          time_seconds: document.getElementById('f-time').value
        })
      });
      const d = await r.json();
      if (d.success) { toast('Prediction started! 🚀'); setTimeout(()=>location.reload(),1500); }
      else { toast(d.error || 'Failed', 'err'); btn.disabled = false; }
    } catch(e) { toast('Network error','err'); btn.disabled = false; }
  });
}

// Timers
function updateTimers() {
  document.querySelectorAll('[data-end]').forEach(el => {
    const end = new Date(el.dataset.end);
    const diff = Math.max(0, Math.floor((end - Date.now()) / 1000));
    const m = Math.floor(diff/60), s = diff%60;
    el.textContent = diff === 0 ? '🔒 Closed' : `⏰ ${m}:${s.toString().padStart(2,'0')}`;
    el.style.color = diff < 30 ? 'var(--accent2)' : 'var(--accent)';
  });
}
setInterval(updateTimers, 1000);
updateTimers();

// ── Confirm dialog ──
let _confirmCallback = null;
function confirmAction(type, predId, side, label) {
  _confirmCallback = { type, predId, side };
  const title = document.getElementById('confirm-title');
  const body = document.getElementById('confirm-body');
  const btn = document.getElementById('confirm-yes-btn');
  if (type === 'resolve') {
    title.textContent = `Resolve as "${label}"?`;
    body.textContent = 'Winners will receive their share of the losing pool. This cannot be undone.';
    btn.className = 'confirm-yes';
    btn.textContent = 'Resolve';
  } else {
    title.textContent = 'Refund & Cancel?';
    body.textContent = 'All bets will be returned to their owners. This cannot be undone.';
    btn.className = 'confirm-yes danger';
    btn.textContent = 'Refund All';
  }
  document.getElementById('confirm-overlay').classList.add('show');
}
function closeConfirm() {
  document.getElementById('confirm-overlay').classList.remove('show');
  _confirmCallback = null;
}
async function confirmExecute() {
  if (!_confirmCallback) return;
  const { type, predId, side } = _confirmCallback;
  closeConfirm();
  try {
    let url, body;
    if (type === 'resolve') {
      url = `/api/${GUILD_ID}/${TOKEN}/prediction/resolve`;
      body = { prediction_id: predId, winner: side };
    } else {
      url = `/api/${GUILD_ID}/${TOKEN}/prediction/refund`;
      body = { prediction_id: predId };
    }
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const d = await r.json();
    if (d.success) {
      toast(type === 'resolve' ? '🏆 Prediction resolved!' : '↩ Prediction refunded!');
      setTimeout(() => location.reload(), 1500);
    } else {
      toast(d.error || 'Action failed', 'err');
    }
  } catch(e) { toast('Network error', 'err'); }
}
// Close confirm on backdrop click
document.getElementById('confirm-overlay').addEventListener('click', function(e) {
  if (e.target === this) closeConfirm();
});

// WebSocket for live updates
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/${GUILD_ID}/${TOKEN}`);
  ws.onmessage = e => {
    const data = JSON.parse(e.data);
    for (const [id, pred] of Object.entries(data)) {
      updateCard(id, pred);
    }
    // Update counts
    document.getElementById('cnt-running').textContent = Object.keys(data).length;
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

function updateCard(id, pred) {
  const card = document.getElementById('card-'+id);
  if (!card) return;
  const set = (sel, val) => { const el = document.getElementById(sel+id); if(el) el.textContent = val; };
  set('bpct-', pred.believe_percentage+'%');
  set('dpct-', pred.doubt_percentage+'%');
  set('bpts-', pred.believe_points);
  set('dpts-', pred.doubt_points);
  set('btrs-', pred.total_bettors);
  const bb = document.getElementById('bbar-'+id);
  const db = document.getElementById('dbar-'+id);
  if(bb) bb.style.width = pred.believe_percentage+'%';
  if(db) db.style.width = pred.doubt_percentage+'%';
  card.dataset.status = pred.closed ? 'closed' : 'open';
  const betrow = document.getElementById('betrow-'+id);
  if(betrow && pred.closed) betrow.style.display = 'none';
}

connectWS();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  DATABASE HELPERS — store resolved/cancelled history
# ─────────────────────────────────────────────────────────────────────────────

def store_resolved_prediction(guild_id, prediction_id, prediction_data, winner_side, winning_pool):
    """Archive a resolved prediction"""
    data = dict(prediction_data)
    data['resolved'] = True
    data['winner'] = winner_side
    data['winning_pool'] = winning_pool
    data['resolved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    key = f"history:resolved:{guild_id}:{prediction_id}"
    db.redis.set(key, json.dumps(data))
    db.redis.sadd(f"history_resolved:{guild_id}", prediction_id)


def store_cancelled_prediction(guild_id, prediction_id, prediction_data):
    """Archive a cancelled/refunded prediction"""
    data = dict(prediction_data)
    data['cancelled'] = True
    data['resolved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    key = f"history:cancelled:{guild_id}:{prediction_id}"
    db.redis.set(key, json.dumps(data))
    db.redis.sadd(f"history_cancelled:{guild_id}", prediction_id)


def get_resolved_predictions(guild_id):
    """Get all resolved predictions for a guild"""
    ids = db.redis.smembers(f"history_resolved:{guild_id}")
    result = {}
    for pid in ids:
        raw = db.redis.get(f"history:resolved:{guild_id}:{pid}")
        if raw:
            result[pid] = json.loads(raw)
    return result


def get_cancelled_predictions(guild_id):
    """Get all cancelled predictions for a guild"""
    ids = db.redis.smembers(f"history_cancelled:{guild_id}")
    result = {}
    for pid in ids:
        raw = db.redis.get(f"history:cancelled:{guild_id}:{pid}")
        if raw:
            result[pid] = json.loads(raw)
    return result


def get_my_bets_history(guild_id, user_id):
    """Get all bets for a user across active + history predictions"""
    bets = []

    # Active predictions
    for pred_id, pred in db.get_all_guild_predictions(guild_id).items():
        bet = db.get_bet(guild_id, pred_id, user_id)
        if bet:
            status = 'closed' if pred.get('closed') else 'live'
            bets.append({
                'pred_id': pred_id,
                'question': pred['question'],
                'believe_answer': pred['believe_answer'],
                'doubt_answer': pred['doubt_answer'],
                'side': bet['side'],
                'amount': bet['amount'],
                'pred_status': status,
                'won': False,
                'payout': 0,
            })

    # Resolved — check if user won (we store payout info)
    for pred_id, pred in get_resolved_predictions(guild_id).items():
        bet_key = f"history_bet:{guild_id}:{pred_id}:{user_id}"
        raw = db.redis.get(bet_key)
        if raw:
            bet = json.loads(raw)
            winner = pred.get('winner')
            won = bet['side'] == winner
            payout = bet.get('payout', 0)
            bets.append({
                'pred_id': pred_id,
                'question': pred['question'],
                'believe_answer': pred['believe_answer'],
                'doubt_answer': pred['doubt_answer'],
                'side': bet['side'],
                'amount': bet['amount'],
                'pred_status': 'resolved',
                'won': won,
                'payout': payout,
            })

    # Cancelled
    for pred_id, pred in get_cancelled_predictions(guild_id).items():
        bet_key = f"history_bet:{guild_id}:{pred_id}:{user_id}"
        raw = db.redis.get(bet_key)
        if raw:
            bet = json.loads(raw)
            bets.append({
                'pred_id': pred_id,
                'question': pred['question'],
                'believe_answer': pred['believe_answer'],
                'doubt_answer': pred['doubt_answer'],
                'side': bet['side'],
                'amount': bet['amount'],
                'pred_status': 'cancelled',
                'won': False,
                'payout': 0,
            })

    return bets


def archive_bets(guild_id, prediction_id, winner_side=None):
    """Copy bets to persistent history storage before deleting active bets"""
    all_bets = db.get_all_bets(guild_id, prediction_id)
    for user_id, bet_data in all_bets.items():
        bet_key = f"history_bet:{guild_id}:{prediction_id}:{user_id}"
        entry = dict(bet_data)
        if winner_side is not None:
            entry['payout'] = bet_data.get('payout', 0)
        db.redis.set(bet_key, json.dumps(entry))


def format_pred_for_display(guild_id, user_id, pred_id, pred, all_bets=None):
    """Format prediction data for template rendering"""
    if all_bets is None:
        all_bets = db.get_all_bets(guild_id, pred_id)

    believe_points = sum(b['amount'] for b in all_bets.values() if b['side'] == 'believe')
    doubt_points = sum(b['amount'] for b in all_bets.values() if b['side'] == 'doubt')
    total = believe_points + doubt_points

    if total > 0:
        believe_pct = int((believe_points / total) * 100)
        doubt_pct = 100 - believe_pct
    else:
        believe_pct = doubt_pct = 50

    streamer_id = pred.get('streamer_id') or pred.get('creator_id', user_id)
    point_name = db.get_streamer_point_name(guild_id, streamer_id)

    # Resolve streamer display info
    streamer_name = f"User {streamer_id}"
    streamer_avatar = ''
    if bot_instance:
        guild = bot_instance.get_guild(guild_id)
        if guild:
            streamer_member = guild.get_member(streamer_id)
            if streamer_member:
                streamer_name = streamer_member.display_name
                streamer_avatar = str(streamer_member.display_avatar.url)

    # Determine if the viewing user can manage this prediction
    can_manage = False
    if bot_instance:
        guild = bot_instance.get_guild(guild_id)
        if guild:
            viewer = guild.get_member(user_id)
            if viewer:
                if viewer.guild_permissions.manage_messages:
                    can_manage = True
                elif viewer.id == streamer_id:
                    can_manage = True
                else:
                    can_manage = db.is_prediction_manager(guild_id, streamer_id, user_id)

    winner = pred.get('winner')
    winner_answer = None
    if winner == 'believe':
        winner_answer = pred.get('believe_answer', 'Believe')
    elif winner == 'doubt':
        winner_answer = pred.get('doubt_answer', 'Doubt')

    return {
        'question': pred.get('question', ''),
        'believe_answer': pred.get('believe_answer', 'Believe'),
        'doubt_answer': pred.get('doubt_answer', 'Doubt'),
        'believe_points': believe_points,
        'doubt_points': doubt_points,
        'believe_percentage': believe_pct,
        'doubt_percentage': doubt_pct,
        'point_name': point_name,
        'ending_timestamp': pred.get('end_time', ''),
        'closed': pred.get('closed', False),
        'resolved': pred.get('resolved', False),
        'winner': winner,
        'winner_answer': winner_answer,
        'winning_pool': pred.get('winning_pool', 0),
        'total_bettors': len(all_bets),
        'resolved_at': pred.get('resolved_at', ''),
        'streamer_id': streamer_id,
        'streamer_name': streamer_name,
        'streamer_avatar': streamer_avatar,
        'can_manage': can_manage,
        'start_time': pred.get('start_time', ''),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(403)
def forbidden(e):
    return render_template_string(ERROR_PAGE, error_code="403", error_title="Access Forbidden",
        error_message="Invalid or expired authentication token. Use /authtoken refresh in Discord."), 403

@app.errorhandler(404)
def not_found(e):
    return render_template_string(ERROR_PAGE, error_code="404", error_title="Not Found",
        error_message="The page or prediction you're looking for doesn't exist."), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template_string(ERROR_PAGE, error_code="500", error_title="Server Error",
        error_message="Something went wrong. Please try again later."), 500


@app.route('/')
def landing_page():
    return render_template_string(LANDING_PAGE)


@app.route('/favicon.ico')
def favicon():
    if bot_instance and bot_instance.user:
        return redirect(bot_instance.user.display_avatar.url)
    return abort(404)


@app.route('/<int:guild_id>', methods=['GET'])
def guild_token_page(guild_id):
    if not bot_instance:
        abort(500)
    guild = bot_instance.get_guild(guild_id)
    if not guild:
        abort(404)
    error = request.args.get('error')
    return render_template_string(GUILD_TOKEN_PAGE, guild_id=guild_id, guild_name=guild.name, error=error)


@app.route('/<int:guild_id>', methods=['POST'])
def guild_token_submit(guild_id):
    token = request.form.get('token', '').strip()
    if not token:
        return redirect(url_for('guild_token_page', guild_id=guild_id, error="Please enter your auth token"))
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        return redirect(url_for('guild_token_page', guild_id=guild_id, error="Invalid token for this server"))
    return redirect(url_for('dashboard', guild_id=guild_id, token=token))


@app.route('/<int:guild_id>/<token>')
def dashboard(guild_id, token):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    user_id = result[1]

    if not bot_instance:
        abort(500)
    guild = bot_instance.get_guild(guild_id)
    if not guild:
        abort(404)

    overlay = request.args.get('overlay') == '1'

    # ── Running predictions — sorted newest first by start_time ──
    running_raw = db.get_all_guild_predictions(guild_id)
    running_predictions = {
        pid: format_pred_for_display(guild_id, user_id, pid, pred)
        for pid, pred in sorted(
            running_raw.items(),
            key=lambda x: x[1].get('start_time', ''),
            reverse=True
        )
    }

    # ── Resolved predictions ──
    resolved_raw = get_resolved_predictions(guild_id)
    resolved_predictions = {}
    for pid, pred in sorted(resolved_raw.items(), key=lambda x: x[1].get('start_time', ''), reverse=True):
        resolved_predictions[pid] = format_pred_for_display(guild_id, user_id, pid, pred, all_bets={})

    # ── Cancelled predictions ──
    cancelled_raw = get_cancelled_predictions(guild_id)
    cancelled_predictions = {}
    for pid, pred in sorted(cancelled_raw.items(), key=lambda x: x[1].get('start_time', ''), reverse=True):
        cancelled_predictions[pid] = format_pred_for_display(guild_id, user_id, pid, pred, all_bets={})

    # ── My bets ──
    my_bets = get_my_bets_history(guild_id, user_id)

    # ── Start prediction eligibility ──
    can_start = False
    eligible_streamers = []
    channels = []
    predictions_cog = bot_instance.get_cog('Predictions')
    if predictions_cog:
        member = guild.get_member(user_id)
        if member:
            eligible = predictions_cog.get_eligible_streamers(guild, member)
            eligible_streamers = [{"id": s.id, "name": s.display_name} for s in eligible]
            can_start = bool(eligible_streamers)
    channels = [{"id": c.id, "name": c.name} for c in guild.text_channels]

    # Collect unique streamers across all tabs for filter UI
    seen = {}
    for pred in list(running_predictions.values()) + list(resolved_predictions.values()) + list(cancelled_predictions.values()):
        sid = pred.get('streamer_id')
        if sid and sid not in seen:
            seen[sid] = {'id': sid, 'name': pred.get('streamer_name', ''), 'avatar': pred.get('streamer_avatar', '')}
    all_streamers = sorted(seen.values(), key=lambda s: s['name'].lower())

    return render_template_string(
        MAIN_TEMPLATE,
        guild_id=guild_id,
        guild_name=guild.name,
        token=token,
        overlay=overlay,
        running_predictions=running_predictions,
        resolved_predictions=resolved_predictions,
        cancelled_predictions=cancelled_predictions,
        my_bets=my_bets,
        running_count=len(running_predictions),
        resolved_count=len(resolved_predictions),
        cancelled_count=len(cancelled_predictions),
        my_bets_count=len(my_bets),
        can_start=can_start,
        eligible_streamers=eligible_streamers,
        channels=channels,
        all_streamers=all_streamers,
    )


# ── Legacy single-prediction URL (redirect to dashboard) ──
@app.route('/<int:guild_id>/<token>/<prediction_id>')
def visual_single_prediction(guild_id, token, prediction_id):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    return redirect(url_for('dashboard', guild_id=guild_id, token=token))


# ─────────────────────────────────────────────────────────────────────────────
#  API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

def get_prediction_data(guild_id, user_id, prediction_id=None):
    """Return live prediction data for WS / API"""
    if not bot_instance:
        return None
    guild = bot_instance.get_guild(guild_id)
    if not guild:
        return None

    if prediction_id:
        raw = db.get_prediction(guild_id, prediction_id)
        if not raw:
            return None
        preds = {prediction_id: raw}
    else:
        preds = db.get_all_guild_predictions(guild_id)
        if not preds:
            return {}

    result = {}
    for pid, pred in preds.items():
        all_bets = db.get_all_bets(guild_id, pid)
        result[pid] = format_pred_for_display(guild_id, user_id, pid, pred, all_bets)
    return result


@app.route('/api/<int:guild_id>/<token>', methods=['GET'])
def api_all_predictions(guild_id, token):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    data = get_prediction_data(guild_id, result[1])
    return jsonify(data or {})


@app.route('/api/<int:guild_id>/<token>/<prediction_id>', methods=['GET'])
def api_single_prediction(guild_id, token, prediction_id):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    data = get_prediction_data(guild_id, result[1], prediction_id)
    if not data:
        abort(404)
    return jsonify(data.get(prediction_id, {}))


@app.route('/api/<int:guild_id>/<token>/prediction/start', methods=['POST'])
def api_start_prediction(guild_id, token):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    user_id = result[1]

    data = request.json if request.is_json else request.form
    streamer_id = data.get('streamer_id')
    channel_id = data.get('channel_id')
    question = data.get('question')
    believe_answer = data.get('believe_answer', 'Believe')
    doubt_answer = data.get('doubt_answer', 'Doubt')
    time_seconds = data.get('time_seconds', 300)

    if not all([streamer_id, channel_id, question]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        streamer_id = int(streamer_id)
        channel_id = int(channel_id)
        time_seconds = int(time_seconds)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numeric format"}), 400

    if not (10 <= time_seconds <= 3600):
        return jsonify({"error": "Time must be between 10 and 3600 seconds"}), 400

    guild = bot_instance.get_guild(guild_id)
    if not guild:
        return jsonify({"error": "Guild not found"}), 404

    member = guild.get_member(user_id)
    if not member:
        return jsonify({"error": "User not found"}), 404

    predictions_cog = bot_instance.get_cog('Predictions')
    if not predictions_cog:
        return jsonify({"error": "Predictions cog not loaded"}), 500

    eligible = predictions_cog.get_eligible_streamers(guild, member)
    if streamer_id not in [s.id for s in eligible]:
        return jsonify({"error": "Permission denied"}), 403

    future = asyncio.run_coroutine_threadsafe(
        predictions_cog.do_start_prediction(
            guild_id, channel_id, user_id, streamer_id,
            time_seconds, question, believe_answer, doubt_answer
        ),
        bot_instance.loop
    )
    try:
        prediction_id = future.result(timeout=10)
        return jsonify({"success": True, "prediction_id": prediction_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/<int:guild_id>/<token>/bet/place', methods=['POST'])
def api_place_bet(guild_id, token):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    user_id = result[1]

    data = request.json if request.is_json else request.form
    prediction_id = data.get('prediction_id')
    side = data.get('side')
    amount = data.get('amount')

    if not all([prediction_id, side, amount]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    if side not in ['believe', 'doubt']:
        return jsonify({"error": "Side must be believe or doubt"}), 400

    predictions_cog = bot_instance.get_cog('Predictions')
    if not predictions_cog:
        return jsonify({"error": "Cog not loaded"}), 500

    future = asyncio.run_coroutine_threadsafe(
        predictions_cog.do_place_bet(guild_id, user_id, prediction_id, side, amount),
        bot_instance.loop
    )
    try:
        success, message = future.result(timeout=10)
        if success:
            return jsonify({"success": True})
        return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
#  WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/<int:guild_id>/<token>/prediction/resolve', methods=['POST'])
def api_resolve_prediction(guild_id, token):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    user_id = result[1]

    data = request.json if request.is_json else request.form
    prediction_id = data.get('prediction_id')
    winner = data.get('winner')

    if not prediction_id or winner not in ('believe', 'doubt'):
        return jsonify({"error": "Missing prediction_id or invalid winner"}), 400

    if not bot_instance:
        return jsonify({"error": "Bot not available"}), 500

    guild = bot_instance.get_guild(guild_id)
    if not guild:
        return jsonify({"error": "Guild not found"}), 404

    prediction = db.get_prediction(guild_id, prediction_id)
    if not prediction:
        return jsonify({"error": "Prediction not found"}), 404

    if prediction.get('resolved'):
        return jsonify({"error": "Prediction already resolved"}), 400

    # Permission check
    viewer = guild.get_member(user_id)
    if not viewer:
        return jsonify({"error": "User not found"}), 404

    streamer_id = prediction.get('streamer_id') or prediction.get('creator_id')
    is_admin = viewer.guild_permissions.manage_messages
    is_streamer = viewer.id == streamer_id
    is_manager = db.is_prediction_manager(guild_id, streamer_id, user_id)
    if not (is_admin or is_streamer or is_manager):
        return jsonify({"error": "Permission denied"}), 403

    predictions_cog = bot_instance.get_cog('Predictions')
    if not predictions_cog:
        return jsonify({"error": "Predictions cog not loaded"}), 500

    # Build a minimal fake context object so the cog method can run
    class _FakeCtx:
        def __init__(self, guild, user):
            self.guild_id = guild.id
            self.guild = guild
            self.user = user
            self.author = user
            self._done = False
        async def response_defer(self): pass
        @property
        def response(self):
            class _R:
                is_done = lambda s: True
            return _R()
        @property
        def followup(self):
            class _FU:
                async def send(s, *a, **kw): pass
            return _FU()
        async def defer(self): pass
        async def respond(self, *a, **kw): pass

    fake_ctx = _FakeCtx(guild, viewer)

    future = asyncio.run_coroutine_threadsafe(
        predictions_cog.resolve_prediction(fake_ctx, prediction_id, winner),
        bot_instance.loop
    )
    try:
        future.result(timeout=10)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/<int:guild_id>/<token>/prediction/refund', methods=['POST'])
def api_refund_prediction(guild_id, token):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)
    user_id = result[1]

    data = request.json if request.is_json else request.form
    prediction_id = data.get('prediction_id')

    if not prediction_id:
        return jsonify({"error": "Missing prediction_id"}), 400

    if not bot_instance:
        return jsonify({"error": "Bot not available"}), 500

    guild = bot_instance.get_guild(guild_id)
    if not guild:
        return jsonify({"error": "Guild not found"}), 404

    prediction = db.get_prediction(guild_id, prediction_id)
    if not prediction:
        return jsonify({"error": "Prediction not found"}), 404

    # Permission check
    viewer = guild.get_member(user_id)
    if not viewer:
        return jsonify({"error": "User not found"}), 404

    streamer_id = prediction.get('streamer_id') or prediction.get('creator_id')
    is_admin = viewer.guild_permissions.manage_messages
    is_streamer = viewer.id == streamer_id
    is_manager = db.is_prediction_manager(guild_id, streamer_id, user_id)
    if not (is_admin or is_streamer or is_manager):
        return jsonify({"error": "Permission denied"}), 403

    predictions_cog = bot_instance.get_cog('Predictions')
    if not predictions_cog:
        return jsonify({"error": "Predictions cog not loaded"}), 500

    class _FakeCtx:
        def __init__(self, guild, user):
            self.guild_id = guild.id
            self.guild = guild
            self.user = user
            self.author = user
        @property
        def response(self):
            class _R:
                is_done = lambda s: True
            return _R()
        @property
        def followup(self):
            class _FU:
                async def send(s, *a, **kw): pass
            return _FU()
        async def defer(self): pass
        async def respond(self, *a, **kw): pass

    fake_ctx = _FakeCtx(guild, viewer)

    future = asyncio.run_coroutine_threadsafe(
        predictions_cog.refund_prediction(fake_ctx, prediction_id),
        bot_instance.loop
    )
    try:
        future.result(timeout=10)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sock.route('/ws/<int:guild_id>/<token>')
def ws_all_predictions(ws, guild_id, token):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        return
    user_id = result[1]
    while True:
        try:
            data = get_prediction_data(guild_id, user_id)
            ws.send(json.dumps(data or {}))
            time.sleep(2)
        except Exception:
            break


@sock.route('/ws/<int:guild_id>/<token>/<prediction_id>')
def ws_single_prediction(ws, guild_id, token, prediction_id):
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        return
    user_id = result[1]
    while True:
        try:
            data = get_prediction_data(guild_id, user_id, prediction_id)
            if data and prediction_id in data:
                ws.send(json.dumps(data[prediction_id]))
            time.sleep(2)
        except Exception:
            break


# ─────────────────────────────────────────────────────────────────────────────
#  RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_web_server(host='0.0.0.0', port=5000):
    app.run(host=host, port=port, threaded=True)
