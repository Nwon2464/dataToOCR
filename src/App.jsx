import { useEffect, useState } from "react";
import JsonRenderDocument from "./renderers/JsonRenderDocument";

function routeChunkId() {
  const match = window.location.pathname.match(/^\/mineru-preview\/([^/]+)/);
  return match?.[1] || "USCPA_REG1_p001_010";
}

function App() {
  const [chunkId] = useState(routeChunkId());
  const [renderJson, setRenderJson] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!chunkId) return;
    setStatus("loading");
    fetch("/processed/render_all.json")
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((data) => {
        if (import.meta.env.DEV) {
          const pages = Array.isArray(data?.pages) ? data.pages.length : 0;
          const blocks = Array.isArray(data?.blocks) ? data.blocks.length : 0;
          console.info(`[render] pages: ${pages}, blocks: ${blocks}`);
        }
        setRenderJson(data);
        setStatus("ready");
        setError("");
      })
      .catch((err) => {
        setRenderJson(null);
        setStatus("failed");
        setError(String(err));
      });
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

  return (
    renderJson ? (
      <JsonRenderDocument renderJson={renderJson} chunkId={chunkId} />
    ) : (
      <main className="min-h-screen bg-slate-100 p-8 text-slate-600">loading {chunkId}</main>
    )
  );
}

export default App;
