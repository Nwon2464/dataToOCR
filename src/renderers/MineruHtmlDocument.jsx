import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const CONTINUOUS_FALLBACK_HEIGHT = 1200;
const LAST_POSITION_KEY_PREFIX = "reader:last-position:";

function formatPageNumber(value) {
  return String(value).padStart(3, "0");
}

function toPageNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function parseDocumentId(chunkId) {
  const match = String(chunkId || "").match(/^(.*)_p\d+_\d+$/);
  return match?.[1] || String(chunkId || "Document");
}

function documentDisplayName(documentId) {
  return String(documentId || "Document").replace(/[_-]+/g, " ").trim();
}

function readLastPosition(documentId, chunks) {
  const fallback = { index: 0, viewMode: "single", restored: false };
  if (!documentId || !chunks.length || typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(`${LAST_POSITION_KEY_PREFIX}${documentId}`);
    if (!raw) return fallback;
    const saved = JSON.parse(raw);
    if (saved?.document_id !== documentId) return fallback;
    const index = chunks.findIndex((chunk) => chunk.chunk_id === saved?.currentChunkId);
    if (index < 0) return fallback;
    const viewMode = saved?.viewMode === "continuous" ? "continuous" : "single";
    return { index, viewMode, restored: true };
  } catch {
    return fallback;
  }
}

function normalizeChunks(manifest) {
  const chunks = Array.isArray(manifest?.chunks) ? manifest.chunks : [];
  return [...chunks].sort((left, right) => {
    const startDifference =
      (toPageNumber(left?.page_start) ?? Number.POSITIVE_INFINITY) -
      (toPageNumber(right?.page_start) ?? Number.POSITIVE_INFINITY);
    if (startDifference) return startDifference;

    const endDifference =
      (toPageNumber(left?.page_end) ?? Number.POSITIVE_INFINITY) -
      (toPageNumber(right?.page_end) ?? Number.POSITIVE_INFINITY);
    if (endDifference) return endDifference;
    return String(left?.chunk_id || "").localeCompare(String(right?.chunk_id || ""));
  });
}

function chunkRangeLabel(chunk) {
  const start = toPageNumber(chunk?.page_start);
  const end = toPageNumber(chunk?.page_end);
  if (start != null && end != null) return `p${formatPageNumber(start)} - p${formatPageNumber(end)}`;
  if (start != null) return `p${formatPageNumber(start)}`;
  return "p???";
}

function chunkDisplayLabel(chunk) {
  const title = String(chunk?.title || chunk?.chunk_id || "Chunk").trim();
  return `${title} · ${chunkRangeLabel(chunk)}`;
}

function findChunkForPage(chunks, page) {
  return chunks.findIndex((chunk) => {
    const start = toPageNumber(chunk?.page_start);
    const end = toPageNumber(chunk?.page_end);
    return start != null && end != null && page >= start && page <= end;
  });
}

function initialLoadedIndexes(index, length) {
  const indexes = [];
  for (let value = index - 1; value <= index + 2; value += 1) {
    if (value >= 0 && value < length) indexes.push(value);
  }
  return indexes;
}

