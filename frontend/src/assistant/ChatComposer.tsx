import { forwardRef, type FormEvent, type KeyboardEvent } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder?: string;
  compact?: boolean;
}

/** Question box: Enter sends, Shift+Enter adds a new line. */
const ChatComposer = forwardRef<HTMLTextAreaElement, Props>(function ChatComposer(
  { value, onChange, onSend, disabled, placeholder, compact = false },
  ref,
) {
  function onSubmit(e: FormEvent) {
    e.preventDefault();
    onSend(value);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend(value);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex items-end gap-2">
      <textarea
        ref={ref}
        className={`input flex-1 resize-none ${compact ? "min-h-[2.5rem] text-[13px]" : "min-h-[2.75rem]"}`}
        rows={compact ? 1 : 2}
        maxLength={4000}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
      />
      <button type="submit" className={`btn-primary ${compact ? "h-10" : "h-11"}`} disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  );
});

export default ChatComposer;
