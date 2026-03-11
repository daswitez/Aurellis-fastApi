import asyncio
import httpx
import random
import logging
import socket
import ssl
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


class FetchHtmlError(Exception):
    def __init__(
        self,
        *,
        url: str,
        error_type: str,
        message: str,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        attempts_made: int = 1,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.attempts_made = attempts_made

    def to_context(self) -> dict:
        return {
            "url": self.url,
            "error_type": self.error_type,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "attempts_made": self.attempts_made,
            "error": self.message,
        }


def _parse_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        retry_after = float(value)
    except ValueError:
        return None
    return retry_after if retry_after >= 0 else None


def _classify_http_status(url: str, status_code: int, retry_after_header: str | None = None) -> FetchHtmlError:
    if status_code == 403:
        return FetchHtmlError(
            url=url,
            error_type="http_403",
            status_code=status_code,
            retryable=False,
            message=f"HTTP 403 Forbidden al visitar {url}",
        )
    if status_code == 429:
        return FetchHtmlError(
            url=url,
            error_type="http_429",
            status_code=status_code,
            retryable=True,
            retry_after_seconds=_parse_retry_after_seconds(retry_after_header),
            message=f"HTTP 429 Too Many Requests al visitar {url}",
        )
    if 500 <= status_code < 600:
        return FetchHtmlError(
            url=url,
            error_type="http_5xx",
            status_code=status_code,
            retryable=True,
            message=f"HTTP {status_code} upstream error al visitar {url}",
        )
    return FetchHtmlError(
        url=url,
        error_type="http_4xx",
        status_code=status_code,
        retryable=False,
        message=f"HTTP {status_code} al visitar {url}",
    )


def _extract_root_cause(error: BaseException) -> BaseException:
    current: BaseException = error
    while True:
        next_error = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if next_error is None:
            return current
        current = next_error


def _classify_request_error(url: str, error: httpx.RequestError) -> FetchHtmlError:
    root_cause = _extract_root_cause(error)

    if isinstance(error, httpx.TimeoutException):
        return FetchHtmlError(
            url=url,
            error_type="timeout",
            retryable=True,
            message=f"Timeout al visitar {url}",
        )
    if isinstance(root_cause, ssl.SSLError):
        return FetchHtmlError(
            url=url,
            error_type="tls_error",
            retryable=False,
            message=f"Error TLS/SSL al visitar {url}: {root_cause}",
        )
    if isinstance(root_cause, socket.gaierror):
        return FetchHtmlError(
            url=url,
            error_type="dns_error",
            retryable=False,
            message=f"Error DNS resolviendo {url}: {root_cause}",
        )
    return FetchHtmlError(
        url=url,
        error_type="network_error",
        retryable=True,
        message=f"Error de red al visitar {url}: {error}",
    )


def _compute_backoff_delay(error: FetchHtmlError, attempt_number: int, base_seconds: float) -> float:
    if error.retry_after_seconds is not None:
        return error.retry_after_seconds
    exponential_delay = max(base_seconds, 0.0) * (2 ** (attempt_number - 1))
    jitter = random.uniform(0.0, max(base_seconds, 0.0))
    return exponential_delay + jitter


async def fetch_html(url: str, timeout: int = 15) -> str:
    """
    Realiza una petición HTTP asíncrona a la URL indicada seleccionando
    un User-Agent aleatorio para evadir las defensas antibot más básicas.
    
    Args:
        url: La dirección web a descargar.
        timeout: Segundos a esperar antes de abortar (default: 15).
        
    Returns:
        El HTML de la página como string.

    Raises:
        FetchHtmlError: cuando la descarga falla con clasificación operativa.
    """
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",  # Do Not Track request header
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    settings = get_settings()
    verify_tls = settings.HTTP_VERIFY_TLS
    max_attempts = max(1, settings.HTTP_MAX_RETRIES + 1)

    if not verify_tls:
        logger.warning("HTTP_VERIFY_TLS=false. TLS deshabilitado para debugging controlado.")

    for attempt_number in range(1, max_attempts + 1):
        try:
            # follows_redirects=True permite perseguir mudanzas de sitios web limpios a www o https sin fallar
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=verify_tls, timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status() # Lanza excepción para 400s y 500s
                return response.text

        except httpx.HTTPStatusError as e:
            classified_error = _classify_http_status(
                url,
                e.response.status_code,
                e.response.headers.get("Retry-After"),
            )
        except httpx.RequestError as e:
            classified_error = _classify_request_error(url, e)
        except Exception as e:
            logger.error(f"Error desconocido extrayendo {url}: {str(e)}")
            classified_error = FetchHtmlError(
                url=url,
                error_type="unknown_error",
                retryable=False,
                message=f"Error desconocido extrayendo {url}: {e}",
            )

        classified_error.attempts_made = attempt_number
        should_retry = classified_error.retryable and attempt_number < max_attempts

        if should_retry:
            delay_seconds = _compute_backoff_delay(
                classified_error,
                attempt_number,
                settings.HTTP_BACKOFF_BASE_SECONDS,
            )
            logger.warning(
                "%s [%s] | intento %s/%s | retry en %.2fs",
                classified_error.message,
                classified_error.error_type,
                attempt_number,
                max_attempts,
                delay_seconds,
            )
            await asyncio.sleep(delay_seconds)
            continue

        logger.warning(
            "%s [%s] | intento %s/%s",
            classified_error.message,
            classified_error.error_type,
            attempt_number,
            max_attempts,
        )
        raise classified_error