function NavigationDrawer({ documentName, chunks, currentIndex, open, onClose, onSelectChunk }) {
  const navRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    requestAnimationFrame(() => {
      navRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "center" });
    });
  }, [currentIndex, open]);

  return (
    <>
      <button
        type="button"
        aria-label="Close navigation"
        tabIndex={open ? 0 : -1}
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-slate-950/25 transition-opacity duration-300 ${
          open ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Page navigation"
        aria-hidden={!open}
        inert={open ? undefined : ""}
        className={`fixed inset-y-0 left-0 z-50 flex w-[min(320px,86vw)] flex-col overflow-hidden border-r border-slate-200 bg-white shadow-xl transition-transform duration-300 ease-out ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="flex min-h-14 shrink-0 items-center justify-between border-b border-slate-200 px-4">
          <div className="truncate pr-3 text-sm font-semibold text-slate-900">{documentName}</div>
          <button
            type="button"
            aria-label="Close navigation"
            onClick={onClose}
            className="flex min-h-11 min-w-11 items-center justify-center rounded-full text-xl text-slate-600 active:bg-slate-100"
          >
            ×
          </button>
        </div>
        <nav ref={navRef} className="grid min-h-0 flex-1 content-start gap-1 overflow-y-auto overscroll-contain p-3">
          {chunks.map((chunk, index) => {
            const active = index === currentIndex;
            return (
              <button
                key={chunk.chunk_id || index}
                type="button"
                data-active={active}
                onClick={() => onSelectChunk(index)}
                className={`min-h-12 w-full border-l-2 px-4 py-3 text-left text-[15px] transition-colors active:bg-slate-100 ${
                  active
                    ? "border-slate-900 bg-slate-100 font-semibold text-slate-950"
                    : "border-transparent text-slate-700"
                }`}
              >
                {chunkRangeLabel(chunk)}
              </button>
            );
          })}
        </nav>
      </aside>
    </>
  );
}

function DrawerOpenButton({ onClick }) {
  return (
    <button
      type="button"
      aria-label="Open page navigation"
      onClick={onClick}
      className="fixed top-1/2 z-30 flex h-12 min-w-11 -translate-y-1/2 items-center justify-center rounded-r-xl border border-l-0 border-slate-300 bg-white/90 text-xl font-medium text-slate-700 shadow-sm backdrop-blur active:bg-slate-100"
      style={{ left: "env(safe-area-inset-left)" }}
    >
      &gt;
    </button>
  );
}

function RenderToolbar({
  documentId,
  currentChunk,
  currentIndex,
  chunks,
  viewerMode,
  pageJump,
  jumpError,
  onModeChange,
  onPageJumpChange,
  onGoToPage,
  onPrevious,
  onNext,
  totalPages,
  progressPercent,
  focusMode,
  onFocusToggle,
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-slate-50/95 backdrop-blur">
      <div className="flex min-h-12 flex-wrap items-center gap-1.5 px-3 py-1.5 sm:gap-2 lg:px-4">
        <div className="w-[calc(100%-72px)] min-w-0 flex-none py-0.5 sm:w-auto sm:flex-1">
          <div className="truncate text-sm font-semibold text-slate-900">{documentId}</div>
          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            <span>{chunkRangeLabel(currentChunk)} / p{formatPageNumber(totalPages)}</span>
            <span className="font-medium text-slate-700">{progressPercent}%</span>
          </div>
        </div>

        <button
          type="button"
          onClick={onFocusToggle}
          aria-pressed={focusMode}
          className={`min-h-10 rounded-md border px-2.5 text-xs ${
            focusMode
              ? "border-slate-900 bg-slate-900 text-white"
              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
          }`}
        >
          {focusMode ? "Exit Focus" : "Focus"}
        </button>

        <div className="flex w-full items-center gap-1 overflow-x-auto sm:w-auto sm:overflow-visible">
          <div className="flex min-h-10 shrink-0 rounded-md border border-slate-300 bg-white p-0.5 text-xs">
            {[
              ["single", "Single"],
              ["continuous", "Continuous"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => onModeChange(value)}
                className={`rounded px-2.5 ${
                  viewerMode === value ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={onPrevious}
              disabled={currentIndex <= 0}
              className="min-h-10 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="sm:hidden">Prev</span><span className="hidden sm:inline">Previous</span>
            </button>
            <button
              type="button"
              onClick={onNext}
              disabled={currentIndex >= chunks.length - 1}
              className="min-h-10 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <input
              value={pageJump}
              onChange={(event) => onPageJumpChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") onGoToPage();
              }}
              inputMode="numeric"
              placeholder="page"
              aria-label="Page number"
              className="min-h-10 w-14 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-900 outline-none focus:border-slate-500 sm:w-20"
            />
            <button
              type="button"
              onClick={onGoToPage}
              className="min-h-10 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-700"
            >
              Go
            </button>
          </div>
        </div>
      </div>
      {jumpError ? <div className="px-4 pb-2 text-xs text-red-700">{jumpError}</div> : null}
      <div
        role="progressbar"
        aria-label="Reading progress"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={progressPercent}
        className="h-0.5 bg-slate-200"
      >
        <div
          className="h-full bg-slate-700 transition-[width] duration-300"
          style={{ width: `${progressPercent}%` }}
        />
      </div>
    </header>
  );
}

function RenderSingleChunk({ chunk, loadState, errorMessage, onLoad, onError }) {
  return (
    <section className="relative min-h-[calc(100dvh-100px)] bg-white sm:min-h-[calc(100dvh-49px)]">
      {errorMessage ? (
        <div className="p-6 text-sm text-red-700">{errorMessage}</div>
      ) : (
        <div className="relative min-h-[calc(100dvh-100px)] bg-white sm:min-h-[calc(100dvh-49px)]">
          {loadState !== "ready" ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/90 text-sm text-slate-500">
              Loading chunk...
            </div>
          ) : null}
          <iframe
            key={chunk.html_path}
            title={chunk.chunk_id || chunkDisplayLabel(chunk)}
            src={chunk.html_path}
            className={`block min-h-[calc(100dvh-100px)] w-full border-0 transition-opacity sm:min-h-[calc(100dvh-49px)] ${
              loadState === "ready" ? "opacity-100" : "opacity-0"
            }`}
            onLoad={onLoad}
            onError={onError}
          />
        </div>
      )}
    </section>
  );
}

