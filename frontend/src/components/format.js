export function formatDate(value, withTime = false) {
  if (!value) return "—";
  const d = new Date(value);
  return withTime ? d.toLocaleString() : d.toLocaleDateString();
}
