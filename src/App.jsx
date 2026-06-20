import { useEffect, useMemo, useState } from "react";
import LibraryView from "./components/LibraryView";
import GoodNotesExportView from "./components/GoodNotesExportView";
import { groupChunksByDocument } from "./lib/documents";
import JsonRenderDocument from "./renderers/JsonRenderDocument";
import MineruHtmlDocument from "./renderers/MineruHtmlDocument";

function routeChunkId() {
  const match = window.location.pathname.match(/^\/mineru-preview\/([^/]+)/);
  return match?.[1] || "USCPA_REG1_p001_010";
}

function ViewerApp() {
  const [chunkId] = useState(routeChunkId());
  const [mode, setMode] = useState("loading");
  const [manifest, setManifest] = useState(null);
  const [renderJson, setRenderJson] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [view, setView] = useState("library");
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);

  const documents = useMemo(() => {
    return groupChunksByDocument(manifest?.chunks || []);
  }, [manifest]);

  const selectedDocument = useMemo(() => {
    if (!documents.length) return null;
    return (
      documents.find((document) => document.document_id === selectedDocumentId) ||
      documents[0]
    );
  }, [documents, selectedDocumentId]);

  const selectedManifest = useMemo(() => {
    if (!manifest || !selectedDocument) return manifest;
    return {
      ...manifest,
      chunks: selectedDocument.chunks,
    };
  }, [manifest, selectedDocument]);

  useEffect(() => {
    if (!chunkId) return;
    let active = true;

    async function loadViewer() {
      setStatus("loading");
      setError("");
      setMode("loading");

      try {
        const manifestResponse = await fetch("/processed/html_manifest.json");
        if (manifestResponse.ok) {
          const data = await manifestResponse.json();
          const chunks = Array.isArray(data?.chunks) ? data.chunks : [];
          if (chunks.length > 0) {
            if (!active) return;
            setManifest(data);
            setRenderJson(null);
            setMode("html");
            setStatus("ready");
            if (import.meta.env.DEV) console.info("[viewer] html mode");
            return;
          }
        }
      } catch (err) {
        void err;
      }

      try {
        const response = await fetch("/processed/render_all.json");
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        const data = await response.json();
        if (!active) return;
        if (import.meta.env.DEV) {
          const pages = Array.isArray(data?.pages) ? data.pages.length : 0;
          const blocks = Array.isArray(data?.blocks) ? data.blocks.length : 0;
          console.info(`[render] pages: ${pages}, blocks: ${blocks}`);
          console.info("[viewer] json fallback mode");
        }
        setManifest(null);
        setRenderJson(data);
        setMode("json");
        setStatus("ready");
        setError("");
      } catch (err) {
        if (!active) return;
        setManifest(null);
        setRenderJson(null);
        setMode("failed");
        setStatus("failed");
        setError(String(err));
      }
    }

    loadViewer();
    return () => {
      active = false;
    };
  }, [chunkId]);

  if (error) {
    return (
      <main className="min-h-screen bg-slate-100 p-8">
        <div className="mx-auto max-w-2xl rounded-2xl bg-white p-8 shadow">
          <p className="text-sm text-slate-500">{chunkId} / {status}</p>
          <p className="mt-3 text-red-700">{error}</p>
        </div>
      </main>
    );
  }

  if (mode === "html" && manifest) {
    if (view === "library") {
      return (
        <LibraryView
          documents={documents}
          onOpenDocument={(documentId) => {
            setSelectedDocumentId(documentId);
            setView("reader");
          }}
        />
      );
    }

    if (!selectedDocument || !selectedManifest) {
      return (
        <main className="min-h-screen bg-slate-100 p-8 text-slate-600">
          No documents found.
        </main>
      );
    }

    return (
      <MineruHtmlDocument
        manifest={selectedManifest}
        chunkId={selectedDocument.chunks[0]?.chunk_id || chunkId}
      />
    );
  }

  return renderJson ? (
    <JsonRenderDocument renderJson={renderJson} chunkId={chunkId} />
  ) : (
    <main className="min-h-screen bg-slate-100 p-8 text-slate-600">
      loading {chunkId}
    </main>
  );
}

function App() {
  if (window.location.pathname.startsWith("/goodnotes-export/")) {
    return <GoodNotesExportView />;
  }

  return <ViewerApp />;
}

export default App;
