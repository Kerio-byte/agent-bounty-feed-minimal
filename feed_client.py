#!/usr/bin/env python3
"""Minimal MCP client for Agent Bounty Feed (Streamable HTTP, no auth).

Prints the paid work an AI agent can claim right now, straight from the free
MCP server. Standard library only: no install step, no API key.

    python3 feed_client.py                       # feed stats + 5 top bounties
    python3 feed_client.py stats                 # feed stats only
    python3 feed_client.py bounties 10           # ten bounties
    python3 feed_client.py bounties 10 --exclude kyc,github,purchase --min-usd 1
    python3 feed_client.py bounties 10 --source algora,taskmarket --json
    python3 feed_client.py get cantina:e275368c  # one listing with full detail

Security model: the feed is third-party text. Titles, URLs and server names are
printed after stripping control characters, and links are printed only when they
are http(s). Nothing from the feed is executed or fetched, and this client does
not verify funding — see the README.

Exit codes: 0 success, 1 transport/protocol error, 2 usage error.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MCP_URL = "https://agent-bounty-feed.dailydollar.workers.dev/mcp"
MCP_HOST = "agent-bounty-feed.dailydollar.workers.dev"
PROTOCOL = "2025-06-18"
TIMEOUT = 30
MAX_BODY = 2 * 1024 * 1024
USER_AGENT = "agent-bounty-feed-minimal/1.1 (+https://github.com/Kerio-byte/agent-bounty-feed-minimal)"

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def clean(value, limit=300):
    """Untrusted text -> printable single line, no terminal escape sequences."""
    if value is None:
        return ""
    text = _CONTROL.sub("", str(value))
    text = text.replace("\r", " ").replace("\n", " ")
    return text[:limit]


def safe_url(value):
    """Print a link only when it is a real http(s) URL."""
    if not isinstance(value, str):
        return ""
    parts = urllib.parse.urlsplit(value)
    return value if parts.scheme in ("http", "https") and parts.netloc else ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(f"refusing redirect to {newurl[:120]!r}")


class MCPClient:
    def __init__(self, url=MCP_URL):
        self.url = url
        self.session_id = None
        self._id = 0
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _post(self, payload, notify=False):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
            # Cloudflare in front of the feed answers the default
            # "Python-urllib/3.x" agent with HTTP 403. Identify the client.
            "User-Agent": USER_AGENT,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with self._opener.open(request, timeout=TIMEOUT) as resp:
                final = urllib.parse.urlsplit(resp.geturl())
                if final.scheme != "https" or final.netloc != MCP_HOST:
                    raise RuntimeError(f"refusing a response from {final.netloc!r}")
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                ctype = resp.headers.get("Content-Type", "")
                body = self._read_capped(resp)
        except TimeoutError as exc:  # socket timeout while reading the body
            raise urllib.error.URLError(f"read timed out after {TIMEOUT}s") from exc
        if notify:
            return None
        if "text/event-stream" in ctype:
            return self._parse_sse(body, payload.get("id"))
        if not body.strip():
            raise RuntimeError("empty response body")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"response is not JSON: {body[:120]!r}") from exc

    @staticmethod
    def _read_capped(resp):
        """Read the body with a hard size cap and an overall time budget."""
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY:
            raise RuntimeError(f"response too large: {declared} bytes declared")
        deadline = time.monotonic() + TIMEOUT
        chunks, total = [], 0
        while True:
            if time.monotonic() > deadline:
                raise RuntimeError(f"response exceeded the {TIMEOUT}s budget")
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BODY:
                raise RuntimeError(f"response exceeded {MAX_BODY} bytes")
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", "replace")

    @staticmethod
    def _parse_sse(body, request_id):
        """Return the JSON-RPC message matching request_id, else the last one."""
        events, current = [], []
        for line in body.splitlines():
            if not line.strip():
                if current:
                    events.append("\n".join(current))
                    current = []
                continue
            if line.startswith("data:"):
                current.append(line[5:].lstrip())
        if current:
            events.append("\n".join(current))
        messages = []
        for raw in events:
            try:
                messages.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        for message in messages:
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
        return messages[-1] if messages else None

    def _call(self, method, params=None, notify=False):
        self._id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = self._id
        response = self._post(payload, notify=notify)
        if notify:
            return None
        if not isinstance(response, dict):
            raise RuntimeError(f"{method}: empty or non-JSON-RPC response")
        if response.get("error"):
            error = response["error"] if isinstance(response["error"], dict) else {}
            raise RuntimeError(
                f"{method}: JSON-RPC error {error.get('code')} {clean(error.get('message'), 160)}"
            )
        return response.get("result")

    def initialize(self):
        result = self._call(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "agent-bounty-feed-minimal", "version": "1.1"},
            },
        )
        if not isinstance(result, dict) or not result.get("protocolVersion"):
            raise RuntimeError("initialize: no protocolVersion in the handshake")
        self._call("notifications/initialized", notify=True)
        return result

    def tools(self):
        result = self._call("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else None
        return tools if isinstance(tools, list) else []

    def call_tool(self, name, arguments=None):
        result = self._call("tools/call", {"name": name, "arguments": arguments or {}})
        if not isinstance(result, dict):
            raise RuntimeError(f"tool {name}: malformed result")
        parts = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        text = "\n".join(parts)
        if result.get("isError"):
            raise RuntimeError(f"tool {name}: {clean(text, 200) or 'error'}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


def print_stats(stats, as_json=False):
    if as_json or not isinstance(stats, dict):
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    data = stats.get("stats") if isinstance(stats.get("stats"), dict) else stats
    print(f"generated_at: {clean(stats.get('generated_at'), 40) or '?'}")
    print(f"open bounties: {data.get('items', '?')}   total: ${data.get('total_usd', '?')}")
    by_source = data.get("by_source")
    if isinstance(by_source, dict):
        ranked = sorted(
            ((name, info) for name, info in by_source.items() if isinstance(info, dict)),
            key=lambda pair: pair[1].get("usd") or 0,
            reverse=True,
        )
        for name, info in ranked:
            if info.get("items"):
                print(f"  {clean(name, 24):<12} {info.get('items'):>3} listings   "
                      f"${info.get('usd', 0)}")


def print_bounties(payload, as_json=False):
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        print("  (no items in the answer)")
        return
    print(f"=== {len(items)} of {payload.get('total_matching', '?')} open bounties "
          f"(sorted by {clean(payload.get('sort'), 40)}) ===")
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        reward = item.get("reward")
        usd = item.get("est_usd")
        usd_text = "n/a" if usd is None else f"${usd}"
        print(f"{index}. [{clean(item.get('source'), 24)}] {clean(item.get('title'), 110)}")
        print(f"   reward: {reward if reward is not None else '?'} "
              f"{clean(item.get('currency'), 12)} (~{usd_text})"
              f" | deadline: {clean(item.get('deadline'), 32) or 'open'}")
        requires = item.get("requires")
        if isinstance(requires, list) and requires:
            print(f"   requires: {', '.join(clean(need, 24) for need in requires)}")
        trust = clean(item.get("trust_layer"), 16) or "unknown"
        verified = item.get("verified")
        checked = ""
        if isinstance(verified, dict) and verified.get("checked_at"):
            checked = f" checked {clean(verified['checked_at'], 32)}"
        print(f"   trust: {trust}{checked}")
        url = safe_url(item.get("url"))
        if url:
            print(f"   url: {url}")


def usage(message=None):
    if message:
        print(f"usage error: {message}", file=sys.stderr)
    print("usage: feed_client.py [all|stats|bounties N|get ID] "
          "[--source LIST] [--exclude LIST] [--min-usd N] [--json]", file=sys.stderr)
    return 2


def main(argv):
    mode = argv[1] if len(argv) > 1 else "all"
    rest = argv[2:]
    as_json = "--json" in rest
    rest = [arg for arg in rest if arg != "--json"]
    source = exclude = None
    min_usd = None
    positional = []
    index = 0
    while index < len(rest):
        arg = rest[index]
        if arg in ("--source", "--exclude", "--min-usd"):
            if index + 1 >= len(rest):
                return usage(f"{arg} needs a value")
            value = rest[index + 1]
            index += 2
            if arg == "--source":
                source = value
            elif arg == "--exclude":
                exclude = value
            else:
                try:
                    min_usd = float(value)
                except ValueError:
                    return usage(f"--min-usd expects a number, got {value!r}")
        elif arg.startswith("--"):
            return usage(f"unknown option {arg}")
        else:
            positional.append(arg)
            index += 1
    if mode not in ("all", "stats", "bounties", "get"):
        return usage(f"unknown mode {mode!r}")
    limit = 5
    if mode == "bounties" and positional:
        try:
            limit = int(positional[0])
        except ValueError:
            return usage(f"limit expects an integer, got {positional[0]!r}")
    limit = max(1, min(limit, 100))
    if mode == "get" and not positional:
        return usage("get needs a bounty id")

    client = MCPClient()
    info = client.initialize()
    if not as_json:
        server = info.get("serverInfo") if isinstance(info.get("serverInfo"), dict) else {}
        print(f"connected: {clean(server.get('name'), 40) or '?'} "
              f"protocol {clean(info.get('protocolVersion'), 20)}")
        names = [clean(tool.get("name"), 32) for tool in client.tools() if isinstance(tool, dict)]
        print("tools:", ", ".join(names))
    if mode in ("all", "stats"):
        print("\n=== feed stats ===")
        print_stats(client.call_tool("get_feed_stats"), as_json=as_json)
    if mode in ("all", "bounties"):
        arguments = {"limit": limit}
        if source:
            arguments["source"] = source
        if exclude:
            arguments["exclude_requires"] = exclude
        if min_usd is not None:
            arguments["min_usd"] = min_usd
        print("")
        print_bounties(client.call_tool("list_bounties", arguments), as_json=as_json)
    if mode == "get":
        print("")
        print(json.dumps(client.call_tool("get_bounty", {"id": positional[0]}),
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, ValueError) as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
