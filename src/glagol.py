"""
Glagol Protocol Client for direct local communication with Yandex Stations.
Communicates directly over local WSS (port 1961) with conversationToken authentication.
Supports modern 2026+ firmware `audio_play` directive with HLS (.m3u8).
"""

import asyncio
import base64
import json
import logging
import ssl
import time
import uuid
import aiohttp
import websockets
from typing import Callable, Optional

logger = logging.getLogger("glagol")


def append_varint(b: bytearray, i: int):
    while i >= 0x80:
        b.append(0x80 | (i & 0x7F))
        i >>= 7
    b.append(i)


def protobuf_dumps(data: dict) -> bytes:
    b = bytearray()
    for tag, value in data.items():
        if isinstance(value, str):
            encoded = value.encode('utf-8')
            b.append(tag << 3 | 2)
            append_varint(b, len(encoded))
            b.extend(encoded)
    return bytes(b)


class GlagolClient:
    """Direct local WebSocket client for a Yandex Station with token auth."""

    def __init__(
        self,
        ip: str,
        port: int = 1961,
        device_id: str = "",
        platform: str = "",
        name: str = "",
        music_token: str = ""
    ):
        self.ip = ip
        self.port = port
        self.device_id = device_id
        self.platform = platform or "yandexstation"
        self.name = name or device_id
        self.music_token = music_token
        self.token: Optional[str] = None
        
        self.ws = None
        self.is_connected = False
        self.state: dict = {}
        self.on_state_change: Optional[Callable[[dict], None]] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def url(self) -> str:
        return f"wss://{self.ip}:{self.port}"

    async def fetch_glagol_token(self) -> Optional[str]:
        """Fetch local device conversation token from Quasar API."""
        if not self.music_token:
            return None
        try:
            url = f"https://quasar.yandex.net/glagol/token?device_id={self.device_id}&platform={self.platform}"
            headers = {"Authorization": f"OAuth {self.music_token}"}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = json.loads(await resp.text())
                    if data.get("status") == "ok":
                        self.token = data.get("token")
                        logger.info(f"[{self.name}] Obtained Glagol conversationToken successfully.")
                        return self.token
                    else:
                        logger.warning(f"[{self.name}] Quasar token error: {data}")
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching Glagol token: {e}")
        return None

    def start(self):
        """Start background connection loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"[{self.name}] Glagol client loop started for {self.url}")

    async def stop(self):
        """Stop client and disconnect."""
        self._running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.is_connected = False
        logger.info(f"[{self.name}] Glagol client disconnected.")

    async def _run_loop(self):
        """Persistent connection loop with auto-reconnect and token auth."""
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        while self._running:
            try:
                if not self.token and self.music_token:
                    await self.fetch_glagol_token()

                logger.debug(f"[{self.name}] Connecting to {self.url}...")
                async with websockets.connect(
                    self.url,
                    ssl=ssl_ctx,
                    ping_interval=15,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=10 * 1024 * 1024
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    logger.info(f"[{self.name}] Connected to Yandex Station locally via Glagol WSS ({self.ip}:{self.port})")

                    async for message in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(message)
                            self._handle_message(data)
                        except json.JSONDecodeError:
                            pass
            except (websockets.exceptions.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                self.is_connected = False
                if self._running:
                    logger.debug(f"[{self.name}] Connection dropped ({e}), reconnecting in 5s...")
                    await asyncio.sleep(5)
            except Exception as e:
                self.is_connected = False
                if self._running:
                    logger.warning(f"[{self.name}] Glagol loop error: {e}, retrying in 5s...")
                    await asyncio.sleep(5)

    def _handle_message(self, data: dict):
        """Process incoming Glagol state update."""
        if "state" in data:
            self.state = data["state"]
            if self.on_state_change:
                try:
                    self.on_state_change(self.state)
                except Exception as e:
                    logger.error(f"[{self.name}] State callback error: {e}")

    async def send_command(self, command: str, extra: Optional[dict] = None):
        """Send a standard Glagol command with conversationToken."""
        if not self.ws or not self.is_connected:
            logger.warning(f"[{self.name}] Cannot send command, not connected to {self.url}")
            return False

        payload = {"command": command}
        if extra:
            payload.update(extra)

        msg_body = {
            "id": str(uuid.uuid4()),
            "sentTime": int(time.time() * 1000),
            "payload": payload
        }
        if self.token:
            msg_body["conversationToken"] = self.token

        try:
            await self.ws.send(json.dumps(msg_body))
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Send error: {e}")
            return False

    async def play_stream(self, stream_url: str, title: str = "Spotify Connect", subtitle: str = "Live Stream", is_hls: bool = True):
        """
        Play an external HLS stream using the modern `audio_play` directive
        (required for Yandex firmware since July 2026).
        """
        audio_play_payload = {
            "stream": {
                "url": stream_url,
                "format": "HLS" if is_hls else "MP3",
                "type": "FmRadio" if is_hls else "Track",
                "offset_ms": 0,
            },
            "set_pause": False,
            "metadata": {
                "title": title,
                "subtitle": subtitle
            }
        }
        
        inner_json = json.dumps(audio_play_payload, ensure_ascii=False)
        proto_bytes = protobuf_dumps({1: "audio_play", 2: inner_json})
        b64_data = base64.b64encode(proto_bytes).decode("ascii")

        logger.info(f"[{self.name}] Sending audio_play ({'HLS' if is_hls else 'MP3'}) -> {stream_url}")
        return await self.send_command("externalCommandBypass", {"data": b64_data})

    async def stop(self):
        """Stop current playback on speaker."""
        logger.info(f"[{self.name}] Stopping playback.")
        return await self.send_command("stop")

    async def pause(self):
        """Pause playback on speaker."""
        return await self.send_command("pause")

    async def play(self):
        """Resume playback on speaker."""
        return await self.send_command("play")

    async def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        vol = max(0.0, min(1.0, float(volume)))
        logger.info(f"[{self.name}] Setting volume to {int(vol * 100)}%")
        return await self.send_command("setVolume", {"volume": vol})
