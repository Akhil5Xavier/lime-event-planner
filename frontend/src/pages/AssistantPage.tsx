import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Link } from "react-router-dom";

import { useChatStatus, useSendChat } from "../api/hooks";
import type { ChatMessage } from "../api/types";

interface Turn extends ChatMessage {
  toolsUsed?: string[];
}

const STORAGE_KEY = "lime-assistant-chat";
const SUGGESTIONS = [
  "Which events are coming up next week?",
  "What's the busiest day this month?",
  "Where should we put extra scooters this Saturday?",
  "What's on at MHPArena in the next 30 days?",
];
const TOOL_LABEL: Record<string, string> = {
  search_events: "events",
  get_day_plan: "day plan",
  get_busiest_days: "busiest days",
  list_venues: "venues",
};

// The thread survives switching to a day view and back, but not closing the tab.
function loadTurns(): Turn[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Turn[]) : [];
  } catch {
    return [];
  }
}

function saveTurns(turns: Turn[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(turns));
  } catch {
    // storage unavailable: the chat just won't survive navigation
  }
}

// Links to the app (e.g. /day/2026-11-07) navigate in-app; anything else opens in a new tab.
const markdownComponents: Components = {
  a: ({ href, children }) =>
    href?.startsWith("/") ? (
      <Link to={href} className="font-medium text-brand-dark underline">
        {children}
      </Link>
    ) : (
      <a href={href} target="_blank" rel="noreferrer" className="text-blue-600 underline">
        {children}
      </a>
    ),
  ul: ({ children }) => <ul className="my-1 list-disc space-y-0.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 list-decimal space-y-0.5 pl-5">{children}</ol>,
  p: ({ children }) => <p className="my-1">{children}</p>,
};

export default function AssistantPage() {
  const status = useChatStatus();
  const send = useSendChat();
  const [turns, setTurns] = useState<Turn[]>(loadTurns);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    saveTurns(turns);
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, send.isPending]);

  function ask(text: string) {
    const question = text.trim();
    if (!question || send.isPending) return;
    const history: Turn[] = [...turns, { role: "user", content: question }];
    setTurns(history);
    setInput("");
    setError(null);
    send.mutate(
      history.map(({ role, content }) => ({ role, content })),
      {
        onSuccess: (res) => setTurns([...history, { role: "assistant", content: res.reply, toolsUsed: res.tools_used }]),
        onError: (err) => {
          // Take the unanswered question back out (the API needs alternating turns) and let the user retry.
          setTurns(turns);
          setInput(question);
          setError(err.message);
        },
      },
    );
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    ask(input);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(input);
    }
  }

  if (status.data && !status.data.enabled) {
    return (
      <div className="card mx-auto max-w-xl space-y-2 p-6">
        <h1 className="text-lg font-semibold">Assistant not set up yet</h1>
        <p className="text-sm text-gray-600">
          An admin needs to add a free AI key: set <code className="rounded bg-gray-100 px-1">LLM_API_KEY</code> in the
          backend's <code className="rounded bg-gray-100 px-1">.env</code> (for example a free Groq key from
          console.groq.com) and restart the backend. See the README section "AI assistant".
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-3xl flex-col">
      <div className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Assistant</h1>
          <p className="text-sm text-gray-500">
            Ask about upcoming events and scooter planning.
            {status.data && (
              <span className="text-gray-400">
                {" "}
                · {status.data.provider}, {status.data.model}
              </span>
            )}
          </p>
        </div>
        {turns.length > 0 && (
          <button
            className="btn-secondary"
            onClick={() => {
              setTurns([]);
              setError(null);
            }}
            disabled={send.isPending}
          >
            New chat
          </button>
        )}
      </div>

      <div className="card flex-1 space-y-3 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <p className="text-sm text-gray-500">Try one of these, or ask your own question:</p>
            <div className="flex max-w-lg flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn-secondary" onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-brand px-3 py-2 text-sm text-white">
                {t.content}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[90%] rounded-2xl rounded-bl-sm bg-gray-100 px-3 py-2 text-sm text-gray-900">
                <ReactMarkdown components={markdownComponents}>{t.content}</ReactMarkdown>
                {t.toolsUsed && t.toolsUsed.length > 0 && (
                  <div className="mt-1 text-[11px] text-gray-400">
                    Looked up: {t.toolsUsed.map((n) => TOOL_LABEL[n] ?? n).join(", ")}
                  </div>
                )}
              </div>
            </div>
          ),
        )}

        {send.isPending && (
          <div className="flex justify-start">
            <div className="animate-pulse rounded-2xl rounded-bl-sm bg-gray-100 px-3 py-2 text-sm text-gray-500">
              Looking that up…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <form onSubmit={onSubmit} className="mt-3 flex items-end gap-2">
        <textarea
          className="input min-h-[2.75rem] flex-1 resize-none"
          rows={2}
          maxLength={4000}
          placeholder="e.g. Which events are coming up next week?  (Enter to send, Shift+Enter for a new line)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={send.isPending}
        />
        <button type="submit" className="btn-primary h-11" disabled={send.isPending || !input.trim()}>
          Send
        </button>
      </form>
      <p className="mt-1 text-[11px] text-gray-400">
        Answers come from the app's event data via an AI model and can contain mistakes. Check important numbers in the
        day view.
      </p>
    </div>
  );
}
