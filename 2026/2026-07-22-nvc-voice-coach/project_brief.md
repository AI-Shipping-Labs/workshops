# NVC Voice Coach — Project Brief

## 1. Product Idea

We are building a natural-sounding voice assistant that helps people prepare for difficult or emotionally sensitive conversations using the principles of Nonviolent Communication (NVC).

The main use case is preparation before a real conversation. A user may have an unresolved issue with a friend, partner, colleague, or family member and wants to discuss it without becoming accusatory, defensive, or overwhelmed.

The user speaks naturally with the voice coach. The coach listens, asks focused questions, helps clarify the situation, and guides the user toward a constructive way of expressing themselves.

The product should feel like a real conversation rather than a voice-controlled form. The user should be able to pause, correct themselves, add context, or interrupt the coach while it is speaking. The coach should then respond naturally and continue from the updated context.

## 2. Core Problem

People often know that they want to address a conflict, but they may struggle to:

- explain what happened without exaggeration or blame;
- separate observable facts from judgments;
- identify what they are actually feeling;
- understand the needs or values behind those feelings;
- formulate a clear and respectful request;
- prepare for a defensive or emotional response;
- stay calm and constructive during the real conversation.

The app helps users organize their thoughts and rehearse the conversation before speaking with the other person.

## 3. Proposed Solution

The NVC Voice Coach guides the user through four central elements of Nonviolent Communication:

1. **Observation** — What happened, described without judgment.
2. **Feeling** — What emotions the situation created.
3. **Need** — What underlying value, need, or expectation was affected.
4. **Request** — What specific and realistic action the user would like to ask for.

The coach should not force the conversation into a rigid questionnaire. It should listen to the user's story, identify what is already clear, and ask only the next most useful question.

## 4. Example User Journey

A user says:

> “My friend cancelled on me again, and I feel like they do not respect my time.”

The coach may respond:

> “When you say they did not respect your time, what happened that someone else could have observed?”

The user explains:

> “They cancelled two meetings on the same day.”

The coach then helps identify feelings, needs, and a request. At the end, it may produce a draft such as:

> “When our plans were cancelled on the same day twice, I felt disappointed and uncertain. Reliability and consideration are important to me. Would you be willing to let me know earlier when you think the plans may change?”

The user can then rehearse the conversation with the coach and receive feedback.

## 5. Main Product Modes

### Prepare

The user describes the conflict or unresolved situation. The coach asks short, focused questions and helps structure the situation.

### Reframe

The coach identifies language that may sound blaming, vague, judgmental, or inflammatory and helps rewrite it more constructively.

### Rehearse

The coach role-plays the other person. The user can practise responding to cooperative, confused, defensive, or emotional reactions.

### Debrief

After a role-play, the coach gives concise feedback about clarity, tone, blame, empathy, and the quality of the request.

### Takeaway

The app produces a written summary that the user can read before the real conversation. This is important because some users may prefer speaking as input but reading the final result.

## 6. Experience Requirements

The voice experience should feel natural and conversational.

Important requirements include:

- low response latency;
- streaming speech recognition;
- natural text-to-speech;
- interruption or barge-in support;
- accurate turn detection;
- short and focused coach responses;
- conversation memory;
- a live or final transcript;
- a written NVC summary;
- support for corrections and added context;
- a calm, warm, and non-judgmental voice.

The assistant should not sound excessively therapeutic, dramatic, or artificial. It should be attentive and supportive without taking sides.

## 7. Selected Technical Options

We selected **Option A** and **Option C** for further exploration.

---

# Option A — Modular Speech Pipeline

## Architecture

```text
Microphone
   ↓
Voice Activity and Turn Detection
   ↓
Streaming Speech-to-Text
   ↓
Language Model and NVC Coaching Logic
   ↓
Streaming Text-to-Speech
   ↓
Speaker
```

This architecture separates the system into individual components:

- speech-to-text converts the user's voice into text;
- a language model analyses the conversation and generates the coaching response;
- text-to-speech converts the response back into audio.

## Possible Technology Choices

### Speech-to-Text

- Deepgram
- OpenAI speech recognition
- ElevenLabs Scribe
- self-hosted Whisper-based models

### Language Model

- OpenAI models
- Google Gemini
- Anthropic Claude
- another model that supports structured outputs and tool calls

### Text-to-Speech

- ElevenLabs
- OpenAI audio models
- Deepgram TTS
- Google audio models

### Voice Orchestration

- LiveKit Agents
- Pipecat
- a custom WebRTC or WebSocket implementation

## Advantages

- Each component can be selected and replaced independently.
- The transcript is easy to inspect, display, and store.
- The NVC reasoning process is easier to evaluate and debug.
- The app can generate structured data for observations, feelings, needs, and requests.
- Safety checks can be performed before a response is spoken.
- The product can support both spoken and written output.
- It is easier to compare providers for transcription, reasoning, and voice quality.

## Disadvantages

