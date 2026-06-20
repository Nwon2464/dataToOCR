import { useEffect, useMemo, useRef, useState } from "react";
import "./MineruHtmlDocument.css";

function toPageNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function normalizeChunks(manifest) {
  const chunks = Array.isArray(manifest?.chunks) ? manifest.chunks : [];
  return [...chunks].sort((left, right) => {
    const startDifference =
      (toPageNumber(left?.page_start) ?? Number.POSITIVE_INFINITY) -
      (toPageNumber(right?.page_start) ?? Number.POSITIVE_INFINITY);
    if (startDifference) return startDifference;
    return String(left?.chunk_id || "").localeCompare(String(right?.chunk_id || ""));
  });
}

function parseDocumentId(chunkId) {
  const match = String(chunkId || "").match(/^(.*)_p\d+_\d+$/);
  return match?.[1] || String(chunkId || "Document");
}

function displayName(value) {
  return String(value || "Document").replace(/[_-]+/g, " ").trim();
}

function isRelativeUrl(value) {
  const url = String(value || "").trim();
  return Boolean(url) && !url.startsWith("#") && !url.startsWith("/") &&
    !/^[a-z][a-z\d+.-]*:/i.test(url) && !url.startsWith("//");
}

function rewriteSrcset(value, assetBase) {
  return String(value || "")
    .split(",")
    .map((candidate) => {
      const parts = candidate.trim().split(/\s+/);
      if (isRelativeUrl(parts[0])) parts[0] = `${assetBase}${parts[0]}`;
      return parts.join(" ");
    })
    .join(", ");
}

function scopeDocumentStyles(cssText) {
  return String(cssText || "")
    .replace(/\bhtml\b(?=\s*[,>{[])/g, ".mineru-html-root")
    .replace(/\bbody\b(?=\s*[,>{[])/g, ".mineru-html-root");
}

function prepareHtml(source, chunkId) {
  const parser = new DOMParser();
  const parsed = parser.parseFromString(source, "text/html");
  const assetBase = `/processed/${encodeURIComponent(chunkId)}/html/`;

  parsed.querySelectorAll("script").forEach((node) => node.remove());
  parsed.querySelectorAll("img").forEach((image) => {
    image.loading = "eager";
    image.removeAttribute("loading");
    image.removeAttribute("decoding");
  });
  parsed.querySelectorAll("[src], [href]").forEach((node) => {
    for (const attribute of ["src", "href"]) {
      const value = node.getAttribute(attribute);
      if (isRelativeUrl(value)) node.setAttribute(attribute, `${assetBase}${value}`);
    }
  });
  parsed.querySelectorAll("[srcset]").forEach((node) => {
    node.setAttribute("srcset", rewriteSrcset(node.getAttribute("srcset"), assetBase));
  });

  const styles = Array.from(parsed.head.querySelectorAll("style, link[rel='stylesheet']"))
    .map((node) => {
      if (node.tagName.toLowerCase() !== "style") return node.outerHTML;
      const styleId = node.id ? ` id="${node.id}"` : "";
      return `<style${styleId}>${scopeDocumentStyles(node.textContent)}</style>`;
    })
    .join("");
  return `${styles}${parsed.body.innerHTML}`;
}

async function loadChunk(chunk, signal) {
  const response = await fetch(chunk.html_path, { cache: "force-cache", signal });
  if (!response.ok) {
    throw new Error(`${chunk.chunk_id}: ${response.status} ${response.statusText}`);
  }
  return {
    ...chunk,
    preparedHtml: prepareHtml(await response.text(), chunk.chunk_id),
  };
}

function waitForImage(image, signal) {
  if (image.complete) {
    return image.naturalWidth > 0
      ? Promise.resolve()
      : Promise.reject(new Error(`Image failed: ${image.currentSrc || image.src}`));
  }

  return new Promise((resolve, reject) => {
    const cleanup = () => {
      image.removeEventListener("load", onLoad);
      image.removeEventListener("error", onError);
      signal.removeEventListener("abort", onAbort);
    };
    const onLoad = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error(`Image failed: ${image.currentSrc || image.src}`));
    };
    const onAbort = () => {
      cleanup();
      reject(new DOMException("Aborted", "AbortError"));
    };
    image.addEventListener("load", onLoad, { once: true });
    image.addEventListener("error", onError, { once: true });
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export default function MineruHtmlDocument({ manifest, chunkId }) {
  const chunks = useMemo(() => normalizeChunks(manifest), [manifest]);
  const documentId = useMemo(
    () => parseDocumentId(chunkId || chunks[0]?.chunk_id),
    [chunkId, chunks],
  );
  const [loadedChunks, setLoadedChunks] = useState([]);
  const [status, setStatus] = useState("loading-html");
  const [error, setError] = useState("");
  const contentRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    setLoadedChunks([]);
    setStatus("loading-html");
    setError("");

    Promise.all(chunks.map((chunk) => loadChunk(chunk, controller.signal)))
      .then((results) => {
        if (!controller.signal.aborted) {
          setLoadedChunks(results);
          setStatus("loading-assets");
        }
      })
      .catch((loadError) => {
        if (loadError?.name !== "AbortError") {
          setError(String(loadError?.message || loadError));
          setStatus("failed");
        }
      });

    return () => controller.abort();
  }, [chunks]);

  useEffect(() => {
    if (status !== "loading-assets" || loadedChunks.length !== chunks.length) return undefined;
    const controller = new AbortController();
    const frame = requestAnimationFrame(() => {
      const images = Array.from(contentRef.current?.querySelectorAll("img") || []);
      const fontsReady = document.fonts?.ready || Promise.resolve();
      Promise.all([...images.map((image) => waitForImage(image, controller.signal)), fontsReady])
        .then(() => {
          if (!controller.signal.aborted) setStatus("ready");
        })
        .catch((assetError) => {
          if (assetError?.name !== "AbortError") {
            setError(String(assetError?.message || assetError));
            setStatus("failed");
          }
        });
    });
    return () => {
      cancelAnimationFrame(frame);
      controller.abort();
    };
  }, [chunks.length, loadedChunks, status]);

  useEffect(() => {
    const blockEarlyPrint = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "p" && status !== "ready") {
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", blockEarlyPrint);
    return () => window.removeEventListener("keydown", blockEarlyPrint);
  }, [status]);

  if (!chunks.length) {
    return <main className="p-8 text-slate-600">No HTML chunks found.</main>;
  }

  const ready = status === "ready";
  const statusText = status === "loading-html"
    ? `Loading HTML 0/${chunks.length}`
    : status === "loading-assets"
      ? `Loading images ${loadedChunks.length}/${chunks.length}`
      : status === "failed"
        ? "Not ready"
        : "Ready to print";

  return (
    <main className={`print-document ${ready ? "print-document--ready" : "print-document--loading"}`}>
      <header className="print-toolbar">
        <div>
          <strong>{displayName(documentId)}</strong>
          <span>{chunks.length} chunks · {statusText}</span>
        </div>
        <button type="button" disabled={!ready} onClick={() => window.print()}>
          Print / Save as PDF
        </button>
      </header>

      {error ? <div className="print-error">{error}</div> : null}
      {!ready && !error ? <div className="print-loading">{statusText}</div> : null}

      <section ref={contentRef} className="print-content" aria-busy={!ready}>
        {loadedChunks.map((chunk) => (
          <article
            key={chunk.chunk_id}
            className="print-chunk mineru-html-root"
            data-chunk-id={chunk.chunk_id}
            dangerouslySetInnerHTML={{ __html: chunk.preparedHtml }}
          />
        ))}
      </section>
    </main>
  );
}
