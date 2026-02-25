from flask import Flask, jsonify, render_template_string, abort, request, redirect, url_for
from flask_sock import Sock
from datetime import datetime
import json
import time
import asyncio
from database import db
import discord

app = Flask(__name__)
sock = Sock(app)

# Store bot reference
bot_instance = None


def init_web_server(bot):
    """Initialize the web server with bot reference"""
    global bot_instance
    bot_instance = bot


# Landing page HTML
LANDING_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Prediction Bot - Web UI</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 20px;
            padding: 60px;
            max-width: 700px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            text-align: center;
        }

        h1 {
            color: #667eea;
            font-size: 48px;
            margin-bottom: 20px;
            font-weight: bold;
        }

        .subtitle {
            color: #666;
            font-size: 20px;
            margin-bottom: 40px;
        }

        .step {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin-bottom: 20px;
            text-align: left;
            border-radius: 8px;
        }

        .step-number {
            display: inline-block;
            background: #667eea;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            text-align: center;
            line-height: 30px;
            margin-right: 10px;
            font-weight: bold;
        }

        .step-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
            color: #333;
        }

        .step-description {
            color: #666;
            line-height: 1.6;
        }

        .command {
            background: #2c3e50;
            color: #2ecc71;
            padding: 10px 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            display: inline-block;
            margin: 10px 0;
            font-size: 16px;
        }

        .button {
            background: #667eea;
            color: white;
            padding: 15px 40px;
            border: none;
            border-radius: 30px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 30px;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
        }

        .button:hover {
            background: #764ba2;
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }

        .info-box {
            background: #e3f2fd;
            border: 1px solid #2196f3;
            border-radius: 8px;
            padding: 20px;
            margin-top: 30px;
            color: #1976d2;
        }

        .info-box strong {
            display: block;
            margin-bottom: 10px;
            font-size: 18px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎲 Prediction Bot</h1>
        <p class="subtitle">Web UI & API Access</p>

        <div class="step">
            <div class="step-number">1</div>
            <div class="step-title">Generate Your Auth Token</div>
            <div class="step-description">
                In Discord, use the command to generate a secure authentication token:
                <br><span class="command">/authtoken refresh</span>
                <br>The bot will send your token via DM. Keep it secret!
            </div>
        </div>

        <div class="step">
            <div class="step-number">2</div>
            <div class="step-title">Get Your Web UI Link</div>
            <div class="step-description">
                In your Discord server, use this command to get your personalized web UI link:
                <br><span class="command">/webui</span>
                <br>This will give you a link specific to your server.
            </div>
        </div>

        <div class="step">
            <div class="step-number">3</div>
            <div class="step-title">Access Your Predictions</div>
            <div class="step-description">
                Visit the link provided and enter your auth token to view your predictions in real-time!
            </div>
        </div>

        <div class="info-box">
            <strong>🔒 Security Note</strong>
            Never share your auth token with anyone. It provides access to view your predictions and should be treated like a password.
        </div>
    </div>
</body>
</html>
"""

# Guild token entry page
GUILD_TOKEN_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Enter Token - {{ guild_name }}</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 20px;
            padding: 50px;
            max-width: 600px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }

        h1 {
            color: #667eea;
            font-size: 36px;
            margin-bottom: 10px;
            text-align: center;
        }

        .guild-name {
            color: #666;
            font-size: 20px;
            margin-bottom: 40px;
            text-align: center;
        }

        .form-group {
            margin-bottom: 25px;
        }

        label {
            display: block;
            color: #333;
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 16px;
        }

        input[type="password"] {
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            font-family: 'Courier New', monospace;
            transition: border-color 0.3s ease;
        }

        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }

        .submit-btn {
            width: 100%;
            background: #667eea;
            color: white;
            padding: 15px;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .submit-btn:hover {
            background: #764ba2;
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }

        .help-text {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin-top: 25px;
            border-radius: 5px;
            color: #666;
            font-size: 14px;
        }

        .help-text strong {
            color: #667eea;
        }

        .error {
            background: #ffebee;
            border: 1px solid #f44336;
            color: #c62828;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }

        .command {
            background: #2c3e50;
            color: #2ecc71;
            padding: 5px 10px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔑 Enter Your Token</h1>
        <p class="guild-name">{{ guild_name }}</p>

        {% if error %}
        <div class="error">
            {{ error }}
        </div>
        {% endif %}

        <form method="POST" action="{{ url_for('guild_token_submit', guild_id=guild_id) }}">
            <div class="form-group">
                <label for="token">Auth Token:</label>
                <input type="password" id="token" name="token" placeholder="Paste your auth token here..." required autocomplete="off">
            </div>

            <button type="submit" class="submit-btn">🚀 Access Predictions</button>
        </form>

        <div class="help-text">
            <strong>Don't have a token?</strong><br>
            In Discord, use <span class="command">/authtoken refresh</span> in {{ guild_name }} to generate one. The bot will DM it to you.
        </div>
    </div>
</body>
</html>
"""

# Error page HTML
ERROR_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ error_code }} - Error</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 20px;
            padding: 60px;
            max-width: 600px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }

        .error-code {
            font-size: 120px;
            font-weight: bold;
            color: #667eea;
            line-height: 1;
            margin-bottom: 20px;
        }

        h1 {
            color: #333;
            font-size: 32px;
            margin-bottom: 20px;
        }

        p {
            color: #666;
            font-size: 18px;
            line-height: 1.6;
            margin-bottom: 30px;
        }

        .button {
            background: #667eea;
            color: white;
            padding: 15px 40px;
            border: none;
            border-radius: 30px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
        }

        .button:hover {
            background: #764ba2;
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="error-code">{{ error_code }}</div>
        <h1>{{ error_title }}</h1>
        <p>{{ error_message }}</p>
        <a href="/" class="button">← Go Home</a>
    </div>
</body>
</html>
"""

# HTML template for visual display (same as before)
VISUAL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Predictions - {{guild_name}}</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background-color: #00FF00; /* Green for chroma key */
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 20px;
        }

        .prediction-card {
            background: rgba(0, 0, 0, 0.85);
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        }

        .question {
            color: #ffffff;
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 30px;
            text-align: center;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
        }

        .prediction-id {
            color: #888;
            font-size: 14px;
            text-align: center;
            margin-bottom: 20px;
        }

        .progress-container {
            width: 100%;
            height: 60px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 30px;
            overflow: hidden;
            position: relative;
            margin-bottom: 20px;
        }

        .progress-bar {
            height: 100%;
            display: flex;
            transition: all 0.5s ease;
        }

        .believe-bar {
            background: linear-gradient(90deg, #4A90E2, #5BA3F5);
            display: flex;
            align-items: center;
            justify-content: flex-start;
            padding-left: 20px;
        }

        .doubt-bar {
            background: linear-gradient(90deg, #E24A90, #F55BA3);
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 20px;
        }

        .bar-label {
            color: white;
            font-weight: bold;
            font-size: 18px;
            text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.8);
        }

        .answers-container {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
        }

        .answer {
            flex: 1;
            padding: 15px;
            border-radius: 10px;
            margin: 0 10px;
        }

        .believe-answer {
            background: rgba(74, 144, 226, 0.2);
            border: 2px solid #4A90E2;
            color: #5BA3F5;
            text-align: left;
        }

        .doubt-answer {
            background: rgba(226, 74, 144, 0.2);
            border: 2px solid #E24A90;
            color: #F55BA3;
            text-align: right;
        }

        .answer-label {
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 5px;
            opacity: 0.8;
        }

        .answer-text {
            font-size: 20px;
            font-weight: bold;
        }

        .stats {
            display: flex;
            justify-content: space-around;
            color: #ffffff;
            margin-top: 20px;
        }

        .stat {
            text-align: center;
        }

        .stat-label {
            font-size: 12px;
            color: #888;
            margin-bottom: 5px;
        }

        .stat-value {
            font-size: 24px;
            font-weight: bold;
        }

        .timer {
            text-align: center;
            color: #FFD700;
            font-size: 32px;
            font-weight: bold;
            margin-top: 20px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
        }

        .closed-badge {
            background: #FF6B6B;
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            display: inline-block;
            margin-bottom: 20px;
            font-weight: bold;
        }

        .point-name {
            color: #FFD700;
            font-size: 16px;
            text-align: center;
            margin-top: 10px;
        }

        /* Management UI Styles */
        .management-container {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 15px;
            padding: 20px;
            margin-top: 20px;
            color: #333;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        }

        .management-title {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 15px;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 5px;
        }

        .form-group {
            margin-bottom: 15px;
        }

        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            font-size: 14px;
        }

        .form-group input, .form-group select {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #ccc;
            border-radius: 5px;
            font-size: 14px;
        }

        .submit-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            font-weight: bold;
            cursor: pointer;
            width: 100%;
            transition: background 0.3s;
        }

        .submit-btn:hover {
            background: #764ba2;
        }

        .bet-buttons {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }

        .bet-btn {
            flex: 1;
            padding: 10px;
            border: none;
            border-radius: 5px;
            font-weight: bold;
            cursor: pointer;
            color: white;
        }

        .believe-btn { background-color: #4A90E2; }
        .believe-btn:hover { background-color: #357ABD; }
        .doubt-btn { background-color: #E24A90; }
        .doubt-btn:hover { background-color: #BD3576; }

        .manage-toggle {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border-radius: 30px;
            text-decoration: none;
            font-weight: bold;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            z-index: 1000;
        }

        .overlay-bg {
            background-color: transparent !important;
        }
        
        #message-box {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            padding: 15px 30px;
            border-radius: 10px;
            color: white;
            font-weight: bold;
            z-index: 2000;
            display: none;
        }
        .success { background-color: #2ecc71; }
        .error { background-color: #e74c3c; }
    </style>
    <script>
        function updateTimers() {
            document.querySelectorAll('[data-end-time]').forEach(el => {
                const endTimeStr = el.dataset.endTime;
                if (!endTimeStr) return;
                const endTime = new Date(endTimeStr);
                const now = new Date();
                const diff = Math.max(0, Math.floor((endTime - now) / 1000));

                const minutes = Math.floor(diff / 60);
                const seconds = diff % 60;
                
                if (diff === 0) {
                    el.textContent = "🔒 CLOSED";
                    el.style.color = "#FF6B6B";
                } else {
                    el.textContent = `⏰ ${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                    el.style.color = "#FFD700";
                }
            });
        }

        function updatePrediction(id, pred) {
            const card = document.getElementById(`card-${id}`);
            if (!card) return;

            // Update closed badge
            const closedContainer = document.getElementById(`closed-container-${id}`);
            if (closedContainer) {
                if (pred.closed) {
                    if (!closedContainer.innerHTML.trim()) {
                        closedContainer.innerHTML = '<span class="closed-badge">BETTING CLOSED</span>';
                    }
                } else {
                    closedContainer.innerHTML = '';
                }
            }

            // Update question and answers
            const questionEl = document.getElementById(`question-${id}`);
            if (questionEl) questionEl.textContent = pred.question;
            
            const bAnswerEl = document.getElementById(`believe-answer-${id}`);
            if (bAnswerEl) bAnswerEl.textContent = pred.believe_answer;
            
            const dAnswerEl = document.getElementById(`doubt-answer-${id}`);
            if (dAnswerEl) dAnswerEl.textContent = pred.doubt_answer;

            // Update bars
            const bBar = document.getElementById(`believe-bar-${id}`);
            const dBar = document.getElementById(`doubt-bar-${id}`);
            const bPct = document.getElementById(`believe-pct-${id}`);
            const dPct = document.getElementById(`doubt-pct-${id}`);

            if (bBar) bBar.style.width = `${pred.believe_percentage}%`;
            if (dBar) dBar.style.width = `${pred.doubt_percentage}%`;
            if (bPct) bPct.textContent = `${pred.believe_percentage}%`;
            if (dPct) dPct.textContent = `${pred.doubt_percentage}%`;

            // Update stats
            const bPoints = document.getElementById(`believe-points-${id}`);
            if (bPoints) bPoints.textContent = pred.believe_points;
            
            const dPoints = document.getElementById(`doubt-points-${id}`);
            if (dPoints) dPoints.textContent = pred.doubt_points;
            
            const totalB = document.getElementById(`total-bettors-${id}`);
            if (totalB) totalB.textContent = pred.total_bettors;
            
            const pName = document.getElementById(`point-name-${id}`);
            if (pName) pName.textContent = `Currency: ${pred.point_name}`;

            // Update management UI visibility
            const mgmt = document.getElementById(`mgmt-${id}`);
            if (mgmt) {
                if (pred.closed || pred.finished) {
                    mgmt.style.display = 'none';
                } else {
                    mgmt.style.display = 'block';
                }
            }

            // Update timer
            const timer = document.getElementById(`timer-${id}`);
            if (timer) {
                if (pred.closed) {
                    timer.style.display = 'none';
                } else {
                    timer.style.display = 'block';
                    timer.dataset.endTime = pred.ending_timestamp;
                }
            }
        }

        // WebSocket setup
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const guild_id = "{{ guild_id }}";
        const token = "{{ token }}";
        const prediction_id = "{{ prediction_id | default('') }}";
        
        let wsUrl = `${protocol}//${window.location.host}/ws/${guild_id}/${token}`;
        if (prediction_id) {
            wsUrl += `/${prediction_id}`;
        }
        
        function connectWS() {
            const socket = new WebSocket(wsUrl);
            
            socket.onmessage = function(event) {
                const data = JSON.parse(event.data);
                if (prediction_id) {
                    updatePrediction(prediction_id, data);
                } else {
                    for (const [id, pred] of Object.entries(data)) {
                        updatePrediction(id, pred);
                    }
                }
            };

            socket.onclose = function() {
                console.log('WebSocket closed, reconnecting...');
                setTimeout(connectWS, 2000); // Reconnect after 2 seconds
            };

            socket.onerror = function(err) {
                console.error('WebSocket error:', err);
                socket.close();
            };
        }

        setInterval(updateTimers, 1000);
        
        window.onload = function() {
            updateTimers();
            connectWS();
        };

        async function submitForm(url, data, successMsg) {
            const msgBox = document.getElementById('message-box');
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                
                msgBox.textContent = result.success ? successMsg : (result.error || 'Something went wrong');
                msgBox.className = result.success ? 'success' : 'error';
                msgBox.style.display = 'block';
                
                if (result.success) {
                    if (data.prediction_id) {
                        // Clear bet amount after success
                        const amtInput = document.getElementById(`amount-${data.prediction_id}`);
                        if (amtInput) amtInput.value = '';
                    } else {
                        // Redirect or refresh after starting prediction
                        setTimeout(() => window.location.reload(), 1500);
                    }
                }
            } catch (err) {
                msgBox.textContent = 'Network error occurred';
                msgBox.className = 'error';
                msgBox.style.display = 'block';
            }
            setTimeout(() => { msgBox.style.display = 'none'; }, 3000);
        }

        function placeBet(predId, side) {
            const amount = document.getElementById(`amount-${predId}`).value;
            if (!amount || amount <= 0) {
                alert('Please enter a valid amount');
                return;
            }
            submitForm(`/api/{{guild_id}}/{{token}}/bet/place`, {
                prediction_id: predId,
                side: side,
                amount: parseInt(amount)
            }, 'Bet placed successfully!');
        }
    </script>
</head>
<body class="{% if not manage %}overlay-bg{% endif %}">
    <div id="message-box"></div>
    
    {% if manage %}
        <a href="?manage=0" class="manage-toggle">📺 Overlay Mode</a>
        
        {% if not single_prediction and eligible_streamers %}
        <div class="management-container" style="max-width: 800px; margin: 0 auto 30px auto;">
            <div class="management-title">➕ Start New Prediction</div>
            <form onsubmit="event.preventDefault(); submitForm('/api/{{guild_id}}/{{token}}/prediction/start', {
                streamer_id: document.getElementById('new-streamer').value,
                channel_id: document.getElementById('new-channel').value,
                question: document.getElementById('new-question').value,
                believe_answer: document.getElementById('new-believe').value,
                doubt_answer: document.getElementById('new-doubt').value,
                time_seconds: document.getElementById('new-time').value
            }, 'Prediction started!');">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                    <div class="form-group">
                        <label>Streamer:</label>
                        <select id="new-streamer">
                            {% for s in eligible_streamers %}
                            <option value="{{ s.id }}">{{ s.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Post to Channel:</label>
                        <select id="new-channel">
                            {% for c in channels %}
                            <option value="{{ c.id }}">#{{ c.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label>Question:</label>
                    <input type="text" id="new-question" placeholder="e.g. Will we win this game?" required>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px;">
                    <div class="form-group">
                        <label>Believe Answer:</label>
                        <input type="text" id="new-believe" value="Believe">
                    </div>
                    <div class="form-group">
                        <label>Doubt Answer:</label>
                        <input type="text" id="new-doubt" value="Doubt">
                    </div>
                    <div class="form-group">
                        <label>Duration (sec):</label>
                        <input type="number" id="new-time" value="300" min="10" max="3600">
                    </div>
                </div>
                <button type="submit" class="submit-btn">🚀 Start Prediction</button>
            </form>
        </div>
        {% endif %}
    {% else %}
        <a href="?manage=1" class="manage-toggle">⚙️ Interactive Mode</a>
    {% endif %}

    {% macro render_prediction(prediction, pred_id) %}
<div class="prediction-card" id="card-{{ pred_id }}">
    <div class="prediction-id"><a href="/{{ guild_id }}/{{ token }}/{{ pred_id }}{% if manage %}?manage=1{% endif %}" style="color: #888; text-decoration: none;">ID: {{ pred_id }}</a></div>

    <div id="closed-container-{{ pred_id }}" style="text-align: center;">
    {% if prediction.closed %}
        <span class="closed-badge">BETTING CLOSED</span>
    {% endif %}
    </div>

    <div class="question" id="question-{{ pred_id }}">{{ prediction.question }}</div>

    <div class="answers-container">
        <div class="answer believe-answer">
            <div class="answer-label">✅ Believe</div>
            <div class="answer-text" id="believe-answer-{{ pred_id }}">{{ prediction.believe_answer }}</div>
        </div>
        <div class="answer doubt-answer">
            <div class="answer-label">❌ Doubt</div>
            <div class="answer-text" id="doubt-answer-{{ pred_id }}">{{ prediction.doubt_answer }}</div>
        </div>
    </div>

    <div class="progress-container">
        <div class="progress-bar">
            <div class="believe-bar" id="believe-bar-{{ pred_id }}" style="width: {{ prediction.believe_percentage }}%;">
                <span class="bar-label" id="believe-pct-{{ pred_id }}">{{ prediction.believe_percentage }}%</span>
            </div>
            <div class="doubt-bar" id="doubt-bar-{{ pred_id }}" style="width: {{ prediction.doubt_percentage }}%;">
                <span class="bar-label" id="doubt-pct-{{ pred_id }}">{{ prediction.doubt_percentage }}%</span>
            </div>
        </div>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="stat-label">Believe Bets</div>
            <div class="stat-value" id="believe-points-{{ pred_id }}" style="color: #5BA3F5;">{{ prediction.believe_points }}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Total Bettors</div>
            <div class="stat-value" id="total-bettors-{{ pred_id }}">{{ prediction.total_bettors }}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Doubt Bets</div>
            <div class="stat-value" id="doubt-points-{{ pred_id }}" style="color: #F55BA3;">{{ prediction.doubt_points }}</div>
        </div>
    </div>

    <div class="point-name" id="point-name-{{ pred_id }}">Currency: {{ prediction.point_name }}</div>

    {% if manage %}
    <div class="management-container" id="mgmt-{{ pred_id }}" style="{% if prediction.closed or prediction.finished %}display: none;{% endif %}">
        <div class="management-title">💸 Place a Bet</div>
        <div class="form-group">
            <label>Amount:</label>
            <input type="number" id="amount-{{ pred_id }}" placeholder="Enter amount..." min="1">
        </div>
        <div class="bet-buttons">
            <button class="bet-btn believe-btn" onclick="placeBet('{{ pred_id }}', 'believe')">✅ {{ prediction.believe_answer }}</button>
            <button class="bet-btn doubt-btn" onclick="placeBet('{{ pred_id }}', 'doubt')">❌ {{ prediction.doubt_answer }}</button>
        </div>
    </div>
    {% endif %}

    <div class="timer" id="timer-{{ pred_id }}" data-end-time="{{ prediction.ending_timestamp }}" style="{% if prediction.closed %}display: none;{% endif %}">
        ⏰ Calculating...
    </div>
</div>
{% endmacro %}

    {% if single_prediction %}
        <a href="/{{ guild_id }}/{{ token }}{% if manage %}?manage=1{% endif %}" style="display: block; margin-bottom: 20px; color: #667eea; text-decoration: none; font-weight: bold; background: white; padding: 10px; border-radius: 10px; text-align: center;">← Back to All Predictions</a>
        {{ render_prediction(single_prediction, prediction_ids[0]) }}
    {% else %}
        {% for pred_id, prediction in predictions.items() %}
            {{ render_prediction(prediction, pred_id) }}
        {% endfor %}
    {% endif %}
</body>
</html>
"""


def get_prediction_data(guild_id: int, user_id: int, prediction_id: str = None):
    """Get prediction data formatted for API/UI"""
    if not bot_instance:
        return None

    guild = bot_instance.get_guild(guild_id)
    if not guild:
        return None

    # Get all predictions for this guild
    if prediction_id:
        predictions_dict = {prediction_id: db.get_prediction(guild_id, prediction_id)}
        if not predictions_dict[prediction_id]:
            return None
    else:
        predictions_dict = db.get_all_guild_predictions(guild_id)

    if not predictions_dict:
        return None

    # Get user (streamer) to find point name
    user = guild.get_member(user_id)
    if not user:
        return None

    point_name = db.get_streamer_point_name(guild_id, user_id)

    result = {}
    for pred_id, prediction in predictions_dict.items():
        if not prediction:
            continue

        # Get all bets
        all_bets = db.get_all_bets(guild_id, pred_id)

        # Calculate totals
        believe_points = sum(bet['amount'] for bet in all_bets.values() if bet['side'] == 'believe')
        doubt_points = sum(bet['amount'] for bet in all_bets.values() if bet['side'] == 'doubt')

        # Get members who bet
        members_list = []
        for bet_user_id in all_bets.keys():
            bet_user = guild.get_member(bet_user_id)
            if bet_user:
                members_list.append({
                    "userId": bet_user_id,
                    "userName": bet_user.display_name
                })

        # Calculate percentages
        total = believe_points + doubt_points
        if total > 0:
            believe_pct = int((believe_points / total) * 100)
            doubt_pct = 100 - believe_pct
        else:
            believe_pct = doubt_pct = 50

        result[pred_id] = {
            "question": prediction['question'],
            "believe_answer": prediction['believe_answer'],
            "doubt_answer": prediction['doubt_answer'],
            "believe_points": believe_points,
            "doubt_points": doubt_points,
            "believe_percentage": believe_pct,
            "doubt_percentage": doubt_pct,
            "point_name": point_name,
            "ending_timestamp": prediction['end_time'],
            "closed": prediction.get('closed', False),
            "members": members_list,
            "finished": prediction.get('resolved', False),
            "total_bettors": len(all_bets)
        }

    return result


# Error handlers
@app.errorhandler(403)
def forbidden(e):
    return render_template_string(ERROR_PAGE,
                                  error_code="403",
                                  error_title="Access Forbidden",
                                  error_message="Invalid or expired authentication token. Please use /authtoken refresh in Discord to get a new token."
                                  ), 403


@app.errorhandler(404)
def not_found(e):
    return render_template_string(ERROR_PAGE,
                                  error_code="404",
                                  error_title="Not Found",
                                  error_message="The page or prediction you're looking for doesn't exist. Make sure you're using the correct link from /webui command."
                                  ), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template_string(ERROR_PAGE,
                                  error_code="500",
                                  error_title="Internal Server Error",
                                  error_message="Something went wrong on our end. Please try again later."
                                  ), 500


# Routes
@app.route('/', methods=['GET'])
def landing_page():
    """Main landing page with instructions"""
    return render_template_string(LANDING_PAGE)


@app.route('/favicon.ico')
def favicon():
    """Favicon redirect to bot's avatar"""
    if bot_instance and bot_instance.user:
        return redirect(bot_instance.user.display_avatar.url)
    return abort(404)


@app.route('/<int:guild_id>', methods=['GET'])
def guild_token_page(guild_id):
    """Token entry page for specific guild"""
    if not bot_instance:
        abort(500)

    guild = bot_instance.get_guild(guild_id)
    if not guild:
        abort(404)

    error = request.args.get('error')

    return render_template_string(GUILD_TOKEN_PAGE,
                                  guild_id=guild_id,
                                  guild_name=guild.name,
                                  error=error
                                  )


@app.route('/<int:guild_id>', methods=['POST'])
def guild_token_submit(guild_id):
    """Handle token submission"""
    token = request.form.get('token', '').strip()

    if not token:
        return redirect(url_for('guild_token_page', guild_id=guild_id, error="Please enter your auth token"))

    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        return redirect(url_for('guild_token_page', guild_id=guild_id, error="Invalid token for this server"))

    # Redirect to predictions view
    return redirect(url_for('visual_all_predictions', guild_id=guild_id, token=token))


@app.route('/api/<int:guild_id>/<token>', methods=['GET'])
def api_all_predictions(guild_id, token):
    """API endpoint for all predictions"""
    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)

    user_id = result[1]

    data = get_prediction_data(guild_id, user_id)
    if data is None:
        abort(404)

    return jsonify(data)


