function chunkLabel(chunk) {
  if (!chunk) return "Chunk";
  const title = String(chunk.title || chunk.chunk_id || "").trim();
  const start = chunk.page_start;
  const end = chunk.page_end;
  if (start && end) return `${title || "Chunk"} · p.${start}-${end}`;
  if (start) return `${title || "Chunk"} · p.${start}`;
  return title || "Chunk";
}

function RenderSidebar({ chunks }) {
  return (
    <aside className="sticky top-0 h-screen overflow-y-auto border-r border-slate-200 bg-slate-950 px-5 py-6 text-slate-50">
      <div className="mb-6">
        <div className="text-lg font-semibold tracking-tight">HTML viewer</div>
        <div className="mt-1 text-xs text-slate-400">chunk iframe list</div>
      </div>
      <nav className="grid gap-2">
        {chunks.map((chunk, index) => {
          const id = `chunk-${chunk.chunk_id || index}`;
          return (
            <a
              key={chunk.chunk_id || index}
              href={`#${id}`}
              className="rounded-xl px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10 hover:text-white"
            >
              {chunkLabel(chunk)}
            </a>
          );
        })}
      </nav>
    </aside>
  );
}

function RenderChunkCard({ chunk, index }) {
  const id = `chunk-${chunk.chunk_id || index}`;
  const label = chunkLabel(chunk);

  return (
    <section id={id} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-900">{label}</div>
          <div className="mt-0.5 text-xs text-slate-500">{chunk.html_path || ""}</div>
        </div>
        <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
          {chunk.chunk_id || `chunk-${index + 1}`}
        </div>
      </div>

      <iframe
        key={chunk.html_path || id}
        title={label}
        src={chunk.html_path}
        className="min-h-[80vh] w-full rounded-2xl border border-slate-200 bg-white"
      />
    </section>
  );
}

export default function MineruHtmlDocument({ manifest }) {
  const chunks = Array.isArray(manifest?.chunks) ? manifest.chunks : [];

  return (
    <div className="min-h-screen bg-slate-100 lg:grid lg:grid-cols-[280px_1fr]">
      <RenderSidebar chunks={chunks} />
      <main className="space-y-5 p-4 lg:p-8">
        {chunks.map((chunk, index) => (
          <RenderChunkCard key={chunk.chunk_id || index} chunk={chunk} index={index} />
        ))}
      </main>
    </div>
  );
}
