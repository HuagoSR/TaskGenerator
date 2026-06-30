import os
from html import escape
from types import TracebackType
from typing import Annotated, Any

import httpx
import trafilatura
from pydantic import BaseModel, Field

from stirrup.core.models import Tool, ToolProvider, ToolResult
from stirrup.utils.text import truncate_msg


MAX_LENGTH_WEB_FETCH_HTML = 40000
MAX_LENGTH_WEB_SEARCH_RESULTS = 40000
WEB_FETCH_TIMEOUT = 180
WEB_SEARCH_TIMEOUT = 180
DEFAULT_WEBFETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class FetchWebPageParams(BaseModel):
    url: Annotated[str, Field(description="Full HTTP or HTTPS URL of the web page to fetch and extract")]


class WebSearchParams(BaseModel):
    query: Annotated[str, Field(description="Natural language web search query")]


class WebFetchMetadata(BaseModel):
    num_uses: int = 1
    pages_fetched: list[str] = Field(default_factory=list)

    def __add__(self, other: "WebFetchMetadata") -> "WebFetchMetadata":
        return WebFetchMetadata(
            num_uses=self.num_uses + other.num_uses,
            pages_fetched=self.pages_fetched + other.pages_fetched,
        )


class WebSearchMetadata(BaseModel):
    num_uses: int = 1
    pages_returned: int = 0
    backend: str = "serper"

    def __add__(self, other: "WebSearchMetadata") -> "WebSearchMetadata":
        return WebSearchMetadata(
            num_uses=self.num_uses + other.num_uses,
            pages_returned=self.pages_returned + other.pages_returned,
            backend=self.backend,
        )


def serper_results_to_xml(payload: dict[str, Any]) -> str:
    results = payload.get("organic", []) or []
    parts = ["<results>"]
    for result in results:
        title = escape(str(result.get("title", "") or ""))
        url = escape(str(result.get("link", "") or ""))
        description = escape(str(result.get("snippet", "") or ""))
        parts.append(
            "<result>"
            f"\n<title>{title}</title>"
            f"\n<url>{url}</url>"
            f"\n<description>{description}</description>"
            "\n</result>"
        )
    parts.append("</results>")
    return "\n".join(parts)


def _get_fetch_web_page_tool(client: httpx.AsyncClient) -> Tool[FetchWebPageParams, WebFetchMetadata]:
    async def fetch_web_page_executor(params: FetchWebPageParams) -> ToolResult[WebFetchMetadata]:
        try:
            response = await client.get(params.url, headers=DEFAULT_WEBFETCH_HEADERS)
            response.raise_for_status()
            body_md = trafilatura.extract(response.text, output_format="markdown") or ""
            return ToolResult(
                content=f"<web_fetch><url>{params.url}</url><body>"
                f"{truncate_msg(body_md, MAX_LENGTH_WEB_FETCH_HTML)}</body></web_fetch>",
                metadata=WebFetchMetadata(pages_fetched=[params.url]),
            )
        except httpx.HTTPError as exc:
            return ToolResult(
                content=f"<web_fetch><url>{params.url}</url><error>"
                f"{truncate_msg(str(exc), MAX_LENGTH_WEB_FETCH_HTML)}</error></web_fetch>",
                success=False,
                metadata=WebFetchMetadata(pages_fetched=[params.url]),
            )

    return Tool[FetchWebPageParams, WebFetchMetadata](
        name="fetch_web_page",
        description="Fetch and extract the main content from a web page as markdown. Returns body text or error as XML.",
        parameters=FetchWebPageParams,
        executor=fetch_web_page_executor,  # ty: ignore[invalid-argument-type]
    )


def _get_serper_search_tool(
    api_key: str,
    client: httpx.AsyncClient,
    num_results: int,
) -> Tool[WebSearchParams, WebSearchMetadata]:
    async def websearch_executor(params: WebSearchParams) -> ToolResult[WebSearchMetadata]:
        response = await client.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json={"q": params.query, "num": num_results},
        )
        response.raise_for_status()
        data = response.json()
        results_xml = serper_results_to_xml(data)
        pages_returned = len(data.get("organic", []) or [])
        return ToolResult(
            content=truncate_msg(results_xml, MAX_LENGTH_WEB_SEARCH_RESULTS),
            metadata=WebSearchMetadata(pages_returned=pages_returned),
        )

    return Tool[WebSearchParams, WebSearchMetadata](
        name="web_search",
        description="Search the web using Serper. Returns top results with title, URL, and description as XML.",
        parameters=WebSearchParams,
        executor=websearch_executor,  # ty: ignore[invalid-argument-type]
    )


class SerperWebToolProvider(ToolProvider):
    """Stirrup-compatible web provider backed by Serper search and local fetch."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str = "SERPER_API_KEY",
        timeout: float = WEB_SEARCH_TIMEOUT,
        num_results: int = 5,
    ) -> None:
        self._api_key = api_key or os.getenv(api_key_env)
        self._api_key_env = api_key_env
        self._timeout = timeout
        self._num_results = num_results
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> list[Tool[Any, Any]]:
        if not self._api_key:
            raise RuntimeError(f"Required environment variable is missing: {self._api_key_env}")
        self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        await self._client.__aenter__()
        return self.get_tools()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)
            self._client = None

    def get_tools(self) -> list[Tool[Any, Any]]:
        if self._client is None:
            raise RuntimeError("SerperWebToolProvider not started. Use 'async with' first.")
        return [
            _get_fetch_web_page_tool(self._client),
            _get_serper_search_tool(self._api_key or "", self._client, self._num_results),
        ]

