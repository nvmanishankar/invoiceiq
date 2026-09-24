import type { ComponentProps } from "react"
import { Slot } from "radix-ui"

import { PixelArrow } from "@/components/brand/PixelArrow"
import { cn } from "@/lib/utils"

type Variant = "primary" | "secondary" | "link"

const BASE = "group/pill inline-flex items-center gap-2.5 font-mono text-[13px] font-medium whitespace-nowrap select-none disabled:pointer-events-none disabled:opacity-45"

const VARIANTS: Record<Variant, string> = {
  primary: "h-11 rounded-full bg-ink px-5 text-white transition-colors duration-200 hover:bg-accent",
  secondary: "h-11 rounded-full border border-line bg-raised px-5 text-ink transition-colors duration-200 hover:border-ink",
  link: "relative h-auto px-0 text-ink after:absolute after:-bottom-0.5 after:left-0 after:h-px after:w-full after:origin-left after:scale-x-0 after:bg-current after:transition-transform after:duration-200 hover:after:scale-x-100",
}

/** Pill button in Geist Mono. Primary and link carry the pixel arrow. */
export function PillButton({
  variant = "primary",
  arrow = variant !== "secondary",
  asChild = false,
  className,
  children,
  ...props
}: ComponentProps<"button"> & { variant?: Variant; arrow?: boolean; asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button"
  return (
    <Comp className={cn(BASE, VARIANTS[variant], className)} {...props}>
      <Slot.Slottable>{children}</Slot.Slottable>
      {arrow && <PixelArrow size={9} className="transition-transform duration-200 group-hover/pill:translate-x-[3px]" />}
    </Comp>
  )
}
