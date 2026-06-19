const IMAGE_PATTERN = /!\[([^\]]*)\]\(([^)]+)\)/g;

export function unescapeMarkdown(value) {
  return value.replace(/\\([\\`*_{}\[\]()#+\-.!])/g, "$1");
}

export function rewriteImagePath(src, chunkId) {
  const value = src.trim();
  if (/^(https?:|data:|\/)/.test(value)) {
    return value;
  }
  const normalized = value.replaceAll("\\", "/").replace(/^\.\//, "");
  return `/api/chunks/${chunkId}/asset/${normalized}`;
}

export function parseMarkdown(markdown, chunkId) {
  const lines = markdown.split(/\r?\n/);
  const blocks = [];
  let paragraph = [];
  let i = 0;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push({
      type: "paragraph",
      lines: paragraph,
    });
    paragraph = [];
  };

  while (i < lines.length) {
    const line = lines[i];
    const stripped = line.trim();

    if (stripped.startsWith("```")) {
      flushParagraph();
      const language = stripped.slice(3).trim();
      const code = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        code.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push({ type: "code", language, code: code.join("\n") });
      continue;
    }

    if (stripped.startsWith("<table")) {
      flushParagraph();
      const tableLines = [line];
      i += 1;
      if (!line.includes("</table>")) {
        while (i < lines.length) {
          tableLines.push(lines[i]);
          if (lines[i].includes("</table>")) {
            i += 1;
            break;
          }
          i += 1;
        }
      }
      blocks.push({ type: "html-table", html: tableLines.join("\n") });
      continue;
    }

    if (stripped.startsWith("<details")) {
      flushParagraph();
      const detailLines = [line];
      i += 1;
      while (i < lines.length) {
        detailLines.push(lines[i]);
        if (lines[i].trim() === "</details>") {
          i += 1;
          break;
        }
        i += 1;
      }
      blocks.push({ type: "raw-html", html: detailLines.join("\n") });
      continue;
    }

    if (!stripped) {
      flushParagraph();
      i += 1;
      continue;
    }

    const heading = stripped.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: heading[2].trim(),
      });
      i += 1;
      continue;
    }

    if (["---", "***", "___"].includes(stripped)) {
      flushParagraph();
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    if (isTableRow(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      flushParagraph();
      const tableLines = [line, lines[i + 1]];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) {
        tableLines.push(lines[i]);
        i += 1;
      }
      blocks.push({ type: "markdown-table", rows: parseMarkdownTable(tableLines) });
      continue;
    }

    if (isUnorderedList(line) || isOrderedList(line)) {
      flushParagraph();
      const ordered = isOrderedList(line);
      const items = [];
      while (i < lines.length) {
        if (ordered && !isOrderedList(lines[i])) break;
        if (!ordered && !isUnorderedList(lines[i])) break;
        items.push(listItemText(lines[i]));
        i += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    paragraph.push(line);
    i += 1;
  }

  flushParagraph();
  return blocks.map((block, index) => ({ ...block, id: `${chunkId}-${index}` }));
}

export function parseInlineParts(value, chunkId) {
  const parts = [];
  let cursor = 0;
  for (const match of value.matchAll(IMAGE_PATTERN)) {
    if (match.index > cursor) {
      parts.push({ type: "text", text: unescapeMarkdown(value.slice(cursor, match.index)) });
    }
    parts.push({
      type: "image",
      alt: match[1] || "",
      src: rewriteImagePath(match[2] || "", chunkId),
    });
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) {
    parts.push({ type: "text", text: unescapeMarkdown(value.slice(cursor)) });
  }
  return parts.length ? parts : [{ type: "text", text: "" }];
}

export function isImageOnlyParagraph(block) {
  if (block.type !== "paragraph" || block.lines.length !== 1) return false;
  const line = typeof block.lines[0] === "string" ? block.lines[0] : block.lines[0]?.text || "";
  return /^!\[[^\]]*\]\([^)]+\)$/.test(line.trim());
}

function isUnorderedList(line) {
  return /^\s*[-*+]\s+/.test(line);
}

function isOrderedList(line) {
  return /^\s*\d+[.)]\s+/.test(line);
}

function listItemText(line) {
  return line.replace(/^\s*(?:[-*+]|\d+[.)])\s+/, "");
}

function isTableSeparator(line) {
  const stripped = line.trim();
  if (!stripped.includes("|")) return false;
  return stripped.replace(/^\|/, "").replace(/\|$/, "").split("|").every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function isTableRow(line) {
  const stripped = line.trim();
  return stripped.startsWith("|") && stripped.endsWith("|") && stripped.slice(1, -1).includes("|");
}

function splitTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function parseMarkdownTable(lines) {
  return lines.filter((line) => !isTableSeparator(line)).map(splitTableRow);
}
