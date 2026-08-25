"""
Spotify Connect Bridge with Ultra-Fast In-Memory RAM (250ms LL-HLS) pipeline.
Runs in-memory via /dev/shm for near-instant response to track switches, pauses, and playback.
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from typing import Optional
from glagol import GlagolClient

logger = logging.getLogger("spotify")


class SpeakerBridge:
    """Manages Spotify Connect receiver with microsecond RAM I/O and 250ms chunks."""

    def __init__(
        self,
        device_id: str,
        name: str,
        glagol: GlagolClient,
        stream_url: str,
        is_enabled: bool = True,
        cache_dir: str = "/app/cache",
        bitrate: int = 320,
        librespot_bin: str = "/app/librespot"
    ):
        self.device_id = device_id
        self.name = name
        self.spotify_name = f"{name} (Spotify)"
        self.glagol = glagol
        self.stream_url = stream_url.replace('.mp3', '.m3u8')
        self.is_enabled = is_enabled
        self.cache_dir = os.path.join(cache_dir, device_id)
        self.bitrate = bitrate
        self.librespot_bin = librespot_bin

        # Use /dev/shm (shared memory RAM) for zero disk I/O latency
        self.hls_dir = f"/dev/shm/hls_{device_id}" if os.path.exists("/dev/shm") else os.path.join(self.cache_dir, "hls")
        self.spotify_device_id = hashlib.sha1(f"yandex_{device_id}".encode()).hexdigest()

        self.is_playing = False
        self.last_audio_time = 0
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._running = False
        self._tasks = []

        self.glagol.on_state_change = self._on_glagol_state_change

    def _on_glagol_state_change(self, state: dict):
        playing = state.get("playing", False)
        player_state = state.get("playerState", {})
        has_pause = player_state.get("has_pause", False)

        if self.is_playing and not playing and not has_pause:
            logger.debug(f"[{self.spotify_name}] Station paused by user/Alice.")

    def start(self):
        if not self.is_enabled or self._running:
            return
        self._running = True
        os.makedirs(self.hls_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        master_cred = "/app/cache/credentials.json"
        speaker_cred = os.path.join(self.cache_dir, "credentials.json")
        if os.path.exists(master_cred) and not os.path.exists(speaker_cred):
            try:
                shutil.copy(master_cred, speaker_cred)
                logger.info(f"[{self.spotify_name}] Initialized credentials.")
            except Exception as e:
                logger.warning(f"[{self.spotify_name}] Credential warning: {e}")

        self._tasks.append(asyncio.create_task(self._hls_pipeline()))
        self._tasks.append(asyncio.create_task(self._silence_watchdog()))
        self.glagol.start()
        logger.info(f"[{self.spotify_name}] Instant RAM HLS Bridge ready -> {self.stream_url}")

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        self.is_playing = False
        await self.glagol.pause()
        logger.info(f"[{self.spotify_name}] Bridge stopped.")

    async def set_enabled(self, enabled: bool):
        if self.is_enabled == enabled:
            return
        self.is_enabled = enabled
        if enabled:
            logger.info(f"[{self.name}] Enabling speaker bridge...")
            self.start()
        else:
            logger.info(f"[{self.name}] Disabling speaker bridge...")
            await self.stop()

    async def _hls_pipeline(self):
        """
        Instant RAM 250ms HLS Pipeline:
        - 250ms chunk size (-hls_time 0.25)
        - Pure in-memory RAM disk storage in /dev/shm
        - Immediate 50ms trigger for sub-second start
        """
        playlist_path = os.path.join(self.hls_dir, "live.m3u8")
        segment_pattern = os.path.join(self.hls_dir, "seg_%05d.ts")

        while self._running:
            # Clean RAM segments on startup
            for f in os.listdir(self.hls_dir):
                try:
                    os.remove(os.path.join(self.hls_dir, f))
                except Exception:
                    pass

            pipeline_cmd = (
                f"{self.librespot_bin} -n '{self.spotify_name}' --device-type speaker "
                f"--backend pipe --bitrate {self.bitrate} --format S16 --cache '{self.cache_dir}' "
                f"--volume-ctrl linear 2>> /tmp/librespot_{self.device_id}.log | "
                f"ffmpeg -loglevel warning -re -probesize 32 -analyzeduration 0 "
                f"-fflags +nobuffer+flush_packets -flags +low_delay -f s16le -ar 44100 -ac 2 -i pipe:0 "
                f"-c:a aac -b:a {self.bitrate}k -ar 44100 -ac 2 -profile:a aac_low "
                f"-f hls -hls_time 0.25 -hls_list_size 4 -hls_flags delete_segments+split_by_time "
                f"-hls_segment_filename '{segment_pattern}' '{playlist_path}'"
            )
            logger.info(f"[{self.spotify_name}] Launching 250ms RAM HLS pipeline: {pipeline_cmd}")

            try:
                self._proc = await asyncio.create_subprocess_shell(
                    pipeline_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )

                last_mod_time = 0
                while self._running:
                    await asyncio.sleep(0.05)
                    if os.path.exists(playlist_path):
                        mtime = os.path.getmtime(playlist_path)
                        if mtime != last_mod_time and os.path.getsize(playlist_path) > 30:
                            last_mod_time = mtime
                            self.last_audio_time = time.time()
                            
                            if not self.is_playing:
                                self.is_playing = True
                                logger.info(f"[{self.spotify_name}] Instant audio stream active! Sending audio_play to Glagol...")
                                await self.glagol.play_stream(self.stream_url, title=self.name, subtitle="Spotify Connect", is_hls=True)

                    if self._proc.returncode is not None:
                        logger.debug(f"[{self.spotify_name}] Pipeline exited, restarting in 2s...")
                        await asyncio.sleep(2)
                        break
            except Exception as e:
                logger.error(f"[{self.spotify_name}] HLS Pipeline error: {e}")
                await asyncio.sleep(2)

    async def _silence_watchdog(self):
        while self._running:
            await asyncio.sleep(2)
            if self.is_playing and time.time() - self.last_audio_time > 20:
                self.is_playing = False
                logger.info(f"[{self.spotify_name}] Inactivity detected (>20s), stopping speaker.")
                await self.glagol.pause()
