<template>
  <transition name="fade">
    <div v-if="entityState.open" class="ovl" @click.self="close">
      <div class="modal" role="dialog" aria-modal="true">
        <div class="head">
          <span class="font-semibold">{{ entityState.name ? 'Edit' : 'New' }} {{ singular }}</span>
          <button class="p-1 rounded hover-app text-muted" @click="close"><X class="w-4 h-4" /></button>
        </div>

        <div v-if="loadingMeta" class="body"><div class="text-sm text-muted py-6 text-center">Loading form…</div></div>

        <div v-else class="body">
          <div v-for="f in fields" :key="f.fieldname" class="fld">
            <span class="lbl">{{ f.label }}<b v-if="f.reqd" style="color:var(--accent)"> *</b></span>

            <textarea v-if="isText(f)" v-model="model[f.fieldname]" rows="3" :disabled="!canWrite" class="in" :placeholder="f.description || ''" />

            <select v-else-if="f.fieldtype === 'Select'" v-model="model[f.fieldname]" :disabled="!canWrite" class="in">
              <option v-for="o in selOpts(f)" :key="o" :value="o">{{ o || '—' }}</option>
            </select>

            <select v-else-if="f.fieldtype === 'Link'" v-model="model[f.fieldname]" :disabled="!canWrite" class="in">
              <option :value="null">— none —</option>
              <option v-for="o in (linkCache[f.options] || [])" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>

            <label v-else-if="f.fieldtype === 'Check'" class="chk">
              <input type="checkbox" :disabled="!canWrite" :checked="!!model[f.fieldname]" @change="model[f.fieldname] = $event.target.checked ? 1 : 0" />
              <span class="text-xs text-muted">{{ f.description || 'Yes' }}</span>
            </label>

            <input v-else-if="f.fieldtype === 'Date'" type="date" v-model="model[f.fieldname]" :disabled="!canWrite" class="in" />
            <input v-else-if="f.fieldtype === 'Datetime'" type="datetime-local" v-model="model[f.fieldname]" :disabled="!canWrite" class="in" />
            <input v-else-if="isNumber(f)" type="number" v-model="model[f.fieldname]" :disabled="!canWrite" class="in" />
            <input v-else v-model="model[f.fieldname]" :disabled="!canWrite" class="in" :placeholder="f.description || ''" />
          </div>
          <div v-if="!fields.length" class="text-sm text-muted py-4 text-center">Nothing to edit.</div>
        </div>

        <div class="foot">
          <button v-if="canWrite && entityState.name" class="btn danger" @click="remove" :disabled="busy">Delete</button>
          <span v-else />
          <div class="flex gap-2">
            <button class="btn ghost" @click="close">{{ canWrite ? 'Cancel' : 'Close' }}</button>
            <button v-if="canWrite" class="btn primary" :disabled="!valid || busy" @click="save">{{ busy ? 'Saving…' : 'Save' }}</button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { canWrite } from '@/utils/access'
import { call } from 'frappe-ui'
import { entityState, closeEntity, markSaved } from '@/ui/entity'
import { toast } from '@/ui/toast'
import X from '~icons/lucide/x'

const loadingMeta = ref(false)
const busy = ref(false)
const fields = ref([])
const model = reactive({})
const metaCache = {}
const linkCache = reactive({})

const singular = computed(() => (entityState.doctype || '').replace(/^Pulse /, ''))
const valid = computed(() => fields.value.every((f) => !f.reqd || (model[f.fieldname] !== undefined && model[f.fieldname] !== null && model[f.fieldname] !== '')))

function isText(f) { return ['Text', 'Long Text', 'Small Text', 'Text Editor', 'Markdown Editor', 'Code', 'HTML Editor'].includes(f.fieldtype) }
function isNumber(f) { return ['Int', 'Float', 'Currency', 'Percent'].includes(f.fieldtype) }
function selOpts(f) { return (f.options || '').split('\n') }

