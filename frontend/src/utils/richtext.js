// Descriptions and comments predate the rich editor and may be plain text.
// Render those as before (newlines kept); anything that already contains tags
// is HTML saved by the editor, which Frappe sanitises on save.
const HAS_TAG = /<\/?[a-z][\s\S]*>/i

export function toHtml(text) {
  if (!text) return ''
  if (HAS_TAG.test(text)) return text
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

// The editor reports an empty document as "<p></p>"; treat that as no content.
export function isEmptyHtml(html) {
  if (!html) return true
  if (/<img\b/i.test(html)) return false
  return html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim() === ''
}
