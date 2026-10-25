import { useEffect, useRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Link } from "react-router-dom";

import type { Turn } from "./useChat";

export const SUGGESTIONS = [
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

interface Props {
  turns: Turn[];
  pending: boolean;
  onSuggestion: (text: string) => void;
  /** Smaller text and fewer suggestions, for the Limy pop-up. */
  compact?: boolean;
  className?: string;
}

/** Scrollable message list: suggestions when empty, bubbles, "Looking that up…" while waiting. */
export default function ChatThread({ turns, pending, onSuggestion, compact = false, className = "" }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, pending]);

  const text = compact ? "text-[13px]" : "text-sm";
  const suggestions = compact ? SUGGESTIONS.slice(0, 3) : SUGGESTIONS;

  return (
    <div className={`space-y-3 overflow-y-auto ${className}`}>
      {turns.length === 0 && (
        <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
          <p className={`${text} text-gray-500`}>Try one of these, or ask your own question:</p>
          <div className="flex max-w-lg flex-wrap justify-center gap-2">
            {suggestions.map((s) => (
              <button key={s} className={`btn-secondary ${compact ? "text-xs" : ""}`} onClick={() => onSuggestion(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {turns.map((t, i) =>
        t.role === "user" ? (
          <div key={i} className="flex justify-end">
            <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-brand px-3 py-2 ${text} text-white`}>
              {t.content}
            </div>
          </div>
        ) : (
          <div key={i} className="flex justify-start">
            <div className={`max-w-[90%] rounded-2xl rounded-bl-sm bg-gray-100 px-3 py-2 ${text} text-gray-900`}>
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

      {pending && (
        <div className="flex justify-start">
          <div className={`animate-pulse rounded-2xl rounded-bl-sm bg-gray-100 px-3 py-2 ${text} text-gray-500`}>
            Looking that up…
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
