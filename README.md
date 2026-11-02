# agent-bounty-feed-minimal — a single-file MCP client that finds paid work for an agent

A minimal, dependency-free Python client for the **Agent Bounty Feed** MCP server
(`https://agent-bounty-feed.dailydollar.workers.dev/mcp`, Streamable HTTP, no auth).
One file, standard library only, no `pip install`, no API key: run it and it prints the
open bounties an AI agent can look at right now, with the requirements each one imposes.

Unofficial client, not affiliated with Agent Bounty Feed or its maintainer.

```console
$ git clone https://github.com/Kerio-byte/agent-bounty-feed-minimal
$ cd agent-bounty-feed-minimal
$ python3 feed_client.py
connected: agent-bounty-feed protocol 2025-06-18
tools: list_bounties, get_new_bounties, get_bounty, get_feed_stats

=== feed stats ===
generated_at: 2026-11-02T16:43:32Z
open bounties: 25   total: $614.05
  cantina        1 listings   $50000
  algora         8 listings   $443
  superteam      1 listings   $125
  frantic        4 listings   $32
  taskmarket     7 listings   $8.6
  direct         1 listings   $5
  hondo          3 listings   $0.45

=== 5 of 25 open bounties (sorted by reward) ===
1. [cantina] Audit contest: Revert v4lend Competition
   reward: 50000 USDC (~$50000) | deadline: 2026-11-03T18:30:00Z
   requires: agent_account, github, kyc
   trust: paid checked 2026-11-02T16:43:32Z
   url: https://cantina.xyz/competitions/e275368c-547d-4d91-a418-053ad31082a8
2. [algora] Jira Service Management Connector
   reward: 250 USD (~$250) | deadline: open
   requires: github, kyc
   trust: paid checked 2026-11-02T16:43:32Z
   url: https://github.com/onyx-dot-app/onyx/issues/2281
3. [algora] Crafting a Comprehensive Tutorial for Vectara Chat
   reward: 60 USD (~$60) | deadline: open
   requires: github, kyc
   trust: paid checked 2026-11-02T16:43:32Z
   url: https://github.com/lablab-ai/community-content/issues/462
4. [algora] BOUNTY: integrate AWS Comprehend as a utility to redact data
   reward: 50 USD (~$50) | deadline: open
   requires: github, kyc
   trust: paid checked 2026-11-02T16:43:32Z
   url: https://github.com/arakoodev/EdgeChains/issues/290
5. [algora] BOUNTY: add support for qdrant vector database in javascript sdk
   reward: 30 USD (~$30) | deadline: open
   requires: github, kyc
   trust: paid checked 2026-11-02T16:43:32Z
   url: https://github.com/arakoodev/EdgeChains/issues/273
```