function ContinuousIframe({ chunk }) {
  const iframeRef = useRef(null);
  const resizeObserverRef = useRef(null);
  const [height, setHeight] = useState(CONTINUOUS_FALLBACK_HEIGHT);
  const [state, setState] = useState("loading");

  useEffect(() => () => resizeObserverRef.current?.disconnect(), []);

  function resizeIframe() {
    try {
      const iframe = iframeRef.current;
      const iframeDocument = iframe?.contentDocument;
      if (!iframeDocument) throw new Error("Iframe document unavailable");
      const nextHeight = Math.max(
        iframeDocument.body?.scrollHeight || 0,
        iframeDocument.documentElement?.scrollHeight || 0,
        1,
      );
      setHeight(nextHeight);
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = new ResizeObserver(resizeIframe);
      if (iframeDocument.body) resizeObserverRef.current.observe(iframeDocument.body);
      if (iframeDocument.documentElement) resizeObserverRef.current.observe(iframeDocument.documentElement);
      setState("ready");
    } catch {
      setHeight(CONTINUOUS_FALLBACK_HEIGHT);
      setState("ready");
    }
  }

  return (
    <div className="relative bg-white" style={{ minHeight: state === "loading" ? CONTINUOUS_FALLBACK_HEIGHT : height }}>
      {state === "loading" ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">Loading chunk...</div>
      ) : null}
      {state === "error" ? (
        <div className="p-6 text-sm text-red-700">Iframe load failed.</div>
      ) : (
        <iframe
          ref={iframeRef}
          title={chunk.chunk_id || "chunk"}
          src={chunk.html_path}
          style={{ height }}
          className={`block w-full border-0 ${state === "ready" ? "opacity-100" : "opacity-0"}`}
          onLoad={resizeIframe}
          onError={() => setState("error")}
        />
      )}
    </div>
  );
}

