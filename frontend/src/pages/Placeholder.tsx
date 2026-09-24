import { SectionTitle } from "@/components/ds/SectionTitle"
import { SplitContainer } from "@/components/ds/SplitContainer"

export function Placeholder({ title }: { title: string }) {
  return (
    <SplitContainer rail={<h1 className="text-h1">{title}</h1>}>
      <SectionTitle>Coming in a later phase</SectionTitle>
      <p className="mt-4 max-w-prose text-ink-2">This page is part of the build plan and isn't wired up yet.</p>
    </SplitContainer>
  )
}