@app.route('/api/<int:guild_id>/<token>/<prediction_id>', methods=['GET'])
def api_single_prediction(guild_id, token, prediction_id):
    """API endpoint for single prediction"""
    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)

    user_id = result[1]

    data = get_prediction_data(guild_id, user_id, prediction_id)
    if data is None or prediction_id not in data:
        abort(404)

    # Return single prediction without wrapper
    return jsonify(data[prediction_id])


@sock.route('/ws/<int:guild_id>/<token>')
def ws_all_predictions(ws, guild_id, token):
    """WebSocket for all predictions"""
    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        return

    user_id = result[1]

    while True:
        try:
            data = get_prediction_data(guild_id, user_id)
            if data:
                ws.send(json.dumps(data))
            time.sleep(2)
        except Exception:
            break


@sock.route('/ws/<int:guild_id>/<token>/<prediction_id>')
def ws_single_prediction(ws, guild_id, token, prediction_id):
    """WebSocket for single prediction"""
    # Verify token
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


@app.route('/<int:guild_id>/<token>', methods=['GET'])
def visual_all_predictions(guild_id, token):
    """Visual UI for all predictions"""
    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)

    user_id = result[1]

    data = get_prediction_data(guild_id, user_id)
    if data is None:
        data = {}

    guild = bot_instance.get_guild(guild_id)
    guild_name = guild.name if guild else f"Guild {guild_id}"

    # Get management data
    manage = request.args.get('manage') == '1'
    eligible_streamers = []
    channels = []
    user_points = {}
    
    if manage:
        predictions_cog = bot_instance.get_cog('Predictions')
        if predictions_cog:
            member = guild.get_member(user_id)
            if member:
                eligible = predictions_cog.get_eligible_streamers(guild, member)
                eligible_streamers = [{"id": s.id, "name": s.display_name} for s in eligible]
        
        channels = [{"id": c.id, "name": c.name} for c in guild.text_channels]
        user_points = db.get_all_user_points(guild_id, user_id)

    return render_template_string(
        VISUAL_TEMPLATE,
        predictions=data,
        prediction_ids=list(data.keys()),
        guild_name=guild_name,
        single_prediction=False,
        guild_id=guild_id,
        token=token,
        manage=manage,
        eligible_streamers=eligible_streamers,
        channels=channels,
        user_points=user_points
    )


