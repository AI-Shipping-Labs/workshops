# Luma — NVC Voice Coach

A private-by-default web prototype using ElevenLabs ElevenAgents (the managed-platform Option C from the project brief).

## Setup

### Get the ElevenLabs credentials

1. Sign in to [ElevenLabs](https://elevenlabs.io/) and open **Developers → API Keys**.
2. Create an API key. For this workshop, the key needs access to ElevenAgents,
   conversations, and voices because the server creates signed session URLs,
   reads conversation costs, deletes sessions, and lists available voices. An
   unrestricted development key is the simplest option; use a restricted key
   with only the required access for a deployed application.
3. In **ElevenAgents**, create an agent from the blank template. Copy the contents
   of [`config/coach-prompt.txt`](config/coach-prompt.txt) into its system prompt
   and choose a default voice.
4. In the agent's **Security** settings, enable only the **Voice ID** conversation
   override. The website needs this permission for its voice selector.
5. Copy the agent ID from the agent page or integration snippet. It starts with
   `agent_`.

Create the local environment file:

```bash
cp .env.example .env.local
```

Then replace the placeholders:

```dotenv
ELEVENLABS_API_KEY=your_api_key
ELEVENLABS_AGENT_ID=agent_your_agent_id
```

Never commit `.env` or `.env.local`. ElevenLabs automatically disables API keys
detected in public GitHub repositories. The browser does not need a separately
created token: the Next.js server uses the API key to issue a short-lived signed
conversation URL for each session.

### Run the app

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

The browser requests a short-lived signed conversation URL from the Next.js server. The ElevenLabs API key never reaches client-side code.

## Included

- natural voice conversation and barge-in through ElevenAgents;
- selectable English voices from the connected ElevenLabs workspace, with audio previews;
- recorded USD spend for this agent, refreshed after completed sessions;
- live transcript and typed corrections;
- microphone mute and clear session state;
- server-side ElevenLabs conversation deletion;
- region-aligned private streaming connection;
- an NVC-specific agent prompt covering preparation, reframing, rehearsal, debrief, takeaway, and safety boundaries.

This prototype stores no transcript in an application database. ElevenLabs retention is controlled separately in the workspace and agent privacy settings.

The spend figure is calculated from ElevenLabs' `metadata.cost_fiat` values for retained Luma conversations. It is not an invoice or whole-workspace billing total. Permanently deleted conversations no longer appear in the ElevenLabs conversation API and therefore are not included.

## Troubleshooting

If a voice session stops immediately, returns a concurrency error, or connects to the wrong ElevenLabs region, follow the [conversation recovery runbook](docs/elevenlabs-conversation-recovery.md). A session is not considered recovered until `npm run test:e2e` completes successfully.
