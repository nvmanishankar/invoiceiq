import { useTypewriter } from "@/hooks/useTypewriter"
import { cn } from "@/lib/utils"

/** The agent's voice: mono, typed in one character at a time. */
export function SpeechBubble({ text, className }: { text: string; className?: string }) {
  const { shown, done } = useTypewriter(text)
  return (
    <div className={cn("relative rounded-card bg-bubble px-5 py-4 font-mono text-[15px] leading-[1.6] text-ink", className)}>
      {/* full text reserves the height and is what screen readers get */}
      <p className="invisible" aria-hidden>{text}</p>
      <p className="absolute inset-0 px-5 py-4" aria-hidden>
        {shown}
        {!done && <span className="ml-0.5 inline-block h-[1.05em] w-[0.55em] translate-y-[0.15em] bg-ink/70" />}
      </p>
      <p className="sr-only" aria-live="polite">{text}</p>
    </div>
  )
}
