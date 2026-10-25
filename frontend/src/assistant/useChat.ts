import { useEffect, useState } from "react";

import { useSendChat } from "../api/hooks";
import type { ChatMessage } from "../api/types";

export interface Turn extends ChatMessage {
  toolsUsed?: string[];
}

// Shared by the Assistant page and the Limy pop-up, so a conversation started in one
// continues in the other. Survives navigation, but not closing the tab.
const STORAGE_KEY = "lime-assistant-chat";

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

export function useChat() {
  const send = useSendChat();
  const [turns, setTurns] = useState<Turn[]>(loadTurns);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => saveTurns(turns), [turns]);

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
          setTurns(history.slice(0, -1));
          setInput(question);
          setError(err.message);
        },
      },
    );
  }

  function reset() {
    setTurns([]);
    setError(null);
  }

  return { turns, input, setInput, error, ask, reset, pending: send.isPending };
}