@app.route('/<int:guild_id>/<token>/<prediction_id>', methods=['GET'])
def visual_single_prediction(guild_id, token, prediction_id):
    """Visual UI for single prediction"""
    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)

    user_id = result[1]

    data = get_prediction_data(guild_id, user_id, prediction_id)
    if data is None or prediction_id not in data:
        abort(404)

    guild = bot_instance.get_guild(guild_id)
    guild_name = guild.name if guild else f"Guild {guild_id}"

    # Get management data
    manage = request.args.get('manage') == '1'
    eligible_streamers = []
    channels = []
    user_points = {}
    
    if manage:
        predictions_cog = bot_instance.get_cog('Predictions')
        if predictions_cog:
            member = guild.get_member(user_id)
            if member:
                eligible = predictions_cog.get_eligible_streamers(guild, member)
                eligible_streamers = [{"id": s.id, "name": s.display_name} for s in eligible]
        
        channels = [{"id": c.id, "name": c.name} for c in guild.text_channels]
        user_points = db.get_all_user_points(guild_id, user_id)

    return render_template_string(
        VISUAL_TEMPLATE,
        single_prediction=data[prediction_id],
        prediction_ids=[prediction_id],
        guild_name=guild_name,
        guild_id=guild_id,
        token=token,
        prediction_id=prediction_id,
        manage=manage,
        eligible_streamers=eligible_streamers,
        channels=channels,
        user_points=user_points
    )


