import { reactive } from 'vue'

// "What was done?" prompt shown when a card is moved to Done. Resolves with the note
// ('' when skipped) or null when the move is cancelled.
export const resolutionState = reactive({ open: false, task: null })
let resolver = null

export function askResolution(task) {
  return new Promise((resolve) => {
    resolver = resolve
    resolutionState.task = task
    resolutionState.open = true
  })
}

export function answerResolution(value) {
  resolutionState.open = false
  const done = resolver
  resolver = null
  done?.(value)
}
