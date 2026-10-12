<template>
  <div class="rt" :class="{ 'rt-compact': compact }" @focusout="onFocusOut">
    <TextEditor
      :content="initial"
      :editable="editable"
      :placeholder="placeholder"
      :upload-args="uploadArgs"
      :upload-function="uploadFunction || undefined"
      editor-class="prose-sm max-w-none"
      @change="onChange"
    />
  </div>
</template>

<script setup>
// Rich text box (TipTap via frappe-ui). Pasting or dropping an image uploads it
// to the task as a private file and inlines it. Content is only read when the
// component is created, so give it a :key to reset it (new task, after sending).
import { computed, ref } from 'vue'
import { TextEditor } from 'frappe-ui'
import { toHtml, isEmptyHtml } from '@/utils/richtext'

const props = defineProps({
  modelValue: { type: String, default: '' },
  taskName: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  compact: { type: Boolean, default: false },
  editable: { type: Boolean, default: true },
  // Custom image upload (file => Promise<{file_url, ...}>); default is Frappe's upload_file.
  uploadFunction: { type: Function, default: null },
})
const emit = defineEmits(['update:modelValue', 'commit'])

const initial = toHtml(props.modelValue)
const dirty = ref(false)

const uploadArgs = computed(() => ({ private: true, doctype: 'Task', docname: props.taskName }))

function onChange(html) {
  dirty.value = true
  emit('update:modelValue', isEmptyHtml(html) ? '' : html)
}

// Fires `commit` once focus leaves the box (not when moving between its own controls).
function onFocusOut(e) {
  if (e.currentTarget.contains(e.relatedTarget)) return
  if (!dirty.value) return
  dirty.value = false
  emit('commit')
}
</script>

<style>
.rt .ProseMirror {
  min-height: 9rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--surface-2);
  color: var(--text);
  outline: none;
}
.rt.rt-compact .ProseMirror { min-height: 4.5rem; }
.rt .ProseMirror:focus { border-color: var(--accent); }
.rt .ProseMirror[contenteditable="false"] { border-color: transparent; background: transparent; padding-left: 0; min-height: 0; }
.rt .ProseMirror p { margin: 0 0 0.4rem; }
.rt .ProseMirror p.is-editor-empty:first-child::before { color: var(--text-faint, #7b8496); }
.rt .ProseMirror img, .rt-content img { max-width: 100%; height: auto; border-radius: 0.375rem; }
.rt .ProseMirror ul, .rt-content ul { list-style: disc; padding-left: 1.25rem; }
.rt .ProseMirror ol, .rt-content ol { list-style: decimal; padding-left: 1.25rem; }
.rt-content p { margin: 0 0 0.4rem; }
.rt-content a { color: var(--accent); text-decoration: underline; }
</style>