function RenderContinuousDocument({ chunks, loadedIndexes, sectionRefs }) {
  return (
    <div className="bg-white">
      {chunks.map((chunk, index) => {
        const loaded = loadedIndexes.has(index);
        return (
          <section
            key={chunk.chunk_id || index}
            ref={(node) => {
              sectionRefs.current[index] = node;
            }}
            data-chunk-index={index}
            className="scroll-mt-12 bg-white"
          >
            <div className="flex h-6 items-center justify-between gap-3 border-y border-slate-200 bg-slate-50/70 px-3 text-[10px] text-slate-400 first:border-t-0">
              <span>{chunkRangeLabel(chunk)}</span>
              <span className="truncate">{chunk.chunk_id || `chunk-${index + 1}`}</span>
            </div>
            {loaded ? (
              <ContinuousIframe chunk={chunk} />
            ) : (
              <div className="flex min-h-[480px] items-center justify-center bg-white px-6 py-20 text-center">
                <div>
                  <div className="text-sm font-medium text-slate-700">{chunkRangeLabel(chunk)}</div>
                  <div className="mt-2 text-xs text-slate-400">{chunk.chunk_id || `chunk-${index + 1}`}</div>
                </div>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

export default function MineruHtmlDocument({ manifest, chunkId }) {
  const chunks = useMemo(() => normalizeChunks(manifest), [manifest]);
  const documentId = useMemo(() => parseDocumentId(chunkId || chunks[0]?.chunk_id), [chunkId, chunks]);
  const documentName = useMemo(() => documentDisplayName(documentId), [documentId]);
  const initialPosition = useMemo(() => readLastPosition(documentId, chunks), [chunks, documentId]);
  const initialIndex = initialPosition.index;
  const totalPages = useMemo(() => chunks.reduce((maximum, chunk) => {
    const pageEnd = toPageNumber(chunk?.page_end);
    return pageEnd == null ? maximum : Math.max(maximum, pageEnd);
  }, 0), [chunks]);
  const [viewerMode, setViewerMode] = useState(initialPosition.viewMode);
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [pageJump, setPageJump] = useState("");
  const [jumpError, setJumpError] = useState("");
  const [loadState, setLoadState] = useState("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [focusMode, setFocusMode] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loadedIndexes, setLoadedIndexes] = useState(
    () => new Set(initialLoadedIndexes(initialIndex, chunks.length)),
  );
  const [prefetchedIndexes, setPrefetchedIndexes] = useState(() => new Set());
  const sectionRefs = useRef([]);
  const visibilityRef = useRef(new Map());
  const currentIndexRef = useRef(initialIndex);
  const navigationTargetRef = useRef(null);
  const navigationTimeoutRef = useRef(null);
  const restoredScrollRef = useRef(false);

  const currentChunk = chunks[currentIndex] || chunks[0] || null;
  const nextChunk = chunks[currentIndex + 1] || null;
  const currentPageEnd = toPageNumber(currentChunk?.page_end) || 0;
  const progressPercent = totalPages > 0
    ? Math.min(100, Math.max(0, Math.round((currentPageEnd / totalPages) * 100)))
    : 0;

  const setTrackedCurrentIndex = useCallback((index) => {
    currentIndexRef.current = index;
    setCurrentIndex(index);
  }, []);

  const scrollToChunkSection = useCallback((index, behavior = "smooth") => {
    let attempt = 0;
    const tryScroll = () => {
      const section = sectionRefs.current[index];
      if (section) {
        section.scrollIntoView({ behavior, block: "start" });
        return;
      }
      attempt += 1;
      if (attempt < 5) requestAnimationFrame(tryScroll);
    };
    requestAnimationFrame(tryScroll);
  }, []);

  const navigateToChunk = useCallback((targetIndex, options = {}) => {
    const index = Number(targetIndex);
    if (!Number.isInteger(index) || index < 0 || index >= chunks.length) return false;

    const targetMode = options.mode || viewerMode;
    currentIndexRef.current = index;
    setCurrentIndex(index);
    setJumpError("");
    setLoadedIndexes((previous) => {
      const next = new Set(previous);
      initialLoadedIndexes(index, chunks.length).forEach((loadedIndex) => next.add(loadedIndex));
      return next;
    });

    if (options.closeDrawer) setDrawerOpen(false);

    if (targetMode === "single") {
      navigationTargetRef.current = null;
      if (navigationTimeoutRef.current) clearTimeout(navigationTimeoutRef.current);
      setLoadState("loading");
      setErrorMessage("");
    } else {
      navigationTargetRef.current = index;
      if (navigationTimeoutRef.current) clearTimeout(navigationTimeoutRef.current);
      navigationTimeoutRef.current = setTimeout(() => {
        navigationTargetRef.current = null;
      }, 1500);
      scrollToChunkSection(index, options.behavior || "smooth");
    }
    return true;
  }, [chunks.length, scrollToChunkSection, viewerMode]);

  const navigateByOffset = useCallback((offset) => {
    navigateToChunk(currentIndexRef.current + offset);
  }, [navigateToChunk]);

  const navigateToPage = useCallback((pageNumber) => {
    const page = Number.parseInt(pageNumber, 10);
    if (!Number.isFinite(page)) {
      setJumpError("Enter valid page number.");
      return false;
    }
    const targetIndex = findChunkForPage(chunks, page);
    if (targetIndex === -1) {
      setJumpError(`Page ${page} not found.`);
      return false;
    }
    return navigateToChunk(targetIndex);
  }, [chunks, navigateToChunk]);

  useEffect(() => {
    if (!chunks.length) return;
    const restoredIndex = initialPosition.index;
    currentIndexRef.current = restoredIndex;
    navigationTargetRef.current = null;
    restoredScrollRef.current = false;
    setCurrentIndex(restoredIndex);
    setViewerMode(initialPosition.viewMode);
    setLoadedIndexes(new Set(initialLoadedIndexes(restoredIndex, chunks.length)));
    setPrefetchedIndexes(new Set());
    setPageJump("");
    setJumpError("");
  }, [chunks, initialPosition]);

  useEffect(() => {
    if (!currentChunk?.chunk_id || !documentId) return;
    try {
      window.localStorage.setItem(`${LAST_POSITION_KEY_PREFIX}${documentId}`, JSON.stringify({
        document_id: documentId,
        currentChunkIndex: currentIndex,
        currentChunkId: currentChunk.chunk_id,
        page_start: toPageNumber(currentChunk.page_start),
        page_end: toPageNumber(currentChunk.page_end),
        viewMode: viewerMode,
        updatedAt: new Date().toISOString(),
      }));
    } catch {
      // Storage may be unavailable in iOS private browsing mode.
    }
  }, [currentChunk, currentIndex, documentId, viewerMode]);

  useEffect(() => {
    if (!initialPosition.restored || restoredScrollRef.current || viewerMode !== "continuous") return;
    restoredScrollRef.current = true;
    navigationTargetRef.current = currentIndexRef.current;
    scrollToChunkSection(currentIndexRef.current, "auto");
  }, [initialPosition.restored, scrollToChunkSection, viewerMode]);

  useEffect(() => {
    setLoadedIndexes((previous) => {
      const next = new Set(previous);
      initialLoadedIndexes(currentIndex, chunks.length).forEach((index) => next.add(index));
      return next;
    });
  }, [chunks.length, currentIndex]);

  useEffect(() => {
    if (viewerMode !== "continuous") return undefined;
    const loadObserver = new IntersectionObserver(
      (entries) => {
        const indexes = entries
          .filter((entry) => entry.isIntersecting)
          .map((entry) => Number(entry.target.dataset.chunkIndex));
        if (!indexes.length) return;
        setLoadedIndexes((previous) => new Set([...previous, ...indexes]));
      },
      { rootMargin: "1000px 0px" },
    );

    const visibleObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          visibilityRef.current.set(Number(entry.target.dataset.chunkIndex), entry.intersectionRatio);
        });
        let visibleIndex = currentIndexRef.current;
        let visibleRatio = 0;
        visibilityRef.current.forEach((ratio, index) => {
          if (ratio > visibleRatio) {
            visibleIndex = index;
            visibleRatio = ratio;
          }
        });
        const navigationTarget = navigationTargetRef.current;
        if (navigationTarget != null) {
          const targetRatio = visibilityRef.current.get(navigationTarget) || 0;
          if (targetRatio >= 0.1) {
            navigationTargetRef.current = null;
            if (navigationTimeoutRef.current) clearTimeout(navigationTimeoutRef.current);
            setTrackedCurrentIndex(navigationTarget);
          }
          return;
        }
        if (visibleRatio > 0) setTrackedCurrentIndex(visibleIndex);
      },
      { threshold: [0, 0.1, 0.25, 0.5, 0.75] },
    );

    sectionRefs.current.forEach((section) => {
      if (section) {
        loadObserver.observe(section);
        visibleObserver.observe(section);
      }
    });
    return () => {
      loadObserver.disconnect();
      visibleObserver.disconnect();
      visibilityRef.current.clear();
    };
  }, [chunks.length, setTrackedCurrentIndex, viewerMode]);

  useEffect(() => {
    if (!nextChunk?.html_path) return undefined;
    const nextIndex = currentIndex + 1;
    if (prefetchedIndexes.has(nextIndex)) return undefined;
    const link = document.createElement("link");
    link.rel = "prefetch";
    link.as = "document";
    link.href = nextChunk.html_path;
    link.onload = () => {
      setPrefetchedIndexes((previous) => new Set(previous).add(nextIndex));
    };
    document.head.appendChild(link);
    return () => {
      link.onload = null;
      link.remove();
    };
  }, [currentIndex, nextChunk?.html_path, prefetchedIndexes]);

  useEffect(() => () => {
    if (navigationTimeoutRef.current) clearTimeout(navigationTimeoutRef.current);
  }, []);

  useEffect(() => {
    if (viewerMode !== "single" || !currentChunk?.html_path) return undefined;
    const controller = new AbortController();
    setLoadState("loading");
    setErrorMessage("");
    fetch(currentChunk.html_path, { cache: "force-cache", signal: controller.signal }).then((response) => {
      if (!response.ok) throw new Error(`Failed to load HTML: ${response.status} ${response.statusText}`);
    }).catch((error) => {
      if (error?.name === "AbortError") return;
      setLoadState("error");
      setErrorMessage(String(error?.message || error));
    });
    return () => controller.abort();
  }, [currentChunk?.html_path, viewerMode]);

  function selectChunk(index) {
    navigateToChunk(index, { closeDrawer: true });
  }

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape" && drawerOpen) {
        event.preventDefault();
        setDrawerOpen(false);
        return;
      }
      const target = event.target;
      const tagName = String(target?.tagName || "").toLowerCase();
      if (["input", "textarea", "select"].includes(tagName) || target?.isContentEditable) return;
      if (event.key === "ArrowLeft" && currentIndexRef.current > 0) {
        event.preventDefault();
        navigateByOffset(-1);
      } else if (event.key === "ArrowRight" && currentIndexRef.current < chunks.length - 1) {
        event.preventDefault();
        navigateByOffset(1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [chunks.length, drawerOpen, navigateByOffset]);

  function goToPage() {
    navigateToPage(pageJump);
  }

  function changeMode(mode) {
    setViewerMode(mode);
    navigateToChunk(currentIndexRef.current, { mode, behavior: "auto" });
  }

  if (!chunks.length) return <main className="min-h-screen bg-slate-100 p-8 text-slate-600">No HTML chunks found.</main>;

  return (
    <div className="min-h-screen bg-white">
      <DrawerOpenButton onClick={() => setDrawerOpen(true)} />
      <NavigationDrawer
        documentName={documentName}
        chunks={chunks}
        currentIndex={currentIndex}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSelectChunk={selectChunk}
      />
      <main className="min-w-0 bg-white">
        <RenderToolbar
          documentId={documentId}
          currentChunk={currentChunk}
          currentIndex={currentIndex}
          chunks={chunks}
          viewerMode={viewerMode}
          pageJump={pageJump}
          jumpError={jumpError}
          onModeChange={changeMode}
          onPageJumpChange={setPageJump}
          onGoToPage={goToPage}
          onPrevious={() => navigateByOffset(-1)}
          onNext={() => navigateByOffset(1)}
          totalPages={totalPages}
          progressPercent={progressPercent}
          focusMode={focusMode}
          onFocusToggle={() => setFocusMode((value) => !value)}
        />
        <div className="reader-surface bg-white">
          {viewerMode === "continuous" ? (
            <RenderContinuousDocument
              chunks={chunks}
              loadedIndexes={loadedIndexes}
              sectionRefs={sectionRefs}
            />
          ) : (
            <RenderSingleChunk
              chunk={currentChunk}
              loadState={loadState}
              errorMessage={errorMessage}
              onLoad={() => setLoadState("ready")}
              onError={() => {
                setLoadState("error");
                setErrorMessage("Iframe load failed.");
              }}
            />
          )}
        </div>
      </main>
    </div>
  );
}
