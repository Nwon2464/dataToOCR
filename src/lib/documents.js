export function getDocumentIdFromChunk(chunk) {
  if (chunk?.document_id) return chunk.document_id;

  const chunkId = String(chunk?.chunk_id || "");
  const match = chunkId.match(/^(.*)_p\d+_\d+$/);
  if (match) return match[1];

  return chunkId || "default_document";
}

export function formatDocumentTitle(documentId) {
  return String(documentId || "Document")
    .replace(/[_-]+/g, " ")
    .trim();
}

export function formatPageNumber(value) {
  return String(value).padStart(3, "0");
}

export function formatPageRange(pageStart, pageEnd) {
  const start = Number(pageStart);
  const end = Number(pageEnd);

  if (Number.isFinite(start) && Number.isFinite(end)) {
    return `p${formatPageNumber(start)} - p${formatPageNumber(end)}`;
  }

  if (Number.isFinite(start)) {
    return `p${formatPageNumber(start)}`;
  }

  return "p???";
}

export function groupChunksByDocument(chunks = []) {
  const documents = new Map();

  for (const chunk of chunks) {
    const documentId = getDocumentIdFromChunk(chunk);

    if (!documents.has(documentId)) {
      documents.set(documentId, {
        document_id: documentId,
        title: formatDocumentTitle(documentId),
        chunks: [],
        page_start: Number.POSITIVE_INFINITY,
        page_end: 0,
      });
    }

    const document = documents.get(documentId);
    const pageStart = Number(chunk?.page_start || 0);
    const pageEnd = Number(chunk?.page_end || 0);

    document.chunks.push(chunk);

    if (Number.isFinite(pageStart) && pageStart > 0) {
      document.page_start = Math.min(document.page_start, pageStart);
    }

    if (Number.isFinite(pageEnd) && pageEnd > 0) {
      document.page_end = Math.max(document.page_end, pageEnd);
    }
  }

  return Array.from(documents.values()).map((document) => {
    const chunks = [...document.chunks].sort((left, right) => {
      return Number(left?.page_start || 0) - Number(right?.page_start || 0);
    });

    return {
      ...document,
      chunks,
      chunk_count: chunks.length,
      page_start: Number.isFinite(document.page_start) ? document.page_start : 0,
    };
  });
}
