const EVENT_HANDLER_ATTR_RE = /\son[a-z]+\s*=\s*(['"]).*?\1/gi;
const JAVASCRIPT_HREF_RE = /\s(href|src)\s*=\s*(['"])\s*javascript:.*?\2/gi;
const DANGEROUS_BLOCK_RE =
  /<\s*(script|iframe|object|embed|style|link|meta)[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi;
const SELF_CLOSING_DANGEROUS_RE = /<\s*(script|iframe|object|embed|style|link|meta)[^>]*\/?\s*>/gi;

export function sanitizeRenderedMarkdown(html = "") {
  return String(html)
    .replace(DANGEROUS_BLOCK_RE, "")
    .replace(SELF_CLOSING_DANGEROUS_RE, "")
    .replace(EVENT_HANDLER_ATTR_RE, "")
    .replace(JAVASCRIPT_HREF_RE, "");
}
