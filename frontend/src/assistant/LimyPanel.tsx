import { useEffect, useRef, type CSSProperties } from "react";
import { Link } from "react-router-dom";

import { useChatStatus } from "../api/hooks";
import ChatComposer from "./ChatComposer";
import ChatThread from "./ChatThread";
import LimyIcon from "./LimyIcon";
import NotConfigured from "./NotConfigured";
import { useChat } from "./useChat";

interface Props {
  style: CSSProperties;
  onClose: () => void;
}

/** The small chat window that opens from the Limy button. Loaded on first open. */
export default function LimyPanel({ style, onClose }: Props) {
  const status = useChatStatus();
  const chat = useChat();
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => inputRef.current?.focus(), []);

  return (
    <div
      role="dialog"
      aria-label="Limy chat"
      style={style}
      className="fixed z-[1100] flex flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl"
    >
      <div className="flex items-center gap-2 bg-brand px-3 py-2 text-white">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
          <LimyIcon className="h-6 w-6 text-white" />
        </span>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="font-semibold">Limy</div>
          <div className="truncate text-[11px] text-white/80">Your event assistant</div>
        </div>
        {chat.turns.length > 0 && (
          <button
            className="rounded px-2 py-1 text-xs hover:bg-white/20 disabled:opacity-50"
            onClick={chat.reset}
            disabled={chat.pending}
            title="Start a new chat"
          >
            New
          </button>
        )}
        <Link to="/assistant" className="rounded px-2 py-1 text-sm hover:bg-white/20" title="Open full page" onClick={onClose}>
          ⤢
        </Link>
        <button className="rounded px-2 py-1 text-sm hover:bg-white/20" onClick={onClose} aria-label="Close chat" title="Close (Esc)">
          ✕
        </button>
      </div>

      {status.data && !status.data.enabled ? (
        <div className="p-4">
          <NotConfigured />
        </div>
      ) : (
        <>
          <ChatThread turns={chat.turns} pending={chat.pending} onSuggestion={chat.ask} compact className="flex-1 p-3" />
          {chat.error && <p className="mx-3 mb-2 rounded-md bg-red-50 px-2 py-1.5 text-xs text-red-700">{chat.error}</p>}
          <div className="border-t border-gray-100 p-2">
            <ChatComposer
              ref={inputRef}
              value={chat.input}
              onChange={chat.setInput}
              onSend={chat.ask}
              disabled={chat.pending}
              placeholder="Ask Limy…"
              compact
            />
            <p className="mt-1 px-1 text-[10px] text-gray-400">AI answers can contain mistakes. Check numbers in the day view.</p>
          </div>
        </>
      )}
    </div>
  );
}
