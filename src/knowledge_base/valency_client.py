"""Valency Bond MCP Client Adapter for PerturbMat-Agent.

Provides high-speed semantic search, bidirectional citation graph traversal,
and publication trend analytics over 46M+ papers and 534M+ citations.
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional


class ValencyClient:
    """Client for interacting directly with the authenticated Valency Bond MCP endpoint."""

    DEFAULT_MCP_URL = "https://mcp.valency.io/"
    DEFAULT_TOKENS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "mcp_oauth_tokens.json"

    def __init__(
        self,
        mcp_url: str = DEFAULT_MCP_URL,
        tokens_path: Optional[Path] = None,
        access_token: Optional[str] = None,
    ):
        self.mcp_url = mcp_url
        self.tokens_path = tokens_path or self.DEFAULT_TOKENS_PATH
        self._access_token = access_token or self._load_token()

    def _load_token(self) -> Optional[str]:
        """Load OAuth access token from antigravity-cli config or environment."""
        env_token = os.environ.get("VALENCY_ACCESS_TOKEN")
        if env_token:
            return env_token

        if self.tokens_path.exists():
            try:
                data = json.loads(self.tokens_path.read_text(encoding="utf-8"))
                valency_data = data.get("https://mcp.valency.io", {})
                return valency_data.get("token", {}).get("access_token")
            except Exception:
                return None
        return None

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute an MCP tool call over JSON-RPC HTTP transport."""
        token = self._access_token or self._load_token()
        if not token:
            raise PermissionError("Valency access token not found. Please authenticate via Antigravity CLI.")

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
            "id": 1,
        }

        req = urllib.request.Request(
            self.mcp_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {token}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data.get("result", {})
                if result.get("isError"):
                    content = result.get("content", [{}])
                    err_msg = content[0].get("text", "Unknown tool error") if content else "Unknown error"
                    raise RuntimeError(f"Valency tool error ({tool_name}): {err_msg}")
                return result
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Valency HTTP {e.code} error: {err_body}")

    def list_sources(self) -> Dict[str, Any]:
        """Retrieve the list of active literature sources, paper counts, and date coverage."""
        res = self.call_tool("list_sources")
        return res.get("structuredContent") or json.loads(res.get("content", [{}])[0].get("text", "{}"))

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        include_abstract: bool = True,
        sort_by: str = "relevance",
    ) -> List[Dict[str, Any]]:
        """Search papers by semantic similarity across PubMed, arXiv, bioRxiv, etc."""
        res = self.call_tool(
            "semantic_search_papers",
            {
                "query": query,
                "limit": limit,
                "include_abstract": include_abstract,
                "sort_by": sort_by,
            },
        )
        data = res.get("structuredContent") or json.loads(res.get("content", [{}])[0].get("text", "{}"))
        return data.get("papers", [])

    def get_forward_citations(self, paper_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Find later papers citing a given paper (downstream citation traversal)."""
        res = self.call_tool(
            "get_citing_papers",
            {
                "paper_id": str(paper_id),
                "limit": limit,
                "sort_by": "citations",
            },
        )
        data = res.get("structuredContent") or json.loads(res.get("content", [{}])[0].get("text", "{}"))
        return data.get("results", [])

    def get_keyword_trends(self, query: str) -> Dict[str, Any]:
        """Analyze temporal publication velocity and research volume for a concept or keyword."""
        res = self.call_tool("get_keyword_trends", {"query": query})
        return res.get("structuredContent") or json.loads(res.get("content", [{}])[0].get("text", "{}"))

    def find_contradicting_evidence(self, hypothesis: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Adversarial search for failed replications, negative findings, or opposing mechanisms."""
        adversarial_query = f"contradiction failed replication degradation inhibition counterion limit {hypothesis}"
        return self.semantic_search(adversarial_query, limit=limit, include_abstract=True)
