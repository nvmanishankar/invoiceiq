import { useEffect, useState } from "react"

import { runStreamUrl } from "@/api"
import type { DecisionInfo, Stage } from "@/types"

type StreamState = {
  runId: string | null
  stages: Stage[]
  decision: DecisionInfo | null
  done: boolean
  lost: boolean // the stream closed before "done"
}

const empty = (runId: string | null): StreamState => ({ runId, stages: [], decision: null, done: false, lost: false })

/** Follows GET /api/runs/{id}/stream: stage → decision → done. Replays from the start, so reconnects are deduped. */
export function useRunStream(runId: string | null): StreamState {
  const [state, setState] = useState<StreamState>(() => empty(runId))
  if (state.runId !== runId) setState(empty(runId))

  useEffect(() => {
    if (!runId) return
    const es = new EventSource(runStreamUrl(runId))
    es.addEventListener("stage", (e) => {
      const stage = JSON.parse((e as MessageEvent).data) as Stage
      setState((s) =>
        s.runId !== runId || s.stages.some((x) => x.order === stage.order)
          ? s
          : { ...s, stages: [...s.stages, stage].sort((a, b) => a.order - b.order) },
      )
    })
    es.addEventListener("decision", (e) => {
      const decision = JSON.parse((e as MessageEvent).data) as DecisionInfo
      setState((s) => (s.runId === runId ? { ...s, decision } : s))
    })
    es.addEventListener("done", () => {
      es.close()
      setState((s) => (s.runId === runId ? { ...s, done: true } : s))
    })
    es.onerror = () => {
      // EventSource retries on its own; only give up once the browser has closed it (e.g. 404).
      if (es.readyState === EventSource.CLOSED) setState((s) => (s.runId === runId ? { ...s, lost: true } : s))
    }
    return () => es.close()
  }, [runId])

  return state
}
