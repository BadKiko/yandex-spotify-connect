"""
Main Entry Point for Yandex Spotify Connect.
Coordinates Zeroconf discovery, Speaker bridges, Web setup wizard, and HTTP server.
"""

import asyncio
import logging
import os
import socket
import sys
import yaml
from typing import Dict, Set

from discovery import YandexDiscovery, SpeakerInfo
from glagol import GlagolClient
from spotify import SpeakerBridge
from streamer import StreamServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("main")

NAME_OVERRIDES = {
    "U00JFJ500KMX8K": "Яндекс Станция 2",
    "M001YJZ0052SEK": "Станция Мини 2",
    "1f82121ab18a11e40ff5": "Яндекс ТВ (Tuvio)",
}


def get_local_ip() -> str:
    """Auto-detect host IP in local network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Application:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        
        self.host_ip = self.config.get("host_ip") or get_local_ip()
        self.port = int(self.config.get("port", 8555))
        self.cache_dir = self.config.get("cache_dir", "/app/cache")
        self.bitrate = int(self.config.get("bitrate", 320))
        self.librespot_bin = self.config.get("librespot_bin", "/app/librespot")
        self.yandex_music_token = self.config.get("yandex_music_token", "")
        
        disabled_list = self.config.get("disabled_speakers", ["1f82121ab18a11e40ff5"])
        self.disabled_speakers: Set[str] = set(disabled_list)

        self.streamer = StreamServer(
            port=self.port,
            on_toggle=self.handle_speaker_toggle,
            on_token_update=self.handle_token_update,
            app_ref=self
        )
        self.bridges: Dict[str, SpeakerBridge] = {}
        self.discovery: YandexDiscovery = None
        self._running = False

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Could not load config from {self.config_path}: {e}")
        return {}

    def _save_config(self):
        try:
            self.config["disabled_speakers"] = list(self.disabled_speakers)
            self.config["yandex_music_token"] = self.yandex_music_token
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, allow_unicode=True)
            logger.info("Saved configuration file successfully.")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    async def handle_token_update(self, token: str):
        """Called when user enters token in Web UI."""
        self.yandex_music_token = token
        self._save_config()
        for bridge in self.bridges.values():
            bridge.glagol.music_token = token
            await bridge.glagol.fetch_glagol_token()
        logger.info("Updated Yandex Music token across all active bridges.")

    async def handle_speaker_toggle(self, device_id: str, enable: bool):
        """Called from Web UI when user toggles a speaker on/off."""
        if enable:
            self.disabled_speakers.discard(device_id)
        else:
            self.disabled_speakers.add(device_id)

        self._save_config()

        bridge = self.bridges.get(device_id)
        if bridge:
            await bridge.set_enabled(enable)

    def _on_speaker_found(self, speaker: SpeakerInfo):
        if speaker.device_id in self.bridges:
            return

        name = NAME_OVERRIDES.get(speaker.device_id, speaker.name)
        is_enabled = speaker.device_id not in self.disabled_speakers

        stream_url = f"http://{self.host_ip}:{self.port}/stream/{speaker.device_id}.mp3"
        glagol = GlagolClient(
            ip=speaker.ip,
            port=speaker.port,
            device_id=speaker.device_id,
            platform=speaker.platform,
            name=name,
            music_token=self.yandex_music_token
        )

        bridge = SpeakerBridge(
            device_id=speaker.device_id,
            name=name,
            glagol=glagol,
            stream_url=stream_url,
            is_enabled=is_enabled,
            cache_dir=self.cache_dir,
            bitrate=self.bitrate,
            librespot_bin=self.librespot_bin
        )

        self.bridges[speaker.device_id] = bridge
        self.streamer.register_bridge(speaker.device_id, bridge)
        bridge.start()
        logger.info(f"Registered bridge: {name} ({speaker.ip}) [Enabled: {is_enabled}]")

    async def start(self):
        logger.info("==================================================")
        logger.info("🚀 Starting Yandex Spotify Connect")
        logger.info(f"Host IP: {self.host_ip} | Stream Port: {self.port}")
        logger.info("==================================================")

        await self.streamer.start()

        # Start Zeroconf discovery with running event loop
        self.discovery = YandexDiscovery(loop=asyncio.get_running_loop(), on_found=self._on_speaker_found)
        self.discovery.start()

        self._running = True
        try:
            while self._running:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self):
        logger.info("Shutting down Yandex Spotify Connect...")
        self._running = False
        if self.discovery:
            self.discovery.stop()
        for b in self.bridges.values():
            await b.stop()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    app = Application()
    try:
        asyncio.run(app.start())
    except (KeyboardInterrupt, SystemExit):
        pass
