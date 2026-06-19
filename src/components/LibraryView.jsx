import { formatPageRange } from "../lib/documents";
import { calculateProgressPercent, loadReaderProgress } from "../lib/readerProgress";

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
          {documents.map((document) => {
            const progress = loadReaderProgress(document.document_id);
            const progressPercent = calculateProgressPercent(progress, document.page_end);
            const lastRange = progress
              ? formatPageRange(
                  progress.page_start || progress.current_page_start,
                  progress.page_end || progress.current_page_end,
                )
              : null;

            return (
              <button
                key={document.document_id}
                type="button"
                onClick={() => onOpenDocument(document.document_id)}
                className="min-h-40 rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition active:scale-[0.99] active:bg-slate-50"
              >
                <div className="text-xl font-bold tracking-tight text-slate-950">
                  {document.title}
                </div>

                <div className="mt-3 text-sm text-slate-600">
                  {formatPageRange(document.page_start, document.page_end)}
                </div>

                <div className="mt-1 text-sm text-slate-500">
                  {document.chunk_count} chunks
                </div>

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
              </button>
            );
          })}
        </div>
      </section>
    </main>
  );
}
