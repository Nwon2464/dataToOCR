export function cx(...values) {
  const seen = new Set();
  const classes = [];
  values
    .flatMap((value) => String(value || "").split(/\s+/))
    .filter(Boolean)
    .forEach((className) => {
      if (!seen.has(className)) {
        seen.add(className);
        classes.push(className);
      }
    });
  return classes.join(" ");
}

export function textOf(block) {
  return String(block?.text || "").replace(/\s+/g, " ").trim();
}

export function normalizeHtml(html, chunkId) {
  if (!html) return "";
  return String(html).replace(/src=(["'])images\//g, `src=$1/processed/${chunkId}/images/`);
}

export function stripHtml(html) {
  return String(html || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;/g, "'")
    .trim();
}

export function themeStyle(block) {
  const fill = Array.isArray(block.theme?.fill) ? block.theme.fill.join(", ") : "13, 83, 222";
  const stroke = Array.isArray(block.theme?.stroke) ? block.theme.stroke.join(", ") : fill;
  return {
    "--data-fill": fill,
    "--data-stroke": stroke,
  };
}

export function blockTypeClass(block) {
  if (block.block_type === "title") return "border-l-4 pl-4";
  if (block.block_type === "header" || block.block_type === "footer" || block.block_type === "page_number") {
    return "text-sm text-slate-500";
  }
  return "";
}
