import { useEffect, useMemo, useState } from "react";
import "./GoodNotesExportView.css";

function parseChunkId() {
  const match = window.location.pathname.match(/^\/goodnotes-export\/([^/]+)\/?$/);
  if (!match) return "";

  try {
    return decodeURIComponent(match[1]);
  } catch {
    return "";
  }
}

function documentNameFromChunkId(chunkId) {
  return chunkId.replace(/_p\d+_\d+$/, "").replace(/[_-]+/g, " ");
}

function isRelativeUrl(value) {
  const url = String(value || "").trim();
  return Boolean(url) && !url.startsWith("#") && !url.startsWith("/") &&
    !/^[a-z][a-z\d+.-]*:/i.test(url) && !url.startsWith("//");
}

function sanitizeHtml(source, chunkId) {
  const parser = new DOMParser();
  const document = parser.parseFromString(source, "text/html");
  const assetBase = `/processed/${encodeURIComponent(chunkId)}/html/`;

  document.querySelectorAll("script").forEach((node) => node.remove());
  document.querySelectorAll("[src], [href]").forEach((node) => {
    for (const attribute of ["src", "href"]) {
      const value = node.getAttribute(attribute);
      if (isRelativeUrl(value)) node.setAttribute(attribute, `${assetBase}${value}`);
    }
  });

  const headContent = Array.from(document.head.querySelectorAll("style, link[rel='stylesheet']"))
    .map((node) => node.outerHTML)
    .join("");

  return `${headContent}${document.body.innerHTML}`;
}

export default function GoodNotesExportView() {
  const chunkId = useMemo(parseChunkId, []);
  const [html, setHtml] = useState("");
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!chunkId) {
      setStatus("failed");
      setError("Invalid GoodNotes export URL.");
      return undefined;
    }

    const controller = new AbortController();

    async function loadHtml() {
      try {
        const response = await fetch(
          `/processed/${encodeURIComponent(chunkId)}/html/index.html`,
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

        const source = await response.text();
        setHtml(sanitizeHtml(source, chunkId));
        setStatus("ready");
      } catch (loadError) {
        if (loadError.name === "AbortError") return;
        setError(String(loadError));
        setStatus("failed");
      }
    }

    loadHtml();
    return () => controller.abort();
  }, [chunkId]);

  const documentName = documentNameFromChunkId(chunkId) || "Document";

  return (
    <main className="goodnotes-export">
      <header className="goodnotes-toolbar">
        <div className="goodnotes-toolbar__identity">
          <strong>{documentName}</strong>
          <span>{chunkId || "Unknown chunk"}</span>
        </div>
        <button
          type="button"
          onClick={() => window.print()}
          disabled={status !== "ready"}
        >
          Print / Save as PDF
        </button>
      </header>

      <section className="goodnotes-preview" aria-busy={status === "loading"}>
        {status === "loading" && <p className="goodnotes-message">Loading preview...</p>}
        {status === "failed" && <p className="goodnotes-message goodnotes-message--error">{error}</p>}
        {status === "ready" && (
          <article
            className="goodnotes-sheet"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        )}
      </section>
    </main>
  );
}
