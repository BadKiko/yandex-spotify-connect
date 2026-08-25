"""
Zeroconf mDNS Discovery for Yandex Stations and TVs.
Listens for _yandexio._tcp.local. services on the local network.
"""

import asyncio
import logging
from typing import Callable, Dict, Optional
from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo

logger = logging.getLogger("discovery")

NAME_OVERRIDES = {
    "U00JFJ500KMX8K": "Яндекс Станция 2",
    "M001YJZ0052SEK": "Станция Мини 2",
    "1f82121ab18a11e40ff5": "Яндекс ТВ (Tuvio)",
}

KNOWN_PLATFORMS = {
    "yandexstation": "Яндекс Станция",
    "yandexstation_2": "Яндекс Станция 2",
    "yandexmini": "Станция Мини",
    "yandexmini_2": "Станция Мини 2",
    "yandexmidi": "Станция Миди",
    "yandexmicro": "Станция Лайт",
    "yandexmax": "Станция Макс",
    "yandexduo": "Станция Дуо",
    "yandex_tv_mt9632_11_cvte": "Яндекс ТВ (Tuvio)",
}


class SpeakerInfo:
    def __init__(self, device_id: str, ip: str, port: int = 1961, platform: str = "", name: str = ""):
        self.device_id = device_id
        self.ip = ip
        self.port = port
        self.platform = platform
        # Explicit override takes top priority
        self.name = NAME_OVERRIDES.get(device_id) or name or KNOWN_PLATFORMS.get(platform, f"Яндекс Устройство ({device_id[:6]})")

    def __repr__(self):
        return f"<Speaker {self.name} ({self.device_id}) at {self.ip}:{self.port}>"


class YandexDiscovery:
    """Discovers Yandex Stations via Zeroconf mDNS with thread-safe asyncio dispatch."""

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None, on_found: Optional[Callable[[SpeakerInfo], None]] = None):
        self.loop = loop
        self.on_found = on_found
        self.speakers: Dict[str, SpeakerInfo] = {}
        self.zc: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None

    def start(self):
        logger.info("Starting Zeroconf mDNS scanner for Yandex devices (_yandexio._tcp.local)...")
        self.zc = Zeroconf()
        self.browser = ServiceBrowser(self.zc, "_yandexio._tcp.local.", handlers=[self._on_state_change])

    def stop(self):
        if self.zc:
            self.zc.close()
            self.zc = None
        logger.info("Zeroconf scanner stopped.")

    def _on_state_change(self, zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                self._process_info(info)

    def _process_info(self, info: ServiceInfo):
        ip = info.parsed_scoped_addresses()[0] if info.parsed_scoped_addresses() else None
        if not ip:
            return

        port = info.port or 1961
        props = {k.decode("utf-8", errors="ignore"): v.decode("utf-8", errors="ignore") for k, v in info.properties.items()}
        device_id = props.get("deviceId", info.name.split(".")[0])
        platform = props.get("platform", "")

        speaker = SpeakerInfo(
            device_id=device_id,
            ip=ip,
            port=port,
            platform=platform
        )

        if device_id not in self.speakers:
            self.speakers[device_id] = speaker
            logger.info(f"Discovered new Yandex device: {speaker}")
            if self.on_found:
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(self.on_found, speaker)
                else:
                    self.on_found(speaker)
