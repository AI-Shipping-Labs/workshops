# Testing the Eve agent over the API (curl)

This documents exactly how I verified the agent works end to end, without a
browser. Eve exposes a **durable session API**, so talking to it is a two-step
dance: **(1) open a session** with your message, then **(2) attach to that
session's stream** to watch it think, call tools, and answer.

Unlike Option 1 (one request → one streamed response), an Eve session is a
*durable* thing: the POST kicks off work that keeps running server-side even if
you disconnect, and you can attach/re-attach to its stream.

## 0. Have the server running

```sh
npm run dev    # Next dev server on http://localhost:3000 (serves the agent too)
```

The agent's API lives under `/eve/v1/...` on that same origin (mounted by
`withEve` in `next.config.ts`).

## 1. Open a session (POST)

```sh
curl -i -X POST http://localhost:3000/eve/v1/session \
  -H 'content-type: application/json' \
  -d '{"message":"How do I install the course dependencies?"}'
```

`-i` prints the response headers — that matters here, because the **session id
comes back in a header**, not just the body:

```
HTTP/1.1 202 Accepted
x-eve-session-id: wrun_01KVZ8J2WRB0ZMXQP86GXKNWZ4

{"continuationToken":"eve:a8aa9d7d-...","ok":true,"sessionId":"wrun_01KVZ8J2WRB0ZMXQP86GXKNWZ4"}
```

What this tells you:
- **`202 Accepted`** — the work was *accepted and started*, not finished. (Compare
  to Option 1's `200` with the answer in the body.) The agent is now running as a
  durable session.
- **`x-eve-session-id`** (also `sessionId` in the body) — the handle you use to
  watch or resume the session. Grab it for step 2.
- **`continuationToken`** — used to send a follow-up message into the *same*
  session later (multi-turn).

Grab the id programmatically:

```sh
SID=$(curl -s -i -X POST http://localhost:3000/eve/v1/session \
  -H 'content-type: application/json' \
  -d '{"message":"How do I install the course dependencies?"}' \
  | grep -i '^x-eve-session-id:' | tr -d '\r' | awk '{print $2}')
echo "$SID"
```

## 2. Attach to the session stream (GET)

```sh
curl -N http://localhost:3000/eve/v1/session/$SID/stream
```

`-N` disables curl's buffering so you see events live. The stream is **NDJSON** —
one JSON lifecycle event per line. For the question above, the real sequence was:

```
{"type":"session.started"}
{"type":"turn.started"}
{"type":"message.received"}
{"type":"step.started"}
... "type":"tool-call"  "toolName":"search"     ← model decided to search the FAQ
{"type":"actions.requested"}
... "type":"tool-result" ... uv ...             ← MiniSearch returned FAQ hits (the uv setup)
{"type":"step.completed"}
{"type":"step.started"}
{"type":"message.appended"} ...Delta...         ← the answer streams in, token by token
{"type":"message.appended"} ...
```

That end-to-end chain is the proof the agent works:
**session.started → tool-call `search` → tool-result → message deltas (the answer).**
It mirrors Option 1's `tool-input → tool-output → text-delta`, just with Eve's
durable-session event names.

### Handy one-liners I used

See just the high-level lifecycle + which tool ran:

```sh
curl -sN http://localhost:3000/eve/v1/session/$SID/stream \
  | grep -oE '"type":"[^"]*"|"toolName":"[^"]*"'
```

Because the session is durable, you can re-run that GET and it **replays** the
recorded events — re-attaching to a session that already finished is fine.

## 3. (Optional) the terminal UI

For interactive poking without curl, Eve ships a TUI:

```sh
npx eve dev          # type questions, watch tool calls/reasoning render live
```

## Same thing in production

After `eve deploy`, the API is identical — just swap the origin:

```sh
curl -i -X POST https://<your-eve-project>.vercel.app/eve/v1/session \
  -H 'content-type: application/json' \
  -d '{"message":"Can I still join the course?"}'
```

(Production also enforces the channel auth in `agent/channels/eve.ts` — the
default `placeholderAuth()` blocks anonymous browser requests; see the README.)