- Every step adds latency.
- More engineering and integration work is required.
- Some emotion, tone, and vocal nuance may be lost during transcription.
- Turn-taking and interruption handling must be carefully implemented.
- Failures can occur at several different points in the pipeline.

## Why Option A Fits This Product

The modular architecture gives us strong control over the coaching behaviour. This is especially useful because the product handles emotionally sensitive situations and should not behave like a generic chatbot.

We can inspect what the user said, maintain structured NVC state, test the quality of the coach's reasoning, and provide a readable summary at the end.

---

# Option C — Managed Voice-Agent Platform

## Architecture

```text
Client Application
   ↓
Managed Voice-Agent Platform
   ├── Speech Recognition
   ├── Turn Detection
   ├── Interruption Handling
   ├── Language Model Integration
   ├── Text-to-Speech
   └── Monitoring and Session Management
   ↓
Audio Response
```

A managed voice-agent platform provides several parts of the voice system in one service. Instead of connecting every component manually, we configure the platform, choose a voice and model, and define the coach's instructions and tools.

## Possible Technology Choices

- ElevenLabs ElevenAgents
- Deepgram Voice Agent API
- LiveKit Agents with managed model integrations
- other conversational voice-agent platforms

## Advantages

- Faster to build and test.
- Less infrastructure and orchestration work.
- Turn-taking and interruptions may already be supported.
- Voice, latency, session management, and monitoring can be handled by one platform.
- Useful for early prototypes, demonstrations, and user testing.
- Makes it easier to evaluate whether users actually prefer voice interaction.

## Disadvantages

- Greater dependence on one provider.
- Less control over some parts of the pipeline.
- Provider-specific limitations may affect the conversation design.
- Costs may increase as usage grows.
- Moving to another platform later may require significant work.
- Debugging the internal behaviour may be more difficult.

## Why Option C Fits This Product

The managed approach allows us to create a realistic voice prototype quickly. It is a good way to test the central product assumption:

> Does a natural voice conversation make NVC preparation more useful, comfortable, and engaging than a text-only experience?

Instead of spending the first phase building audio infrastructure, we can focus on the coaching experience, prompts, role-play behaviour, and user feedback.

---

## 8. Recommended Evaluation Approach

Rather than choosing one architecture immediately, we should prototype and compare both.

### Prototype A — Modular Pipeline

A possible stack:

```text
Frontend: React, Next.js, or React Native
Audio Transport: WebRTC
Speech-to-Text: Deepgram
Language Model: OpenAI or another structured-output model
Text-to-Speech: ElevenLabs
Orchestration: LiveKit Agents or Pipecat
Backend: Node.js, TypeScript, or Python
Storage: PostgreSQL or temporary session storage
```

### Prototype C — Managed Platform

A possible stack:

```text
Frontend: React, Next.js, or React Native
Audio Transport: WebRTC or provider SDK
Voice Platform: ElevenAgents or Deepgram Voice Agent API
Language Model: provider-supported model or external LLM
Backend: lightweight application server
Storage: transcript and structured NVC session state
```

## 9. Comparison Criteria

The two prototypes should be tested using the same example conversations.

Important metrics include:

- time until the coach starts speaking;
- transcription accuracy;
- voice naturalness;
- interruption success rate;
- turn-taking quality;
- usefulness of the coach's questions;
- quality of the final NVC formulation;
- how often the coach talks too much;
- user comfort and trust;
- quality of role-play;
- ease of debugging;
- development effort;
- cost per session;
- privacy and data-retention options.

## 10. Recommended First Scope

The first version should focus on one user preparing before a real conversation.

It should not initially listen to two people during a live conflict or automatically interject. A live mediation mode would create additional challenges involving consent, privacy, speaker identification, timing, and emotional safety.

The first version should include:

- one-to-one voice conversation with the coach;
- live interruption support;
- transcript display;
- NVC clarification questions;
- structured observation, feeling, need, and request extraction;
- role-play;
- concise feedback;
- a final written conversation plan;
- an option to delete the session.

## 11. Safety and Privacy Principles

The app will process sensitive information about relationships, conflict, emotions, and possibly abuse or trauma.

The product should therefore:

- clearly state that it is a communication-preparation tool, not a therapist;
- avoid deciding who is right or wrong;
- avoid automatically encouraging confrontation;
- obtain consent before recording anyone other than the user;
- avoid ambient or hidden recording;
- minimize the retention of raw audio;
- make transcript and audio deletion easy;
- explain which service providers process the audio;
- encrypt stored data;
- provide a private-session mode;
- recommend human or professional support when the situation is outside the coach's role.

## 12. Initial Product Goal

The goal of the first phase is not to build the complete final platform.

The goal is to validate three assumptions:

1. Users are comfortable describing sensitive conflicts to a voice coach.
2. Voice interaction provides meaningful value beyond text input.
3. The coach can consistently help users create a clearer and more constructive conversation plan.

By testing Option A and Option C in parallel, we can compare flexibility and control against speed and simplicity, then choose the architecture that best supports the actual user experience.
