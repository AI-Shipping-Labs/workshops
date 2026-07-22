# ElevenLabs conversation recovery runbook

Use this runbook when **Begin conversation** immediately stops, the app cannot create a private session, or ElevenLabs reports that the workspace has reached its conversation limit.

## Known failure modes

### WebRTC region mismatch

Symptoms in the browser console:

```text
wss://livekit.rtc.eu.residency.elevenlabs.io/rtc ... 401
WebSocket closed with code 1006
```

This happens when a token issued by the standard ElevenLabs API is sent to the EU-residency LiveKit endpoint. `eu-residency` is not merely a choice of the nearest server; the ElevenLabs workspace must support that residency region.

Recovery:

1. Use the same region for URL/token issuance and the client connection.
2. For this project, use the standard `us` region.
3. Do not configure `eu-residency` unless the ElevenLabs workspace itself has EU residency enabled.

The current app explicitly sets `serverLocation: "us"` and uses a standard-region signed URL.

### Workspace concurrency reservation

Server response:

```json
{
  "detail": {
    "code": "concurrent_limit_exceeded",
    "status": "workspace_concurrency_limit_exceeded",
    "message": "Workspace has reached its maximum concurrent capacity. Please try again later."
  }
}
```

In the original implementation this appeared to the browser as HTTP 502. Repeatedly requesting WebRTC conversation tokens made recovery harder because unconsumed or failed token reservations could temporarily occupy the workspace slot.

## Recovery procedure

### 1. Stop creating new WebRTC tokens

Close old app tabs and stop any automated test that repeatedly calls:

```text
GET /v1/convai/conversation/token
```

Do not poll this endpoint while the workspace is locked. A successful request can create another short-lived reservation.

### 2. Check for real conversations

Load the local environment and list only this agent's conversations:

```bash
set -a
. ./.env
. ./.env.local
set +a

curl --fail-with-body --silent --show-error \
  "https://api.elevenlabs.io/v1/convai/conversations?agent_id=${ELEVENLABS_AGENT_ID}&page_size=20" \
  -H "xi-api-key: ${ELEVENLABS_API_KEY}" \
  | jq '.conversations[] | {
      conversation_id,
      status,
      start_time_unix_secs,
      call_duration_secs,
      message_count,
      termination_reason
    }'
```

If a known failed test conversation is still active, close its browser/client session first. Delete it only when its identity and disposable status are certain:

```bash
curl --fail-with-body --silent --show-error \
  -X DELETE \
  "https://api.elevenlabs.io/v1/convai/conversations/CONVERSATION_ID" \
  -H "xi-api-key: ${ELEVENLABS_API_KEY}"
```

Deletion is permanent. Never bulk-delete conversations or delete an ID that has not been inspected.

### 3. Handle an invisible reservation

Sometimes the token endpoint reports `workspace_concurrency_limit_exceeded` while the conversations API returns an empty list. In our incident, reservation conversation IDs returned 404 and therefore could not be deleted through the conversations API.

In that case:

1. Stop requesting more WebRTC tokens.
2. Allow the outstanding token/reservation window to expire. Tokens observed during this incident had a 15-minute lifetime.
3. Prefer the signed-WebSocket path below instead of waiting if service needs to be restored immediately.

### 4. Use the signed-WebSocket path

The current application uses:

```text
GET /v1/convai/conversation/get-signed-url
```

and starts the ElevenLabs SDK with:

```ts
conversation.startSession({
  signedUrl,
  connectionType: "websocket",
  serverLocation: "us",
});
```

This is private: the API key remains on the Next.js server, while the browser receives only a short-lived signed URL. During the incident this endpoint returned HTTP 200 and completed a voice session even while the WebRTC token endpoint returned a concurrency error.

Do not switch the app back to `conversationToken` without first testing token lifecycle, cleanup, reconnection, and region behavior.

## Required verification

Do not declare the service recovered based only on a successful credential endpoint request. Run the browser-level voice test:

```bash
npm run test:e2e
```

The test is successful only when all of these are true:

- Chromium grants fake microphone access;
- the private ElevenLabs connection is established;
- Luma's first agent message reaches the live transcript;
- the client ends the session cleanly;
- there are no browser console errors;
- there are no failed browser requests.

Then run the local checks:

```bash
npm run lint
npm run build
npm audit --omit=dev
```

Automated tests create real ElevenLabs conversations. Inspect and delete only those synthetic test conversations after the test finishes.

## Unrelated browser messages

These messages did not cause the voice failure:

- `cz-shortcut-listen="true"` hydration mismatch: a browser extension modified `<body>` before React hydrated.
- `Unable to add filesystem: <illegal path>`: a browser DevTools or extension filesystem-workspace message.
- a favicon 404: cosmetic; the app now includes `app/icon.svg`.

Confirm suspected application failures in a clean automated Chromium run before treating extension messages as product bugs.