@app.route('/api/<int:guild_id>/<token>/prediction/start', methods=['POST'])
def api_start_prediction(guild_id, token):
    """API endpoint to start a new prediction"""
    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)

    user_id = result[1]
    
    # Get data from JSON or Form
    if request.is_json:
        data = request.json
    else:
        data = request.form

    streamer_id = data.get('streamer_id')
    channel_id = data.get('channel_id')
    question = data.get('question')
    believe_answer = data.get('believe_answer', 'Believe')
    doubt_answer = data.get('doubt_answer', 'Doubt')
    time_seconds = data.get('time_seconds', 300)

    if not all([streamer_id, channel_id, question]):
        return jsonify({"error": "Missing required fields (streamer_id, channel_id, question)"}), 400

    try:
        streamer_id = int(streamer_id)
        channel_id = int(channel_id)
        time_seconds = int(time_seconds)
    except ValueError:
        return jsonify({"error": "Invalid numeric format"}), 400

    if not (10 <= time_seconds <= 3600):
        return jsonify({"error": "Time must be between 10 and 3600 seconds"}), 400

    guild = bot_instance.get_guild(guild_id)
    if not guild:
        return jsonify({"error": "Guild not found"}), 404

    user = guild.get_member(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    predictions_cog = bot_instance.get_cog('Predictions')
    if not predictions_cog:
        return jsonify({"error": "Predictions cog not loaded"}), 500

    # Check eligibility
    eligible = predictions_cog.get_eligible_streamers(guild, user)
    if streamer_id not in [s.id for s in eligible]:
        return jsonify({"error": "You don't have permission to start predictions for this streamer"}), 403

    # Call the cog method in the event loop
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
    """API endpoint to place a bet"""
    # Verify token
    result = db.verify_auth_token(token)
    if not result or result[0] != guild_id:
        abort(403)

    user_id = result[1]
    
    # Get data from JSON or Form
    if request.is_json:
        data = request.json
    else:
        data = request.form

    prediction_id = data.get('prediction_id')
    side = data.get('side')
    amount = data.get('amount')

    if not all([prediction_id, side, amount]):
        return jsonify({"error": "Missing required fields (prediction_id, side, amount)"}), 400

    try:
        amount = int(amount)
    except ValueError:
        return jsonify({"error": "Invalid amount format"}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    if side not in ['believe', 'doubt']:
        return jsonify({"error": "Side must be 'believe' or 'doubt'"}), 400

    predictions_cog = bot_instance.get_cog('Predictions')
    if not predictions_cog:
        return jsonify({"error": "Predictions cog not loaded"}), 500

    # Call the cog method in the event loop
    future = asyncio.run_coroutine_threadsafe(
        predictions_cog.do_place_bet(
            guild_id, user_id, prediction_id, side, amount
        ),
        bot_instance.loop
    )
    
    try:
        success, message = future.result(timeout=10)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_web_server(host='0.0.0.0', port=5000):
    """Run the Flask web server"""
    app.run(host=host, port=port, threaded=True)
