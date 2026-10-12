<template>
  <transition name="fade">
    <div v-if="resolutionState.open" class="ovl" @click.self="cancel" @keydown.esc="cancel">
      <div class="modal" role="dialog" aria-modal="true" aria-label="Mark as done">
        <div class="head">
          <span class="font-semibold">Mark as done</span>
          <button class="p-1 rounded hover-app text-muted" @click="cancel"><X class="w-4 h-4" /></button>
        </div>
        <div class="body">
          <div class="text-sm text-muted">
            <b class="text-app">{{ resolutionState.task?.issue_key }}</b>
            {{ resolutionState.task?.subject }}
          </div>
          <label class="fld">
            <span class="lbl">What was done? (optional)</span>
            <textarea ref="box" v-model="note" rows="4" class="in"
              placeholder="A line or two for the summary email sent to everyone following this task"
              @keydown.ctrl.enter="done" @keydown.meta.enter="done" />
          </label>
        </div>
        <div class="foot">
          <button class="btn ghost" @click="cancel">Cancel</button>
          <div class="flex gap-2">
            <button class="btn ghost" @click="skip">Skip note</button>
            <button class="btn primary" @click="done">Mark as done</button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import X from '~icons/lucide/x'
import { resolutionState, answerResolution } from '@/ui/resolution'

const note = ref('')
const box = ref(null)

watch(() => resolutionState.open, (open) => {
  if (open) { note.value = ''; nextTick(() => box.value?.focus()) }
})

const cancel = () => answerResolution(null)
const skip = () => answerResolution('')
const done = () => answerResolution(note.value.trim())
</script>

<style scoped>
.ovl { position: fixed; inset: 0; z-index: 95; background: rgba(0, 0, 0, 0.5); display: grid; place-items: start center; padding-top: 14vh; }
.modal { width: 480px; max-width: calc(100vw - 32px); background: var(--surface); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow); }
.head { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--border-soft); }
.body { padding: 16px; display: flex; flex-direction: column; gap: 13px; }
.fld { display: flex; flex-direction: column; gap: 5px; }
.lbl { font-size: 11px; color: var(--muted); font-weight: 500; }
.in { width: 100%; background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font-size: 13px; border-radius: 7px; padding: 7px 9px; outline: none; resize: vertical; font-family: inherit; }
.in:focus { border-color: var(--accent); }
.foot { display: flex; align-items: center; justify-content: space-between; padding: 13px 16px; border-top: 1px solid var(--border-soft); }
.btn { font-size: 13px; padding: 7px 14px; border-radius: 7px; }
.btn.ghost { border: 1px solid var(--border); background: transparent; color: var(--text); }
.btn.primary { background: var(--accent); color: var(--on-accent); }
</style>
