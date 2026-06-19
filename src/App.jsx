import { useEffect, useState } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

const SAMPLE_CHUNK_ID = "USCPA_REG1_p001_010";
const ALPHA_SECTION_RE = /^[a-z]\)\s*/;
const NUMBERED_SECTION_RE = /^\d+[）)]\s*/;
const IMPORTANT_IMAGE_KEYWORDS = ["Input期", "Output期", "推奨学習パターン", "トレーニング", "学習", "flow", "pattern"];
const ICON_IMAGE_KEYWORDS = ["アイコンについて", "補足", "用語", "参照", "MC", "TBS"];
const MATH_BLOCK_TYPES = new Set(["equation", "formula", "math", "equation_interline", "interline_equation", "inline_equation"]);

function cx(...values) {
  const seen = new Set();
  const classes = [];
  values
    .flatMap((value) => String(value || "").split(/\s+/))
    .filter(Boolean)
    .forEach((className) => {
      if (!seen.has(className)) {
        seen.add(className);
        classes.push(className);
      }
    });
  return classes.join(" ");
}

function routeChunkId() {
  const match = window.location.pathname.match(/^\/mineru-preview\/([^/]+)/);
  return match?.[1] || SAMPLE_CHUNK_ID;
}

function textOf(block) {
  return String(block?.text || "").replace(/\s+/g, " ").trim();
}

function isAlphaSection(block) {
  return ALPHA_SECTION_RE.test(textOf(block));
}

function isNumberedSection(block) {
  return NUMBERED_SECTION_RE.test(textOf(block));
}

function imageClassFor(block, index, blocks) {
  if (block.block_type !== "image") return "";
  if (block.imageClassName) return block.imageClassName;

  const context = blocks
    .slice(Math.max(0, index - 4), index)
    .map(textOf)
    .filter(Boolean)
    .join("\n");
  const lower = context.toLowerCase();

  if (ICON_IMAGE_KEYWORDS.some((keyword) => context.includes(keyword))) return "icon-image";
  if (IMPORTANT_IMAGE_KEYWORDS.some((keyword) => context.includes(keyword) || lower.includes(keyword.toLowerCase()))) {
    return "important-image";
  }
  return "normal-image";
}

function indentClassesFor(block, index, blocks) {
  if (block.sectionClassName || block.indentClassName) {
    return cx(block.sectionClassName, block.indentClassName);
  }

  if (block.role === "decorative" || ["title", "table_body", "image"].includes(block.block_type)) return "";
  if (isAlphaSection(block)) return "section-alpha";
  if (isNumberedSection(block)) return "section-numbered indent-level-1";
  if (block.block_type !== "text" || block.kind !== "paragraph") return "";

  let previousNumbered = false;
  let inAlphaSection = false;
  for (let i = index - 1; i >= 0; i -= 1) {
    const previous = blocks[i];
    if (previous?.role === "decorative" || ["image", "table_body"].includes(previous?.block_type)) continue;
    if (previous?.block_type === "title") break;
    if (isAlphaSection(previous)) {
      inAlphaSection = true;
      break;
    }
    if (isNumberedSection(previous)) {
      previousNumbered = true;
    }
  }

  if (previousNumbered) return "indent-level-2";
  if (inAlphaSection) return "indent-level-1";
  return "";
}

