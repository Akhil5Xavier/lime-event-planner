/** Limy's face: a friendly chat-bubble bot. Inherits text colour via currentColor. */
export default function LimyIcon({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" aria-hidden="true">
      <path
        d="M6 7.5A3.5 3.5 0 0 1 9.5 4h13A3.5 3.5 0 0 1 26 7.5v10a3.5 3.5 0 0 1-3.5 3.5H14l-5.2 4.4A.8.8 0 0 1 7.5 24.8V21A3.5 3.5 0 0 1 6 17.5z"
        fill="currentColor"
      />
      <circle cx="12.5" cy="12" r="1.8" fill="#00C300" />
      <circle cx="19.5" cy="12" r="1.8" fill="#00C300" />
      <path d="M12.5 16.2c1.9 1.5 5.1 1.5 7 0" stroke="#00C300" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
