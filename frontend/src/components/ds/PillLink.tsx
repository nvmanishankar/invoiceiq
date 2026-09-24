import type { ComponentProps, ReactNode } from "react"
import { HoverCard } from "radix-ui"

import { cn } from "@/lib/utils"
import { TextureDot } from "./TextureDot"

/** White 48px pill with a texture dot. Optional hover/focus popover. */
export function PillLink({
  label,
  dot = 0,
  active = false,
  hint,
  className,
  ...props
}: ComponentProps<"button"> & { label: ReactNode; dot?: number; active?: boolean; hint?: ReactNode }) {
  const pill = (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "flex h-12 w-full items-center gap-3 rounded-full border bg-raised pr-5 pl-4 text-left text-[15px] text-ink transition-[transform,border-color] duration-200 hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0",
        active ? "border-ink" : "border-line hover:border-ink-3",
        className,
      )}
      {...props}
    >
      <TextureDot index={dot} />
      <span className="truncate">{label}</span>
    </button>
  )
  if (!hint) return pill
  return (
    <HoverCard.Root openDelay={250} closeDelay={80}>
      <HoverCard.Trigger asChild>{pill}</HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="right"
          align="start"
          sideOffset={12}
          className="z-50 w-72 rounded-card border border-line bg-raised p-4 text-sm leading-relaxed text-ink-2 shadow-float data-[state=open]:animate-in data-[state=open]:fade-in-0"
        >
          {hint}
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  )
}
