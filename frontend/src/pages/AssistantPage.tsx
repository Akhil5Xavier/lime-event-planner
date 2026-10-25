import { useChatStatus } from "../api/hooks";
import ChatComposer from "../assistant/ChatComposer";
import ChatThread from "../assistant/ChatThread";
import NotConfigured from "../assistant/NotConfigured";
import { useChat } from "../assistant/useChat";

export default function AssistantPage() {
  const status = useChatStatus();
  const chat = useChat();

  if (status.data && !status.data.enabled) {
    return (
      <div className="card mx-auto max-w-xl space-y-2 p-6">
        <h1 className="text-lg font-semibold">Limy isn't set up yet</h1>
        <NotConfigured />
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-3xl flex-col">
      <div className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Limy, your event assistant</h1>
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
        {chat.turns.length > 0 && (
          <button className="btn-secondary" onClick={chat.reset} disabled={chat.pending}>
            New chat
          </button>
        )}
      </div>

      <ChatThread turns={chat.turns} pending={chat.pending} onSuggestion={chat.ask} className="card flex-1 p-4" />

      {chat.error && <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{chat.error}</p>}

      <div className="mt-3">
        <ChatComposer
          value={chat.input}
          onChange={chat.setInput}
          onSend={chat.ask}
          disabled={chat.pending}
          placeholder="e.g. Which events are coming up next week?  (Enter to send, Shift+Enter for a new line)"
        />
      </div>
      <p className="mt-1 text-[11px] text-gray-400">
        Answers come from the app's event data via an AI model and can contain mistakes. Check important numbers in the
        day view.
      </p>
    </div>
  );
}
