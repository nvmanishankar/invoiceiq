import { useSyncExternalStore } from "react"

/** The "Start here" tour on the Process page. Steps tick from what actually happened (a run's result, a page
 * visited), never from the click alone. Remembered in this browser; a private window just starts fresh. */
export const TOUR_STEPS = ["pay", "fraud", "overbill", "dashboard", "tests"] as const
export type TourStep = (typeof TOUR_STEPS)[number]

/** open: the full card shows. lineHidden: the slim "New here?" line was closed with × (the rail's Tour link stays). */
type TourState = { open: boolean; lineHidden: boolean; done: TourStep[]; overbillRun: string | null }

const KEY = "invoiceiq.tour"
const EMPTY: TourState = { open: false, lineHidden: false, done: [], overbillRun: null }

function load(): TourState {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<TourState> | null
    if (!v || typeof v !== "object") return EMPTY
    return {
      open: v.open === true,
      lineHidden: v.lineHidden === true,
      done: Array.isArray(v.done) ? v.done.filter((s): s is TourStep => TOUR_STEPS.includes(s)) : [],
      overbillRun: typeof v.overbillRun === "string" ? v.overbillRun : null,
    }
  } catch {
    return EMPTY
  }
}

let state = load()
const listeners = new Set<() => void>()

function set(next: Partial<TourState>) {
  state = { ...state, ...next }
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    // private window: progress just isn't remembered
  }
  listeners.forEach((l) => l())
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}

export const tour = {
  complete(step: TourStep) {
    if (state.done.includes(step)) return
    const done = [...state.done, step]
    // The last step folds the card down to the "Tour complete" line.
    set(done.length === TOUR_STEPS.length ? { done, open: false } : { done })
  },
  setOverbillRun(runId: string) {
    if (state.overbillRun !== runId) set({ overbillRun: runId })
  },
  open: () => set({ open: true }),
  collapse: () => set({ open: false }),
  hideLine: () => set({ lineHidden: true }),
  restart: () => set({ done: [], overbillRun: null, open: true }),
}

export const useTour = () => useSyncExternalStore(subscribe, () => state)
