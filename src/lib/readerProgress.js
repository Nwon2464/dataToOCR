const LAST_POSITION_KEY_PREFIX = "reader:last-position:";

export function getReaderProgressKey(documentId) {
  return `${LAST_POSITION_KEY_PREFIX}${documentId}`;
}

export function loadReaderProgress(documentId) {
  if (!documentId || typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(getReaderProgressKey(documentId));
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (error) {
    console.warn("[readerProgress] failed to load progress", error);
    return null;
  }
}

export function saveReaderProgress(documentId, progress) {
  if (!documentId || typeof window === "undefined") return;

  try {
    window.localStorage.setItem(
      getReaderProgressKey(documentId),
      JSON.stringify({
        ...progress,
        document_id: documentId,
        updatedAt: new Date().toISOString(),
      }),
    );
  } catch (error) {
    console.warn("[readerProgress] failed to save progress", error);
  }
}

export function calculateProgressPercent(progress, totalPages) {
  const pageEnd = Number(progress?.page_end || progress?.current_page_end || 0);
  const total = Number(totalPages || 0);

  if (!pageEnd || !total) return 0;

  return Math.max(0, Math.min(100, Math.round((pageEnd / total) * 100)));
}
