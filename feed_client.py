#!/usr/bin/env python3
"""Minimal MCP client for Agent Bounty Feed (Streamable HTTP, no auth, stdlib only).

Usage:
    python3 feed_client.py            # stats + newest bounties
    python3 feed_client.py stats      # feed stats only
    python3 feed_client.py bounties 5 # list 5 bounties

Exit code 0 on success, 1 on any transport/protocol error.
"""
import json
import sys
import urllib.request
import urllib.error

MCP_URL = "https://agent-bounty-feed.dailydollar.workers.dev/mcp"
PROTOCOL = "2025-06-18"
TIMEOUT = 30


class MCPClient:
    def __init__(self, url=MCP_URL):
        self.url = url
        self.session_id = None
        self._id = 0

    def _post(self, payload, notify=False):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
            # Cloudflare in front of the feed rejects the default
            # "Python-urllib/3.x" agent with HTTP 403. Any normal UA works.
            "User-Agent": "agent-bounty-feed-minimal/1.0",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            body = resp.read().decode("utf-8", "replace")
            ctype = resp.headers.get("Content-Type", "")
        if notify:
            return None
        if "text/event-stream" in ctype:
            return self._parse_sse(body)
        return json.loads(body) if body.strip() else None

    @staticmethod
    def _parse_sse(body):
        """Return the last JSON-RPC message carried in an SSE stream."""
        last = None
        for line in body.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk:
                    try:
                        last = json.loads(chunk)
                    except json.JSONDecodeError:
                        pass
        return last

    def _call(self, method, params=None, notify=False):
        self._id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = self._id
        return self._post(payload, notify=notify)

    def initialize(self):
        res = self._call(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "agent-bounty-feed-minimal", "version": "1.0.0"},
            },
        )
        self._call("notifications/initialized", notify=True)
        return (res or {}).get("result", {})

    def tools(self):
        res = self._call("tools/list", {})
        return (res or {}).get("result", {}).get("tools", [])

    def call_tool(self, name, arguments=None):
        res = self._call("tools/call", {"name": name, "arguments": arguments or {}})
        result = (res or {}).get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"tool {name} returned an error")
        parts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
        raw = "\n".join(parts)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def _short(b, i):
    lines = [f"{i}. {b.get('title') or b.get('name') or '(no title)'}"]
    for key, label in (
        ("reward_usd", "reward"),
        ("reward", "reward"),
        ("source", "source"),
        ("url", "url"),
        ("deadline", "deadline"),
    ):
        if b.get(key) not in (None, ""):
            lines.append(f"   {label}: {b[key]}")
            break
    for key in ("source", "url", "deadline"):
        pass
    return "\n".join(lines)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    client = MCPClient()
    info = client.initialize()
    print(f"connected: {info.get('serverInfo', {}).get('name', '?')} "
          f"protocol {info.get('protocolVersion', '?')}")
    names = [t["name"] for t in client.tools()]
    print("tools:", ", ".join(names))
    if mode in ("all", "stats"):
        stats = client.call_tool("get_feed_stats")
        print("\n=== feed stats ===")
        print(json.dumps(stats, ensure_ascii=False, indent=2)[:1200])
    if mode in ("all", "bounties"):
        data = client.call_tool("list_bounties", {"limit": limit})
        items = data.get("items") if isinstance(data, dict) else data
        if isinstance(items, list):
            print(f"\n=== {len(items)} of {data.get('total_matching', '?')} open bounties "
                  f"(sorted by {data.get('sort', '?')}) ===")
            for i, b in enumerate(items, 1):
                print(f"{i}. [{b.get('source', '?')}] {b.get('title', '(no title)')}")
                print(f"   reward: {b.get('reward', '?')} {b.get('currency', '')} "
                      f"(~${b.get('est_usd', '?')}) | deadline: {b.get('deadline') or 'open'}")
                needs = b.get("requires") or []
                if needs:
                    print(f"   requires: {', '.join(needs)}")
                if b.get("url"):
                    print(f"   url: {b['url']}")
        else:
            print("\n=== raw answer ===")
            print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, ValueError) as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
