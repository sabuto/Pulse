// Turn a Desk route string as captured by Report Bug (frappe.get_route_str(),
// e.g. "List/Company/List" or "Form/User/a@b.com") into a Desk URL.
// Always returns a same-origin /app/... path, whatever the stored text says.
const slug = (s) => s.toLowerCase().replace(/\s+/g, '-')
const enc = encodeURIComponent

export function deskUrl(route) {
  const parts = String(route || '').split('/').filter(Boolean)
  if (!parts.length) return null
  const [head, doctype, ...rest] = parts

  if (head === 'Form' && doctype) {
    return rest.length ? `/app/${slug(doctype)}/${enc(rest.join('/'))}` : `/app/${slug(doctype)}`
  }
  if (head === 'List' && doctype) {
    const [view = 'List', ...more] = rest
    return `/app/${slug(doctype)}/view/${[view.toLowerCase(), ...more.map(enc)].join('/')}`
  }
  if (head === 'Tree' && doctype) return `/app/${slug(doctype)}/view/tree`
  if (head === 'Workspaces' && doctype) return `/app/${slug(doctype)}`
  return `/app/${parts.map(enc).join('/')}`
}
