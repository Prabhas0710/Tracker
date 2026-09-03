"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ChatAttachFab, { type AttachKind } from "@/components/ChatAttachFab";
import { api } from "@/lib/api";
import type { ChatMessage } from "@/types/analytics";

type Message = ChatMessage;

const STARTERS = [
  "How much did I spend this month?",
  "What did I eat today?",
  "Change Myntra to Shopping",
  "Set my protein goal to 140",
];

function isPageReload(): boolean {
  if (typeof window === "undefined") return false;
  const entry = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
  if (entry?.type === "reload") return true;
  // Older Safari fallback
  const legacy = (performance as Performance & { navigation?: { type?: number } }).navigation;
  return legacy?.type === 1;
}

function splitBriefing(content: string) {
  const lines = content.split("\n").filter(Boolean);
  const headline = lines[0] ?? "Welcome back, Prabhas.";
  const festival = lines[1]?.startsWith("Happy ") ? lines[1] : null;
  const bodyStart = festival ? 2 : 1;
  const body = lines.slice(bodyStart).join("\n").trim();
  return { headline, festival, body };
}

export default function ChatHome() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedId = searchParams.get("c");
  const wantNew = searchParams.has("new");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [briefingText, setBriefingText] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceLevel, setVoiceLevel] = useState(0);
  const endRef = useRef<HTMLDivElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const silenceRafRef = useRef<number | null>(null);
  const heardSpeechRef = useRef(false);

  const clearSilenceWatch = () => {
    if (silenceRafRef.current != null) {
      cancelAnimationFrame(silenceRafRef.current);
      silenceRafRef.current = null;
    }
    const ctx = audioContextRef.current;
    audioContextRef.current = null;
    if (ctx) void ctx.close().catch(() => undefined);
  };

  useEffect(() => {
    return () => {
      clearSilenceWatch();
      mediaRecorderRef.current?.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const briefing = await api.ensureChatBriefing();

        // Refresh always starts a fresh chat; prior threads stay in History.
        if (isPageReload() || wantNew) {
          setConversationId(null);
          setMessages([]);
          setBriefingText(briefing.message);
          if (requestedId || wantNew) router.replace("/");
          return;
        }

        // Only continue a chat when opened from History (?c=id).
        const id = requestedId ? Number(requestedId) : NaN;
        if (Number.isFinite(id) && id > 0) {
          try {
            const conv = await api.getChatConversation(id);
            setConversationId(conv.id);
            setMessages(conv.messages);
            setBriefingText(null);
            return;
          } catch {
            router.replace("/");
          }
        }

        setConversationId(null);
        setMessages([]);
        setBriefingText(briefing.message);
      } catch {
        /* offline or first visit */
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [requestedId, wantNew, router]);

  const hasUserMessages = messages.some((msg) => msg.role === "user");
  const briefing = useMemo(() => {
    if (hasUserMessages) return null;
    const source =
      briefingText ||
      [...messages].reverse().find((msg) => msg.role === "assistant" && msg.content.startsWith("Welcome back"))
        ?.content;
    if (!source?.startsWith("Welcome back")) return null;
    return splitBriefing(source);
  }, [messages, hasUserMessages, briefingText]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, loading]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: trimmed }]);
    setBusy(true);
    setError(null);
    try {
      const result = await api.chat(trimmed, undefined, conversationId ?? undefined);
      setMessages((m) => [...m, { role: "assistant", content: result.reply }]);
      // Keep id in memory for this tab session only — do not put it in the URL,
      // so a browser refresh starts a new chat. History still lists this thread.
      if (result.conversation_id) setConversationId(result.conversation_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setBusy(false);
    }
  };

  const stopListening = () => {
    clearSilenceWatch();
    setVoiceLevel(0);
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  };

  const startListening = async () => {
    if (busy || loading || listening || transcribing) return;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Microphone is not supported in this browser");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "";
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      heardSpeechRef.current = false;
      setVoiceLevel(0);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        clearSilenceWatch();
        setListening(false);
        setVoiceLevel(0);
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        mediaRecorderRef.current = null;
        const spoke = heardSpeechRef.current;
        heardSpeechRef.current = false;
        const type = recorder.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        chunksRef.current = [];

        // No real speech → never send to chat (avoids Whisper hallucinations).
        if (!spoke || !blob.size) {
          setError("Voice not heard, please say again");
          return;
        }

        setTranscribing(true);
        try {
          const ext = type.includes("mp4") ? "m4a" : "webm";
          const result = await api.transcribeAudio(blob, `chat.${ext}`);
          const text = (result.text || "").trim();
          if (!text) {
            setError("Voice not heard, please say again");
            return;
          }
          await send(text);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not understand audio");
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setListening(true);

      // Auto-stop after ~2s of silence once sustained speech is heard.
      // If nothing is said for a while, stop and ask to try again.
      const SILENCE_MS = 2000;
      const NO_SPEECH_MS = 6000;
      const SPEECH_RMS = 0.022;
      const SPEECH_HOLD_MS = 280;
      const listenStartedAt = performance.now();
      try {
        const AudioCtx =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        const ctx = new AudioCtx();
        audioContextRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 2048;
        source.connect(analyser);
        const samples = new Uint8Array(analyser.fftSize);
        let heardSpeech = false;
        let loudSince: number | null = null;
        let silenceStartedAt: number | null = null;

        const watch = () => {
          analyser.getByteTimeDomainData(samples);
          let sum = 0;
          for (let i = 0; i < samples.length; i += 1) {
            const v = (samples[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / samples.length);
          const nextLevel = Math.min(1, rms / 0.12);
          setVoiceLevel((prev) => (Math.abs(prev - nextLevel) < 0.05 ? prev : nextLevel));
          const now = performance.now();

          if (rms >= SPEECH_RMS) {
            if (loudSince == null) loudSince = now;
            else if (now - loudSince >= SPEECH_HOLD_MS) {
              heardSpeech = true;
              heardSpeechRef.current = true;
            }
            silenceStartedAt = null;
          } else {
            loudSince = null;
            if (heardSpeech) {
              if (silenceStartedAt == null) silenceStartedAt = now;
              else if (now - silenceStartedAt >= SILENCE_MS) {
                stopListening();
                return;
              }
            } else if (now - listenStartedAt >= NO_SPEECH_MS) {
              stopListening();
              return;
            }
          }
          silenceRafRef.current = requestAnimationFrame(watch);
        };
        silenceRafRef.current = requestAnimationFrame(watch);
      } catch {
        // Can't measure silence — still allow processing if the user stops the mic.
        heardSpeechRef.current = true;
      }
    } catch {
      setError("Microphone permission denied");
      setListening(false);
    }
  };

  const toggleMic = () => {
    if (listening) stopListening();
    else void startListening();
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  const onAttach = async (kind: AttachKind, file: File) => {
    if (kind === "file") {
      void send(`I attached a file named “${file.name}”. Help me with it.`);
      return;
    }
    const userLine =
      kind === "camera"
        ? `Camera photo: ${file.name}`
        : `Screenshot: ${file.name}`;
    setMessages((m) => [...m, { role: "user", content: userLine }]);
    setBusy(true);
    setError(null);
    try {
      const result = await api.importExpensesFromImage(file, file.name || "screenshot.png");
      setMessages((m) => [...m, { role: "assistant", content: result.reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read that image");
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: "I couldn’t read that screenshot. Try a clearer photo of the transaction list.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const heroText = briefing?.headline ?? (loading ? "" : "Where should we begin?");
  const showVoiceStage = listening || transcribing;
  const orbScale = 1 + voiceLevel * 0.35;

  return (
    <section className="chat-shell">
      {hasUserMessages && !showVoiceStage && (
        <div className="chat-toolbar">
          <Link className="chat-new-link" href="/?new=1">
            New chat
          </Link>
        </div>
      )}
      <div className={`chat-stage${hasUserMessages && !showVoiceStage ? " has-thread" : ""}`}>
        {loading && <p className="chat-hero muted">Loading…</p>}

        {showVoiceStage && (
          <div className="chat-voice-stage" aria-live="polite">
            <div className="chat-voice-rings" aria-hidden="true">
              <span className="chat-voice-ring" />
              <span className="chat-voice-ring" />
              <span className="chat-voice-ring" />
              <div className="chat-voice-orb" style={{ transform: `scale(${orbScale})` }}>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M12 14a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v4a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"
                  />
                </svg>
              </div>
            </div>
            <p className="chat-voice-label">
              {transcribing ? "Understanding…" : "Listening…"}
            </p>
          </div>
        )}

        {!loading && !hasUserMessages && !showVoiceStage && (
          <div className="chat-home">
            <h1 className="chat-hero">{heroText}</h1>
            {briefing?.festival && <p className="chat-festival">{briefing.festival}</p>}
            {briefing?.body && <div className="chat-briefing">{briefing.body}</div>}
            {!briefing && (
              <div className="chat-starters chat-starters-center">
                {STARTERS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className="chat-starter"
                    onClick={() => void send(item)}
                    disabled={busy}
                  >
                    {item}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {hasUserMessages && !showVoiceStage && (
          <div className="chat-log">
            {messages.map((msg, idx) => (
              <div key={`${msg.role}-${idx}`} className={`bubble ${msg.role}`}>
                {msg.content}
              </div>
            ))}
            {busy && <div className="bubble assistant is-typing">Working…</div>}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="chat-composer-row">
        <form className="chat-composer-pill" onSubmit={onSubmit}>
          <ChatAttachFab
            disabled={busy || loading || listening || transcribing}
            onPick={onAttach}
          />
          <input
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              listening ? "Listening… pause to send" : transcribing ? "Understanding…" : "Ask anything"
            }
            disabled={busy || loading || listening || transcribing}
            aria-label="Message"
          />
          <button
            type="button"
            className={`chat-mic${listening ? " is-on" : ""}`}
            onClick={toggleMic}
            disabled={busy || loading || transcribing}
            aria-label={listening ? "Cancel recording" : "Speak"}
            title={listening ? "Cancel recording" : "Speak — auto-sends after a 2s pause"}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              {listening ? (
                <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />
              ) : (
                <path
                  fill="currentColor"
                  d="M12 14a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v4a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"
                />
              )}
            </svg>
          </button>
          <button
            className="chat-send"
            type="submit"
            disabled={busy || loading || listening || transcribing || !input.trim()}
            aria-label="Send"
          >
            ↑
          </button>
        </form>
      </div>
      {error && <p className="error chat-error">{error}</p>}
      {(listening || transcribing) && (
        <p className="muted chat-voice-status">
          {listening
            ? "Listening… I’ll send after you pause for 2 seconds"
            : "Turning speech into a command…"}
        </p>
      )}
    </section>
  );
}