async function loadMeta(dt) {
  if (metaCache[dt]) return metaCache[dt]
  const m = await call('pulse.api.spa.get_form_meta', { doctype: dt })
  metaCache[dt] = m
  return m
}

async function fetchLinks(flds) {
  const targets = [...new Set(flds.filter((f) => f.fieldtype === 'Link' && f.options).map((f) => f.options))]
  await Promise.all(targets.map(async (t) => {
    if (linkCache[t]) return
    linkCache[t] = await call('pulse.api.spa.link_options', { doctype: t }).catch(() => [])
  }))
}

watch(() => entityState.open, async (open) => {
  if (!open) return
  loadingMeta.value = true
  try {
    const meta = await loadMeta(entityState.doctype)
    fields.value = meta.fields
    await fetchLinks(meta.fields)

    // reset model
    Object.keys(model).forEach((k) => delete model[k])
    for (const f of meta.fields) model[f.fieldname] = f.fieldtype === 'Check' ? (parseInt(f.default) || 0) : (f.default ?? '')
    Object.assign(model, entityState.defaults)

    if (entityState.name) {
      const rec = await call('pulse.api.spa.get_entity', { doctype: entityState.doctype, name: entityState.name }).catch(() => null)
      if (rec) for (const f of meta.fields) if (rec[f.fieldname] !== undefined && rec[f.fieldname] !== null) model[f.fieldname] = rec[f.fieldname]
    }
  } catch (e) {
    // never leave the dialog stuck on "Loading form…" — surface and close
    toast.error(e?.messages?.[0] || e?.message || 'Could not load form')
    closeEntity()
  } finally {
    loadingMeta.value = false
  }
})

function close() { closeEntity() }

async function save() {
  if (!valid.value) return
  busy.value = true
  const doc = { doctype: entityState.doctype, ...model }
  if (entityState.name) doc.name = entityState.name
  try {
    await call('pulse.api.spa.save_entity', { doc: JSON.stringify(doc) })
    toast.success(`${singular.value} saved`)
    markSaved()
    closeEntity()
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || 'Could not save')
  } finally { busy.value = false }
}

async function remove() {
  if (!confirm(`Delete this ${singular.value.toLowerCase()}?`)) return
  busy.value = true
  try {
    await call('pulse.api.spa.delete_entity', { doctype: entityState.doctype, name: entityState.name })
    toast.success(`${singular.value} deleted`)
    markSaved()
    closeEntity()
  } catch (e) {
    toast.error(e?.messages?.[0] || 'Could not delete')
  } finally { busy.value = false }
}
</script>

<style scoped>
.ovl { position: fixed; inset: 0; z-index: 90; background: rgba(0, 0, 0, 0.5); display: grid; place-items: start center; padding-top: 8vh; }
.modal { width: 520px; max-width: calc(100vw - 32px); max-height: 84vh; overflow-y: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow); }
.head { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--border-soft); }
.body { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.fld { display: flex; flex-direction: column; gap: 5px; }
.lbl { font-size: 11px; color: var(--muted); font-weight: 500; }
.in { width: 100%; background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font-size: 13px; border-radius: 7px; padding: 7px 9px; outline: none; }
.in:focus { border-color: var(--accent); }
textarea.in { resize: vertical; font-family: inherit; }
.chk { display: flex; align-items: center; gap: 8px; }
.foot { display: flex; align-items: center; justify-content: space-between; padding: 13px 16px; border-top: 1px solid var(--border-soft); position: sticky; bottom: 0; background: var(--surface); }
.btn { font-size: 13px; padding: 7px 14px; border-radius: 7px; }
.btn.ghost { border: 1px solid var(--border); background: transparent; color: var(--text); }
.btn.primary { background: var(--accent); color: var(--on-accent); }
.btn.primary:disabled { opacity: 0.45; }
.btn.danger { border: 1px solid rgba(242,114,109,0.4); color: #f2726d; background: transparent; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.16s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
