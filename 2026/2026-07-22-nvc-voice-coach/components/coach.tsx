"use client";

import {
  ConversationProvider,
  useConversation,
  useConversationInput,
  useConversationMode,
  useConversationStatus,
} from "@elevenlabs/react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type TranscriptItem = {
  id: string;
  role: "user" | "agent";
  text: string;
};

type ConversationMessage = {
  message?: string;
  source?: "user" | "ai";
  role?: "user" | "agent";
  type?: string;
};

type VoiceOption = {
  voiceId: string;
  name: string;
  category: string;
  previewUrl: string | null;
  accent: string | null;
  gender: string | null;
  description: string | null;
};

type CostSummary = {
  totalUsd: number;
  conversationCount: number;
  pricedConversationCount: number;
};

const steps = ["Observation", "Feeling", "Need", "Request"];

export function Coach() {
  const [messages, setMessages] = useState<TranscriptItem[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [costRefreshKey, setCostRefreshKey] = useState(0);

  const onMessage = useCallback((message: ConversationMessage) => {
    if (!message.message) return;
    const role = message.source === "user" || message.role === "user" ? "user" : "agent";
    setMessages((current) => [
      ...current,
      { id: `${Date.now()}-${current.length}`, role, text: message.message! },
    ]);
  }, []);

  return (
    <ConversationProvider
      onMessage={onMessage}
      onConnect={({ conversationId: id }) => setConversationId(id)}
      onError={(message) => setConnectionError(message)}
      onDisconnect={(details) => {
        if (details.reason === "error") setConnectionError(details.message);
        setCostRefreshKey((key) => key + 1);
      }}
      serverLocation="us"
    >
      <CoachExperience
        messages={messages}
        clearMessages={() => setMessages([])}
        conversationId={conversationId}
        clearConversationId={() => setConversationId(null)}
        connectionError={connectionError}
        clearConnectionError={() => setConnectionError(null)}
        costRefreshKey={costRefreshKey}
        requestCostRefresh={() => setCostRefreshKey((key) => key + 1)}
      />
    </ConversationProvider>
  );
}

function CoachExperience({
  messages,
  clearMessages,
  conversationId,
  clearConversationId,
  connectionError,
  clearConnectionError,
  costRefreshKey,
  requestCostRefresh,
}: {
  messages: TranscriptItem[];
  clearMessages: () => void;
  conversationId: string | null;
  clearConversationId: () => void;
  connectionError: string | null;
  clearConnectionError: () => void;
  costRefreshKey: number;
  requestCostRefresh: () => void;
}) {
  const conversation = useConversation();
  const { status } = useConversationStatus();
  const { isSpeaking, isListening } = useConversationMode();
  const { isMuted, setMuted } = useConversationInput();
  const [error, setError] = useState<string | null>(null);
  const [typedMessage, setTypedMessage] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState("");
  const [voicesLoading, setVoicesLoading] = useState(true);
  const [costs, setCosts] = useState<CostSummary | null>(null);
  const [costsLoading, setCostsLoading] = useState(true);
  const [previewingVoiceId, setPreviewingVoiceId] = useState<string | null>(null);
  const transcriptEnd = useRef<HTMLDivElement>(null);
  const previewAudio = useRef<HTMLAudioElement | null>(null);

  const connected = status === "connected";
  const activeStep = useMemo(() => Math.min(Math.floor(messages.length / 3), 3), [messages.length]);

  const loadCosts = useCallback(async () => {
    try {
      const response = await fetch("/api/elevenlabs/costs", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load spending.");
      setCosts((await response.json()) as CostSummary);
    } catch {
      setCosts(null);
    } finally {
      setCostsLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    fetch("/api/elevenlabs/voices")
      .then(async (response) => {
        if (!response.ok) throw new Error("Could not load voices.");
        return response.json() as Promise<{ voices: VoiceOption[]; defaultVoiceId: string }>;
      })
      .then((data) => {
        if (!active) return;
        setVoices(data.voices);
        setSelectedVoiceId(data.defaultVoiceId || data.voices[0]?.voiceId || "");
      })
      .catch(() => setVoices([]))
      .finally(() => {
        if (active) setVoicesLoading(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(loadCosts, 0);
    if (costRefreshKey === 0) return () => window.clearTimeout(initialLoad);
    const firstRetry = window.setTimeout(loadCosts, 2500);
    const secondRetry = window.setTimeout(loadCosts, 8000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearTimeout(firstRetry);
      window.clearTimeout(secondRetry);
    };
  }, [costRefreshKey, loadCosts]);

  useEffect(() => () => previewAudio.current?.pause(), []);

  function toggleVoicePreview(voice: VoiceOption) {
    if (!voice.previewUrl) return;
    if (previewingVoiceId === voice.voiceId) {
      previewAudio.current?.pause();
      setPreviewingVoiceId(null);
      return;
    }
    previewAudio.current?.pause();
    const audio = new Audio(voice.previewUrl);
    previewAudio.current = audio;
    setPreviewingVoiceId(voice.voiceId);
    audio.onended = () => setPreviewingVoiceId(null);
    audio.onerror = () => setPreviewingVoiceId(null);
    void audio.play();
  }

  async function startConversation() {
    setError(null);
    clearConnectionError();
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      const response = await fetch("/api/elevenlabs/signed-url");
      const data = (await response.json()) as { signedUrl?: string; error?: string };
      if (!response.ok || !data.signedUrl) throw new Error(data.error || "Could not start the session.");
      conversation.startSession({
        signedUrl: data.signedUrl,
        connectionType: "websocket",
        serverLocation: "us",
        ...(selectedVoiceId ? { overrides: { tts: { voiceId: selectedVoiceId } } } : {}),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Microphone access could not be started.");
    }
  }

  async function endConversation() {
    await conversation.endSession();
  }

  function sendTypedMessage(event: FormEvent) {
    event.preventDefault();
    const text = typedMessage.trim();
    if (!text || !connected) return;
    conversation.sendUserMessage(text);
    setTypedMessage("");
  }

  async function deleteSession() {
    if (!window.confirm("Delete this conversation and its transcript? This cannot be undone.")) return;
    setDeleting(true);
    setError(null);
    try {
      if (connected) await conversation.endSession();
      if (conversationId) {
        const response = await fetch(`/api/conversations/${conversationId}`, { method: "DELETE" });
        if (!response.ok) {
          const data = (await response.json()) as { error?: string };
          throw new Error(data.error || "Could not delete this session.");
        }
      }
      clearMessages();
      clearConversationId();
      requestCostRefresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete this session.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="Luma home">
          <span className="brand-mark">L</span>
          <span>Luma</span>
        </a>
        <div className="header-actions">
          <div className="cost-pill" title="USD total from retained Luma conversation history">
            <small>Recorded spend</small>
            <strong>{costsLoading ? "—" : formatUsd(costs?.totalUsd ?? 0)}</strong>
            <span>{costs?.conversationCount ?? 0} sessions</span>
          </div>
          <div className="privacy-pill"><span /> Private session</div>
        </div>
      </header>

      <section className="intro">
        <p className="eyebrow">NVC voice coach</p>
        <h1>Find the words<br />before the moment.</h1>
        <p className="lede">A calm space to prepare for conversations that matter.</p>
      </section>

      <section className="workspace">
        <div className="conversation-card">
          <div className="card-header">
            <div>
              <p className="section-label">Your conversation</p>
              <h2>{connected ? (isSpeaking ? "Luma is speaking" : isListening ? "I’m listening" : "We’re connected") : "Ready when you are"}</h2>
            </div>
            <div className={`status-dot ${connected ? "live" : ""}`} aria-label={status} />
          </div>

          <div className={`voice-orb ${isSpeaking ? "speaking" : ""} ${isListening ? "listening" : ""}`}>
            <div className="orb-core">
              {[0, 1, 2, 3, 4].map((bar) => <i key={bar} />)}
            </div>
          </div>

          <p className="voice-hint">
            {connected ? "Speak naturally — you can interrupt or correct yourself anytime." : "Your microphone starts only after you choose to begin."}
          </p>

          {(error || connectionError) && <p className="error" role="alert">{error || connectionError}</p>}

          <div className="voice-picker">
            <div>
              <label htmlFor="coach-voice">Coach voice</label>
              <p>{voicesLoading ? "Loading your voices…" : "Choose a voice for this session"}</p>
            </div>
            <div className="voice-select-wrap">
              <select
                id="coach-voice"
                value={selectedVoiceId}
                disabled={connected || voicesLoading || voices.length === 0}
                onChange={(event) => {
                  setSelectedVoiceId(event.target.value);
                  previewAudio.current?.pause();
                  setPreviewingVoiceId(null);
                }}
              >
                {voices.map((voice) => (
                  <option value={voice.voiceId} key={voice.voiceId}>
                    {voice.name}{voice.accent ? ` · ${voice.accent}` : ""}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="preview-button"
                aria-label={previewingVoiceId === selectedVoiceId ? "Stop voice preview" : "Preview selected voice"}
                disabled={!voices.find((voice) => voice.voiceId === selectedVoiceId)?.previewUrl}
                onClick={() => {
                  const voice = voices.find((item) => item.voiceId === selectedVoiceId);
                  if (voice) toggleVoicePreview(voice);
                }}
              >
                {previewingVoiceId === selectedVoiceId ? "■" : "▶"}
              </button>
            </div>
          </div>

          <div className="primary-controls">
            {!connected ? (
              <button className="button primary" onClick={startConversation} disabled={status === "connecting"}>
                <MicIcon /> {status === "connecting" ? "Connecting…" : "Begin conversation"}
              </button>
            ) : (
              <>
                <button className="button secondary" onClick={() => setMuted(!isMuted)}>
                  {isMuted ? <MicIcon /> : <MuteIcon />} {isMuted ? "Unmute" : "Mute"}
                </button>
                <button className="button end" onClick={endConversation}>End session</button>
              </>
            )}
          </div>

          <p className="consent">By beginning, you agree that your audio is processed by ElevenLabs. Luma is a preparation tool, not a therapist or crisis service.</p>
        </div>

        <aside className="side-panel">
          <div className="progress-block">
            <p className="section-label">Conversation map</p>
            <ol className="steps">
              {steps.map((step, index) => (
                <li className={index <= activeStep && messages.length ? "active" : ""} key={step}>
                  <span>{index + 1}</span><div><strong>{step}</strong><small>{["What happened?", "What came up?", "What matters?", "What could help?"][index]}</small></div>
                </li>
              ))}
            </ol>
          </div>

          <div className="transcript-block">
            <div className="transcript-title">
              <p className="section-label">Live transcript</p>
              {messages.length > 0 && <span>{messages.length} turns</span>}
            </div>
            <div className="transcript" aria-live="polite">
              {messages.length === 0 ? (
                <p className="empty">Your conversation will appear here as you speak.</p>
              ) : messages.map((item) => (
                <div className={`message ${item.role}`} key={item.id}>
                  <span>{item.role === "user" ? "You" : "Luma"}</span>
                  <p>{item.text}</p>
                </div>
              ))}
              <div ref={transcriptEnd} />
            </div>

            <form className="text-input" onSubmit={sendTypedMessage}>
              <input
                aria-label="Type a message"
                placeholder={connected ? "Or type a correction…" : "Start a session to type"}
                value={typedMessage}
                disabled={!connected}
                onChange={(event) => {
                  setTypedMessage(event.target.value);
                  conversation.sendUserActivity();
                }}
              />
              <button aria-label="Send" disabled={!connected || !typedMessage.trim()}>↗</button>
            </form>
          </div>
        </aside>
      </section>

      <footer>
        <p><ShieldIcon /> Audio isn’t stored by this app. ElevenLabs may retain conversation data according to your workspace settings.</p>
        <button className="delete-button" onClick={deleteSession} disabled={deleting || (!conversationId && !messages.length)}>
          {deleting ? "Deleting…" : "Delete session"}
        </button>
      </footer>
    </main>
  );
}

function MicIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="3" width="8" height="12" rx="4" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" /></svg>;
}

function MuteIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 9v2a3 3 0 0 0 5.1 2.1M15 9V7a3 3 0 0 0-5.8-1M5 11a7 7 0 0 0 11.7 5.2M19 11a7 7 0 0 1-.5 2.6M12 18v3M9 21h6M3 3l18 18" /></svg>;
}

function ShieldIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 5 6v5c0 4.4 2.8 8.4 7 10 4.2-1.6 7-5.6 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></svg>;
}

function formatUsd(amount: number) {
  const showFinePrecision = amount > 0 && amount < 1;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: showFinePrecision ? 4 : 2,
    maximumFractionDigits: showFinePrecision ? 4 : 2,
  }).format(amount);
}