function normalizeHtml(html, chunkId) {
  if (!html) return "";
  return String(html).replace(/src=(["'])images\//g, `src=$1/processed/${chunkId}/images/`);
}

function stripHtml(html) {
  return String(html || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;/g, "'")
    .trim();
}

function isMathBlock(block) {
  const blockType = String(block?.block_type || "").toLowerCase();
  const originalType = String(block?.source?.original_type || "").toLowerCase();
  return MATH_BLOCK_TYPES.has(blockType) || MATH_BLOCK_TYPES.has(originalType);
}

function mathSource(block) {
  const mathContent = String(block?.math_content || "").trim();
  if (mathContent) return mathContent;
  const text = String(block?.text || "").trim();
  if (text) return text;
  return stripHtml(block?.html);
}

function themeStyle(block) {
  const fill = Array.isArray(block.theme?.fill) ? block.theme.fill.join(", ") : "13, 83, 222";
  const stroke = Array.isArray(block.theme?.stroke) ? block.theme.stroke.join(", ") : fill;
  return {
    "--data-fill": fill,
    "--data-stroke": stroke,
  };
}

function blockTypeClass(block) {
  if (block.block_type === "title") return "border-l-4 pl-4";
  if (block.block_type === "header" || block.block_type === "footer" || block.block_type === "page_number") {
    return "text-sm text-slate-500";
  }
  return "";
}

function MathBlock({ block }) {
  const source = mathSource(block);
  if (!source) return null;

  try {
    const rendered = katex.renderToString(source, {
      displayMode: true,
      throwOnError: true,
      strict: "ignore",
      trust: false,
      output: "html",
    });
    return (
      <div
        className="math-render math-block"
        dangerouslySetInnerHTML={{ __html: rendered }}
      />
    );
  } catch (err) {
    if (import.meta.env.DEV) {
      console.warn("[math] KaTeX render failed", {
        blockId: block?.id,
        blockType: block?.block_type,
        originalType: block?.source?.original_type,
        reason: err?.message || String(err),
        source,
      });
    }
    return <pre className="math-block">{source}</pre>;
  }
}

function RenderBlock({ block, index, blocks, chunkId }) {
  if ((block.role || "content") === "decorative") return null;

  const imageClass = imageClassFor(block, index, blocks);
  const indentClasses = indentClassesFor(block, index, blocks);
  const extraClassName = cx(block.extraClassName, imageClass, indentClasses);
  const wrapperClassName = cx("relative md-wrapper my-3", imageClass ? `image-block ${imageClass}` : "", indentClasses);
  const containerClassName = cx(
    "markdown-container markdown-theme-base relative",
    block.className || "custom-block-text",
    blockTypeClass(block),
    extraClassName,
  );

  const safeHtml = normalizeHtml(block.html, block.chunk_id || chunkId);

  return (
    <hgroup className={wrapperClassName} data-block-id={block.id}>
      <div className={containerClassName} style={themeStyle(block)}>
        {isMathBlock(block) ? (
          <div className="markdownRender">
            <MathBlock block={block} />
          </div>
        ) : safeHtml ? (
          <div className="markdownRender" dangerouslySetInnerHTML={{ __html: safeHtml }} />
        ) : (
          <div className="markdownRender">
            <p>{block.text || ""}</p>
          </div>
        )}
      </div>
    </hgroup>
  );
}

function RenderPage({ page, chunkId }) {
  const blocks = Array.isArray(page.blocks) ? page.blocks : [];
  return (
    <section id={`page-${page.page}`} className="page-card mx-auto mb-8 max-w-[900px] rounded-2xl bg-white p-10 shadow">
      <div className="mb-5 text-xs font-bold tracking-widest text-slate-500">PAGE {page.page}</div>
      <div className="page-wrapper-content">
        {blocks.map((block, index) => (
          <RenderBlock key={block.id || index} block={block} index={index} blocks={blocks} chunkId={chunkId} />
        ))}
      </div>
    </section>
  );
}

function RenderSidebar({ pages }) {
  return (
    <aside className="sidebar sticky top-0 h-screen overflow-y-auto bg-slate-900 px-5 py-6 text-white">
      <div className="mb-5 text-lg font-bold">MinerU Preview</div>
      <nav className="grid gap-1">
        {pages.map((page) => (
          <a
            key={page.page}
            href={`#page-${page.page}`}
            className="page-link overflow-hidden truncate rounded-lg px-3 py-2 text-sm text-blue-100 hover:bg-white/10 hover:text-white"
          >
            P{page.page} · {page.title || `Page ${page.page}`}
          </a>
        ))}
      </nav>
    </aside>
  );
}

function RenderDocument({ renderJson, chunkId }) {
  const pages = Array.isArray(renderJson?.pages) ? renderJson.pages : [];
  return (
    <div className="min-h-screen bg-slate-100 lg:grid lg:grid-cols-[280px_1fr]">
      <RenderSidebar pages={pages} />
      <main className="main-content p-4 lg:p-8">
        {pages.map((page) => (
          <RenderPage key={page.page} page={page} chunkId={chunkId} />
        ))}
      </main>
    </div>
  );
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
      <RenderDocument renderJson={renderJson} chunkId={chunkId} />
    ) : (
      <main className="min-h-screen bg-slate-100 p-8 text-slate-600">loading {chunkId}</main>
    )
  );
}

export default App;
