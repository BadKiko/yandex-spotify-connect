"""
HTTP Streaming Server and Modern Web Dashboard with 100% Automatic Magic QR Authentication.
"""

import asyncio
import json
import logging
import os
import re
from aiohttp import web
from typing import Dict

logger = logging.getLogger("streamer")

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yandex Spotify Connect</title>
    <style>
        :root {
            --bg: #121212;
            --card: #1e1e1e;
            --accent: #1db954;
            --accent-hover: #1ed760;
            --text: #ffffff;
            --subtext: #888888;
            --border: #2c2c2c;
            --danger: #e74c3c;
            --input-bg: #2a2a2a;
            --yandex: #fc3f1d;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
            display: flex;
            justify-content: center;
        }
        .container { max-width: 800px; width: 100%; }
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }
        h1 { margin: 0; font-size: 22px; display: flex; align-items: center; gap: 10px; }
        .badge {
            background: var(--accent);
            color: #000;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 12px;
        }
        .card {
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            border: 1px solid var(--border);
            transition: opacity 0.2s ease, border-color 0.2s ease;
        }
        .card.disabled {
            opacity: 0.55;
            border-color: #222;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 14px;
        }
        .speaker-name { font-size: 18px; font-weight: 700; }
        .speaker-ip { font-size: 13px; color: var(--subtext); margin-top: 2px; }
        .status-pill {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        .playing { background: rgba(29, 185, 84, 0.2); color: var(--accent); }
        .idle { background: rgba(255, 255, 255, 0.08); color: var(--subtext); }
        .off { background: rgba(231, 76, 60, 0.15); color: var(--danger); }
        
        .toggle-wrap {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #3e3e3e;
            transition: .3s;
            border-radius: 24px;
        }
        .slider:before {
            position: absolute; content: "";
            height: 18px; width: 18px;
            left: 3px; bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--accent); }
        input:checked + .slider:before { transform: translateX(20px); }

        .stream-link { color: var(--accent); text-decoration: none; font-size: 13px; }
        .stream-link:hover { text-decoration: underline; }
        .empty-state { text-align: center; color: var(--subtext); padding: 40px; }

        /* Setup Wizard */
        .setup-box {
            background: #181818;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
        }
        .setup-title { font-size: 18px; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
        .setup-desc { font-size: 14px; color: var(--subtext); line-height: 1.5; margin-bottom: 16px; }
        .qr-section {
            display: flex;
            align-items: center;
            gap: 24px;
            margin-top: 16px;
            padding: 20px;
            background: #202020;
            border-radius: 12px;
            border: 1px solid #2e2e2e;
        }
        .qr-img {
            width: 150px;
            height: 150px;
            background: #fff;
            border-radius: 8px;
            padding: 8px;
        }
        .qr-text { font-size: 14px; color: var(--text); line-height: 1.6; }
        .qr-link { color: var(--accent); font-weight: 600; text-decoration: none; }
        .qr-link:hover { text-decoration: underline; }
        .pulse-status {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #f1c40f;
            font-size: 13px;
            margin-top: 8px;
        }
        .pulse-dot {
            width: 8px;
            height: 8px;
            background: #f1c40f;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.6; }
            50% { transform: scale(1.3); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.6; }
        }
        .success-toast {
            background: rgba(29, 185, 84, 0.2);
            border: 1px solid var(--accent);
            color: #fff;
            padding: 14px 18px;
            border-radius: 8px;
            margin-bottom: 16px;
            display: none;
            font-weight: 600;
        }
        .input-manual {
            margin-top: 16px;
            display: flex;
            gap: 10px;
        }
        input[type="text"] {
            flex: 1;
            background: var(--input-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 14px;
            color: #fff;
            font-size: 13px;
            outline: none;
        }
        input[type="text"]:focus { border-color: var(--accent); }
        .btn-save {
            background: #333;
            color: #fff;
            border: 1px solid #444;
            border-radius: 8px;
            padding: 10px 18px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }
        .btn-save:hover { background: #444; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎵 Yandex Spotify Connect</h1>
            <div style="display: flex; gap: 10px; align-items: center;">
                <button onclick="toggleWizard()" style="padding: 6px 12px; font-size: 12px; background: #333; color: #fff; border: 1px solid #444; border-radius: 6px; cursor: pointer;">⚙️ Сменить аккаунт</button>
                <span class="badge">Standalone</span>
            </div>
        </header>

        <div id="success-toast" class="success-toast">
            ✅ Авторизация успешна! Колонки созданы и подключены к Spotify.
        </div>

        <div id="setup-wizard" class="setup-box" style="display: none;">
            <div class="setup-title">📱 Авторизация через QR-код (Автоматически)</div>
            <div class="setup-desc">
                Наведите камеру смартфона на QR-код и подтвердите вход в аккаунт Яндекса. Токен подхватится <b>полностью автоматически</b> без копирования ссылок!
            </div>

            <div class="qr-section">
                <img class="qr-img" id="qr-code" src="" alt="Загрузка QR-кода...">
                <div class="qr-text">
                    <b>Инструкция:</b><br>
                    1. Отсканируйте QR-код камерой телефона или приложением Яндекс.<br>
                    2. Нажмите <b>«Войти» / «Подтвердить»</b> на экране телефона.<br>
                    <div class="pulse-status">
                        <span class="pulse-dot"></span> Ожидание подтверждения с телефона...
                    </div>
                </div>
            </div>

            <div style="margin-top: 16px; font-size: 12px; color: var(--subtext);">
                Или введите токен вручную, если QR-код недоступен:
            </div>
            <div class="input-manual">
                <input type="text" id="token-input" placeholder="y0_AgAAAA..." autocomplete="off">
                <button class="btn-save" onclick="saveTokenManual()">Сохранить</button>
            </div>
        </div>

        <div id="speakers-list">
            <div class="empty-state">Поиск Яндекс Станций в сети...</div>
        </div>
    </div>

    <script>
        let qrPollInterval = null;

        function toggleWizard() {
            const w = document.getElementById('setup-wizard');
            const isHidden = (w.style.display === 'none' || !w.style.display);
            w.style.display = isHidden ? 'block' : 'none';
            if (isHidden) {
                loadQrCode();
            }
        }

        async function loadQrCode() {
            try {
                const res = await fetch('/api/auth/qr');
                const data = await res.json();
                if (data.qr_url) {
                    document.getElementById('qr-code').src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(data.qr_url)}`;
                    startQrPolling();
                }
            } catch (e) {
                console.error("QR load error:", e);
            }
        }

        function startQrPolling() {
            if (qrPollInterval) clearInterval(qrPollInterval);
            qrPollInterval = setInterval(async () => {
                try {
                    const res = await fetch('/api/auth/qr_status');
                    const data = await res.json();
                    if (data.status === 'ok') {
                        clearInterval(qrPollInterval);
                        qrPollInterval = null;
                        document.getElementById('setup-wizard').style.display = 'none';
                        const toast = document.getElementById('success-toast');
                        toast.style.display = 'block';
                        setTimeout(() => toast.style.display = 'none', 5000);
                        fetchStatus();
                    }
                } catch (e) {
                    console.error("QR poll error:", e);
                }
            }, 1500);
        }

        async function saveTokenManual() {
            const val = document.getElementById('token-input').value.trim();
            const tokenMatch = val.match(/y0_AgAAAA[a-zA-Z0-9_-]+/) || [val];
            if (!tokenMatch[0]) return alert('Вставьте токен!');
            
            try {
                const res = await fetch('/api/config/token', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: tokenMatch[0]})
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    document.getElementById('setup-wizard').style.display = 'none';
                    fetchStatus();
                }
            } catch (e) {
                alert('Ошибка: ' + e);
            }
        }

        async function toggleSpeaker(deviceId, enable) {
            try {
                await fetch(`/api/speakers/${deviceId}/toggle`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({enabled: enable})
                });
                fetchStatus();
            } catch (e) {
                console.error(e);
            }
        }

        let wizardLoaded = false;
        async function fetchStatus() {
            try {
                const res = await fetch('/api/speakers');
                const data = await res.json();
                const container = document.getElementById('speakers-list');
                const wizard = document.getElementById('setup-wizard');
                
                if (!data.has_token) {
                    wizard.style.display = 'block';
                    if (!wizardLoaded) {
                        wizardLoaded = true;
                        loadQrCode();
                    }
                } else {
                    wizard.style.display = 'none';
                }

                if (data.speakers.length === 0) {
                    container.innerHTML = `<div class="empty-state">${data.has_token ? 'Поиск колонок в локальной сети...' : '🔒 Требуется авторизация Яндекс для создания колонок в Spotify.'}</div>`;
                    return;
                }

                container.innerHTML = data.speakers.map(s => `
                    <div class="card ${s.is_enabled ? '' : 'disabled'}">
                        <div class="card-header">
                            <div>
                                <div class="speaker-name">${s.name}</div>
                                <div class="speaker-ip">${s.ip}:${s.port} (${s.device_id})</div>
                            </div>
                            <div class="toggle-wrap">
                                <span class="status-pill ${!s.is_enabled ? 'off' : (s.is_playing ? 'playing' : 'idle')}">
                                    ${!s.is_enabled ? '✕ Отключено' : (s.is_playing ? '▶ Играет Spotify' : '● Готов')}
                                </span>
                                <label class="switch">
                                    <input type="checkbox" ${s.is_enabled ? 'checked' : ''} onchange="toggleSpeaker('${s.device_id}', this.checked)">
                                    <span class="slider"></span>
                                </label>
                            </div>
                        </div>
                        ${s.is_enabled ? `
                            <div style="font-size: 13px; color: var(--subtext); margin-bottom: 6px;">
                                Устройство Spotify Connect: <b>${s.spotify_name}</b>
                            </div>
                            <div style="font-size: 12px;">
                                HLS Live Stream: <a class="stream-link" href="${s.stream_url}" target="_blank">${s.stream_url}</a>
                            </div>
                        ` : `
                            <div style="font-size: 12px; color: var(--subtext);">
                                Трансляция Spotify Connect и связь по Glagol для этого устройства отключены.
                            </div>
                        `}
                    </div>
                `).join('');
            } catch (e) {
                console.error(e);
            }
        }
        fetchStatus();
        setInterval(fetchStatus, 2000);
    </script>
</body>
</html>
"""


class StreamServer:
    """Aiohttp server hosting Low-Latency HLS streams, web UI, and AlexxIT Magic QR API."""

    def __init__(self, port: int = 8555, on_toggle=None, on_token_update=None, yandex_auth=None, app_ref=None):
        self.port = port
        self.bridges: Dict[str, object] = {}
        self.on_toggle = on_toggle
        self.on_token_update = on_token_update
        self.yandex_auth = yandex_auth
        self.app_ref = app_ref
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get('/', self._handle_index)
        self.app.router.add_get('/health', self._handle_health)
        self.app.router.add_get('/api/speakers', self._handle_api_speakers)
        self.app.router.add_get('/api/auth/qr', self._handle_get_qr)
        self.app.router.add_get('/api/auth/qr_status', self._handle_qr_status)
        self.app.router.add_post('/api/speakers/{device_id}/toggle', self._handle_toggle)
        self.app.router.add_post('/api/config/token', self._handle_save_token)
        self.app.router.add_get('/stream/{device_id}.m3u8', self._handle_hls_playlist)
        self.app.router.add_get('/stream/{device_id}/{segment}', self._handle_hls_segment)

    def register_bridge(self, device_id: str, bridge):
        self.bridges[device_id] = bridge

    async def _handle_index(self, request):
        return web.Response(text=HTML_DASHBOARD, content_type='text/html')

    async def _handle_health(self, request):
        return web.Response(text="OK")

    async def _handle_get_qr(self, request):
        if not self.yandex_auth:
            return web.HTTPInternalServerError(text="Auth service unavailable")
        try:
            qr_link = await self.yandex_auth.get_qr()
            return web.json_response({"qr_url": qr_link})
        except Exception as e:
            logger.error(f"Error generating QR link: {e}")
            return web.HTTPInternalServerError(text=str(e))

    async def _handle_qr_status(self, request):
        if not self.yandex_auth:
            return web.json_response({"status": "error"})
        try:
            token = await self.yandex_auth.check_qr_status()
            if token:
                if self.on_token_update:
                    await self.on_token_update(token)
                return web.json_response({"status": "ok", "token": token})
            return web.json_response({"status": "waiting"})
        except Exception as e:
            return web.json_response({"status": "waiting", "error": str(e)})

    async def _handle_api_speakers(self, request):
        has_token = bool(self.app_ref and self.app_ref.yandex_music_token)
        data = {
            "has_token": has_token,
            "speakers": [
                {
                    "device_id": b.device_id,
                    "name": b.name,
                    "spotify_name": b.spotify_name,
                    "ip": b.glagol.ip,
                    "port": b.glagol.port,
                    "stream_url": b.stream_url,
                    "is_playing": b.is_playing,
                    "is_connected": b.glagol.is_connected,
                    "is_enabled": b.is_enabled,
                }
                for b in self.bridges.values()
            ]
        }
        return web.json_response(data)

    async def _handle_save_token(self, request):
        body = await request.json()
        token = body.get('token', '').strip()
        
        token_match = re.search(r'y0_AgAAAA[a-zA-Z0-9_-]+', token)
        if token_match:
            token = token_match.group(0)

        if not token:
            return web.HTTPBadRequest(text="Invalid token")

        if self.on_token_update:
            await self.on_token_update(token)

        return web.json_response({"status": "ok", "message": "Token updated successfully"})

    async def _handle_toggle(self, request):
        device_id = request.match_info['device_id']
        bridge = self.bridges.get(device_id)
        if not bridge:
            return web.HTTPNotFound(text="Speaker not found")

        body = await request.json()
        enable = bool(body.get('enabled', True))
        
        if self.on_toggle:
            await self.on_toggle(device_id, enable)

        return web.json_response({"status": "ok", "device_id": device_id, "enabled": enable})

    async def _handle_hls_playlist(self, request):
        device_id = request.match_info['device_id']
        bridge = self.bridges.get(device_id)
        if not bridge or not bridge.is_enabled:
            return web.HTTPNotFound(text=f"Speaker bridge for {device_id} not active.")

        playlist_file = os.path.join(bridge.hls_dir, "live.m3u8")
        if not os.path.exists(playlist_file):
            return web.HTTPNotFound(text="Stream initializing...")

        try:
            with open(playlist_file, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace('seg_', f'http://{request.host}/stream/{device_id}/seg_')
            return web.Response(
                text=content,
                content_type='application/vnd.apple.mpegurl',
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                    'Access-Control-Allow-Origin': '*',
                    'X-Accel-Buffering': 'no',
                }
            )
        except Exception as e:
            return web.HTTPInternalServerError(text=str(e))

    async def _handle_hls_segment(self, request):
        device_id = request.match_info['device_id']
        segment = request.match_info['segment']
        bridge = self.bridges.get(device_id)
        if not bridge:
            return web.HTTPNotFound()

        seg_file = os.path.join(bridge.hls_dir, segment)
        if not os.path.exists(seg_file):
            return web.HTTPNotFound()

        return web.FileResponse(
            seg_file,
            headers={
                'Content-Type': 'video/MP2T',
                'Cache-Control': 'no-cache, no-store, max-age=0',
                'Access-Control-Allow-Origin': '*',
                'X-Accel-Buffering': 'no',
            }
        )

    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"Magic QR Server & Web UI ready at http://0.0.0.0:{self.port}")
