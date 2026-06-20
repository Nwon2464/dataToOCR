import { useState } from "react";
import { formatPageRange } from "../lib/documents";
import { calculateProgressPercent, loadReaderProgress } from "../lib/readerProgress";

function LibraryDocumentCard({ document, onOpenDocument }) {
  const [exportChunkId, setExportChunkId] = useState(document.chunks[0]?.chunk_id || "");
  const progress = loadReaderProgress(document.document_id);
  const progressPercent = calculateProgressPercent(progress, document.page_end);
  const lastRange = progress
    ? formatPageRange(
        progress.page_start || progress.current_page_start,
        progress.page_end || progress.current_page_end,
      )
    : null;

  return (
    <article className="min-h-40 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-xl font-bold tracking-tight text-slate-950">{document.title}</div>
      <div className="mt-3 text-sm text-slate-600">
        {formatPageRange(document.page_start, document.page_end)}
      </div>
      <div className="mt-1 text-sm text-slate-500">{document.chunk_count} chunks</div>
      <div className="mt-5 text-sm font-medium text-slate-800">
        {lastRange ? `Last: ${lastRange}` : "Not started"}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full rounded-full bg-slate-900 transition-[width] duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <span className="min-w-9 text-right text-xs font-medium text-slate-500">
          {progressPercent}%
        </span>
      </div>

      <div className="mt-5 grid gap-2">
        <button
          type="button"
          onClick={() => onOpenDocument(document.document_id)}
          className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white active:bg-slate-700"
        >
          Open Reader
        </button>
        <select
          value={exportChunkId}
          onChange={(event) => setExportChunkId(event.target.value)}
          aria-label={`${document.title} export chunk`}
          className="min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
        >
          {document.chunks.map((chunk) => (
            <option key={chunk.chunk_id} value={chunk.chunk_id}>
              {formatPageRange(chunk.page_start, chunk.page_end)} · {chunk.chunk_id}
            </option>
          ))}
        </select>
        <a
          href={`/goodnotes-export/${encodeURIComponent(exportChunkId)}`}
          className="rounded-lg border border-slate-300 px-3 py-2 text-center text-sm font-semibold text-slate-800 active:bg-slate-50"
        >
          Export PDF
        </a>
      </div>
    </article>
  );
}

export default function LibraryView({ documents, onOpenDocument }) {
  return (
    <main className="min-h-screen bg-slate-100 px-4 py-6 text-slate-950 sm:px-6">
      <section className="mx-auto max-w-3xl">
        <div className="mb-5">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
            현재 저장된 텍스트 데이터
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            공부할 문서를 선택하세요.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {documents.map((document) => (
            <LibraryDocumentCard
              key={document.document_id}
              document={document}
              onOpenDocument={onOpenDocument}
            />
          ))}
        </div>
      </section>
    </main>
  );
}