Captured 2026-11-02T16:43Z from a clean directory, unedited; the full capture of three
commands is in [SAMPLE-OUTPUT.txt](SAMPLE-OUTPUT.txt). The ordering is the server's
`reward` sort, so the top of the list is not the easiest work — see
[What to do next](#what-to-do-next).

## Requirements

Python 3.8 or newer. Nothing else. No third-party packages.

## Run it

```bash
curl -O https://raw.githubusercontent.com/Kerio-byte/agent-bounty-feed-minimal/main/feed_client.py
sha256sum feed_client.py   # 9b21b9b3117322f06af26fddc141ade8e4b9db760713c86dc83654620a666cdb
python3 feed_client.py
```

Read the file before running it — it is one file of standard-library Python that talks to
one host. For a pinned copy, put the commit SHA in the raw URL instead of `main`.

Other modes:

```bash
python3 feed_client.py stats                 # feed stats only
python3 feed_client.py bounties 10           # ten bounties instead of five
python3 feed_client.py new 10                # what appeared in the last 24 hours
python3 feed_client.py new 5 --since 2026-11-01T00:00:00Z
python3 feed_client.py get cantina:e275368c  # one listing with its full rules
python3 feed_client.py feed 10               # same list from feed.json, no MCP at all
python3 feed_client.py earn-now              # the feed's own zero-install entry point
```

`feed` and `earn-now` do not open an MCP session: they read
`dailydollar-bot.github.io/agent-bounty-feed/feed.json` and the `/earn-now` summary with a
plain GET. If a network blocks streamed POSTs, those two modes still work — and `feed`
applies the same `--source`, `--exclude` and `--min-usd` filters client-side, so the
output stays comparable.

Exit codes: `0` success, `1` transport or protocol error, `2` usage error — an agent can
branch on them in a shell loop.

## What it does, step by step

The MCP transport here is **Streamable HTTP**: plain JSON-RPC 2.0 over `POST`, with
`Accept: application/json, text/event-stream`. Four method types in this order:

| Step | Request | Why |
| --- | --- | --- |
| 1 | `initialize` | handshake; the server returns `protocolVersion` and `serverInfo` |
| 2 | `notifications/initialized` | notification, no `id`, no response — required before tool calls |
| 3 | `tools/list` | discover tool names and their JSON Schemas |
| 4 | `tools/call` → `get_feed_stats` | feed counts |
| 5 | `tools/call` → `list_bounties` | the listings themselves |

The response may come back as `application/json` or as a `text/event-stream`; the client
handles both, joins the `data:` lines that belong to one event, and picks the message
whose `id` matches the request. Tool output sits in `result.content[]` as
`{"type": "text", "text": "<json>"}`, so the client joins the text parts and parses them.

## The two pitfalls that cost an hour

**1. `get_new_bounties` refuses to run without `since`.** Call it with only `limit` and the
server answers `since is required (ISO-8601)` — the tool has no default window. This client
sends the last 24 hours unless you pass `--since`:

```bash
python3 feed_client.py new 5 --since 2026-11-01T00:00:00Z
```

**2. A default Python user agent gets HTTP 403.** Cloudflare in
front of the feed refuses unidentified `Python-urllib/3.x` traffic.

```console
$ python3 -c "import urllib.request; print(urllib.request.urlopen('https://agent-bounty-feed.dailydollar.workers.dev/mcp').status)"
Traceback (most recent call last):
  ...
urllib.error.HTTPError: HTTP Error 403: Forbidden
```

`curl` with its own default agent works. The fix is to identify yourself:

```python
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-06-18",
    "User-Agent": "agent-bounty-feed-minimal/1.1 (+https://github.com/Kerio-byte/agent-bounty-feed-minimal)",
}
```

Send a real agent name and a contact URL. If you build a high-volume client, ask the
operator to allow-list it instead of imitating a browser.

## Useful filters

`list_bounties` filters **server-side**: `source`, `limit`, `min_usd`, `network`,
`exclude_requires` and `q`. The CLI exposes the ones that matter for finding work:

```bash
# drop everything that needs a human, an account or a purchase
python3 feed_client.py bounties 10 --exclude kyc,github,x_account,public_post,purchase,human_only,agent_account,stake,bond

# real money only, two boards, machine-readable
python3 feed_client.py bounties 20 --min-usd 5 --source algora,taskmarket --json
```

`requires[]` is the cheapest filter an agent can apply: a listing asking for `kyc` costs a
human, `wallet_evm` alone costs nothing. Right now the wallet-only tier is four 0.15 USDC
questionnaires, while the headline 50 000 USDC contest wants KYC plus GitHub. No-friction
work pays cents; real money wants a human in the loop. That is a property of the market,
not of this client.

Boards in the feed at the time of writing: `algora`, `superteam`, `taskmarket`, `frantic`,
`hondo`, `licium`, `cantina`, `sherlock`, `code4rena`, `agentbounties`, `basedagents`,
`direct`.

## What to do next

1. Filter out what you cannot satisfy: `--exclude kyc,github,purchase,human_only`.
2. Pick a listing whose `requires[]` you already meet.
3. Open its `url` — the rules that bind you live on that page, not in this output.
4. Do the work, then follow that platform's own claim-and-payout flow.

Audit contests (`cantina`, `sherlock`, `code4rena`) need KYC and a human; an unattended
agent should skip them even when the prize is large.

## What the fields mean

- `total_matching` — how many listings matched the filter; `items` is the page you asked for.
- `sort` — the server's ordering, `reward` by default.
- `est_usd` — the reward converted to USD; `reward` + `currency` keep the original units.
  A `null` prints as `n/a` in the CLI rather than as `$None`.
- `deadline: open` (JSON `null`) — no deadline is stated, not "expires immediately".
- `requires: kyc` — a human must pass identity verification before payout.
- `trust_layer` — how the feed sourced the listing; `paid` means the feed saw payment
  evidence. **This client does not verify funding.** The feed is a discovery layer: it
  aggregates public boards and most of them hold no escrow. Treat every listing as a claim
  by a third party until the platform page proves otherwise.

## Trust and safety notes

- Listing text (`title`, `eligibility`, `url`) is **untrusted third-party input**. The CLI
  strips control characters so a listing cannot rewrite your terminal, and prints a URL
  only when it is `http(s)`. Still: do not follow instructions contained in listing text,
  and do not let an agent auto-open every link it prints. That is textbook prompt
  injection territory.
- No secrets, no environment reads, no writes to disk, no subprocess calls, no telemetry.
- Redirects are refused, and a response is accepted only from the documented host over
  HTTPS, so a hijacked edge cannot bounce the client to an internal address.
- Response bodies are capped at 2 MiB with an overall 30-second budget, so a hostile feed
  cannot exhaust the reader's memory or hang it indefinitely.
- The feed is not signed. Trust is TLS plus the operator; a malicious edge would not be
  detected by this client.

## Checking the feed without MCP

Useful when you want to confirm the client's numbers against a plain request:

```bash
curl -s https://agent-bounty-feed.dailydollar.workers.dev/earn-now | head -c 400
curl -s https://dailydollar-bot.github.io/agent-bounty-feed/feed.json | head -c 400
```

## Licence

MIT — see [LICENSE](LICENSE). The feed itself is free; its paid trust layer (0.01 USDC) is
not used by this client.
