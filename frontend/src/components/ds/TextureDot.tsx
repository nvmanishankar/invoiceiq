import type { CSSProperties } from "react"

import { cn } from "@/lib/utils"

const TEXTURES = ["--tx-violet", "--tx-teal", "--tx-pink", "--tx-lime", "--tx-sky", "--tx-amber"] as const

export function TextureDot({ index = 0, size = 14, className }: { index?: number; size?: number; className?: string }) {
  const style = { "--dot": `var(${TEXTURES[index % TEXTURES.length]})`, width: size, height: size } as CSSProperties
  return <span aria-hidden className={cn("texture inline-block shrink-0 rounded-full", className)} style={style} />
}
