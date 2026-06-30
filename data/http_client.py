"""
通用 HTTP 客户端 — 带重试、速率限制、错误处理
所有 scraper 统一使用此客户端
"""
import time
import logging
from typing import Optional, Any
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class RateLimiter:
    """简易速率限制器"""
    def __init__(self, calls_per_minute: int = 30):
        self.min_interval = 60.0 / calls_per_minute
        self._last_call = 0.0

    def wait(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()


class APIClient:
    """HTTP API 客户端"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 3,
        calls_per_minute: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.rate_limiter = RateLimiter(calls_per_minute)

        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET 请求"""
        self.rate_limiter.wait()
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = self.session.get(
                url, params=params, timeout=self.timeout,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            # 统一处理 API 错误
            if "errors" in data and data["errors"]:
                err = data["errors"]
                logger.error(f"API Error: {url} → {err}")
                # 速率限制 → 等待后重试
                if any("rate" in str(e).lower() for e in (err if isinstance(err, list) else [err])):
                    time.sleep(60)
                    return self.get(path, params)
                return {"error": str(err), "data": []}
            return data
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout: {url}")
            return {"error": "timeout", "data": []}
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP {e.response.status_code}: {url}")
            return {"error": str(e), "data": []}
        except Exception as e:
            logger.error(f"Request failed: {url} → {e}")
            return {"error": str(e), "data": []}

    def _headers(self) -> dict:
        return {
            "Accept": "application/json",
            "User-Agent": "FootballQuant/0.1",
        }
