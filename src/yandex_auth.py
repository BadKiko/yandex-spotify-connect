"""
AlexxIT-style 100% Automatic Yandex QR Authentication & Token Exchange.
Provides seamless QR code login via Yandex Push / Magic code without manual copying.
"""

import aiohttp
import asyncio
import json
import logging
import re
from typing import Optional

logger = logging.getLogger("yandex_auth")


class YandexAuth:
    """Manages Yandex Passport QR code authentication and automatic token exchange."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._own_session = False
        self.auth_headers = {}
        self.auth_json = {}

    async def _ensure_session(self):
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    async def close(self):
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def get_qr(self) -> str:
        """
        Requests magic QR code link from Yandex Passport:
        https://passport.yandex.ru/am/push/qrsecure?track_id=...&magic=...
        """
        await self._ensure_session()
        async with self._session.get("https://passport.yandex.ru/pwl-yandex") as r:
            text = await r.text()
            m = re.search(r'__CSRF__ = "([^"]+)', text)
            if not m:
                raise Exception("Failed to extract Yandex CSRF token")
            csrf = m[1]

        self.auth_headers = {"X-CSRF-Token": csrf, "Accept": "application/json"}

        async with self._session.post(
            "https://passport.yandex.ru/pwl-yandex/api/passport/auth/password/submit",
            json={"retpath": "https://passport.yandex.ru/"},
            headers=self.auth_headers
        ) as r:
            self.auth_json = await r.json()

        async with self._session.post(
            "https://passport.yandex.ru/pwl-yandex/api/passport/auth/magic/code",
            data={
                "location_id": "0",
                "magic_track_id": self.auth_json["track_id"],
                "track_id": "",
            },
            headers=self.auth_headers
        ) as r:
            resp = await r.json()
            return resp["link"]

    async def check_qr_status(self) -> Optional[str]:
        """
        Polls magic QR login status.
        If user approved login on phone, returns the full yandex_music_token automatically!
        """
        if not self.auth_json or "track_id" not in self.auth_json:
            return None

        await self._ensure_session()
        async with self._session.post(
            "https://passport.yandex.ru/pwl-yandex/api/passport/auth/magic/code/status",
            json=self.auth_json,
            headers=self.auth_headers
        ) as r:
            resp = await r.json()

        if resp.get("state") != "otp_auth_finished":
            return None

        logger.info("User confirmed QR login! Exchanging session for music token...")

        # 1. Get session cookies
        async with self._session.post(
            "https://passport.yandex.ru/pwl-yandex/api/passport/sessions/get_session",
            data={"track_id": resp["trackId"]},
            headers=self.auth_headers
        ) as r:
            await r.read()

        cookies = "; ".join(
            [f"{c.key}={c.value}" for c in self._session.cookie_jar if c["domain"].endswith("yandex.ru")]
        )

        # 2. Get x_token from sessionid
        async with self._session.post(
            "https://mobileproxy.passport.yandex.net/1/bundle/oauth/token_by_sessionid",
            data={
                "client_id": "c0ebe342af7d48fbbbfcf2d2eedb8f9e",
                "client_secret": "ad0a908f0aa341a182a37ecd75bc319e",
            },
            headers={"Ya-Client-Host": "passport.yandex.ru", "Ya-Client-Cookie": cookies}
        ) as r:
            token_resp = await r.json()
            x_token = token_resp.get("access_token")

        if not x_token:
            logger.error(f"Failed to get x_token: {token_resp}")
            return None

        # 3. Exchange x_token for Yandex Music OAuth token
        async with self._session.post(
            "https://oauth.mobile.yandex.net/1/token",
            data={
                "client_secret": "53bc75238f0c4d08a118e51fe9203300",
                "client_id": "23cabbbdc6cd418abb4b39c32c41195d",
                "grant_type": "x-token",
                "access_token": x_token,
            }
        ) as r:
            music_resp = await r.json()
            music_token = music_resp.get("access_token")

        logger.info(f"Successfully obtained Yandex Music token: {music_token[:10]}...")
        return music_token
