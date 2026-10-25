/** Shown instead of the chat when the backend has no AI provider configured. */
export default function NotConfigured() {
  return (
    <p className="text-sm text-gray-600">
      An admin needs to add a free AI key: set <code className="rounded bg-gray-100 px-1">LLM_API_KEY</code> in the
      backend's <code className="rounded bg-gray-100 px-1">.env</code> (for example a free Groq key from console.groq.com)
      and restart the backend. See the README section "AI assistant".
    </p>
  );
}
