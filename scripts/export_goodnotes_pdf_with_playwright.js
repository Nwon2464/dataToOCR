import { spawn } from "node:child_process";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";
import { chromium } from "playwright";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "..");
const HOST = process.env.GOODNOTES_EXPORT_HOST || "127.0.0.1";
const PORT = Number(process.env.GOODNOTES_EXPORT_PORT || 4173);
const BASE_URL = process.env.GOODNOTES_EXPORT_BASE_URL || `http://${HOST}:${PORT}`;
const DOCUMENT_TITLE = process.env.GOODNOTES_DOCUMENT_TITLE || "USCPA REG1";
const OUTPUT_PATH = path.resolve(
  PROJECT_ROOT,
  process.env.GOODNOTES_OUTPUT_PATH ||
    "exports/goodnotes/raw/USCPA_REG1_goodnotes_no_header.pdf",
);
const TOC_OUTPUT_PATH = path.resolve(
  PROJECT_ROOT,
  process.env.GOODNOTES_TOC_OUTPUT_PATH || "data/processed/toc_pdf.json",
);
const READY_TIMEOUT_MS = Number(process.env.GOODNOTES_READY_TIMEOUT_MS || 300_000);

function normalizeText(value) {
  return String(value || "").normalize("NFKC").replace(/\s+/g, " ").trim();
}

function compactText(value) {
  return normalizeText(value).toLowerCase().replace(/\s+/g, "");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function findPdfPages(pdfPath, chapters) {
  const pdfBytes = new Uint8Array(await readFile(pdfPath));
  const pdf = await getDocument({ data: pdfBytes, useSystemFonts: true }).promise;
  try {
    const pageTexts = [];
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const pdfPage = await pdf.getPage(pageNumber);
      const textContent = await pdfPage.getTextContent();
      pageTexts.push(normalizeText(textContent.items.map((item) => item.str || "").join(" ")));
      pdfPage.cleanup();
    }

    const toc = [];
    let searchStart = 0;
    for (const chapter of chapters) {
      const chapterPattern = new RegExp(
        `chapter\\s*${escapeRegExp(chapter.number)}(?!\\d)(?!\\s*contents)`,
        "i",
      );
      const titleNeedle = compactText(chapter.titleText);
      let matchedPage = null;

      for (let index = searchStart; index < pageTexts.length; index += 1) {
        const currentText = pageTexts[index];
        const currentAndNext = `${currentText} ${pageTexts[index + 1] || ""}`;
        if (!chapterPattern.test(currentText)) continue;
        const compactWindow = compactText(currentAndNext);
        if (!compactWindow.includes(titleNeedle)) continue;
        if (!compactWindow.includes(compactText("本章のポイント"))) continue;
        matchedPage = index + 1;
        searchStart = index + 1;
        break;
      }

      if (matchedPage == null) {
        throw new Error(`Could not map chapter to PDF page: ${chapter.label}`);
      }
      toc.push({ title: chapter.label, page: matchedPage, level: 1 });
    }
    return { toc, pageCount: pdf.numPages };
  } finally {
    await pdf.destroy();
  }
}

function startServer() {
  const viteBin = path.join(PROJECT_ROOT, "node_modules", "vite", "bin", "vite.js");
  const child = spawn(
    process.execPath,
    [viteBin, "--host", HOST, "--port", String(PORT), "--strictPort"],
    {
      cwd: PROJECT_ROOT,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  child.stdout.on("data", (chunk) => process.stdout.write(`[server] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[server] ${chunk}`));
  return child;
}

async function waitForServer(server) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`Vite server exited with code ${server.exitCode}`);
    }
    try {
      const response = await fetch(BASE_URL);
      if (response.ok) return;
    } catch {
      // Server still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for server: ${BASE_URL}`);
}

async function stopServer(server) {
  if (!server || server.exitCode !== null) return;
  server.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => server.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (server.exitCode === null) server.kill("SIGKILL");
}

async function waitForReaderReady(page) {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  let previousStatus = "";

  while (Date.now() < deadline) {
    const snapshot = await page.evaluate(() => {
      const toolbarStatus = document.querySelector(".print-toolbar span")?.textContent?.trim() || "";
      const error = document.querySelector(".print-error")?.textContent?.trim() || "";
      const images = Array.from(document.images);
      return {
        toolbarStatus,
        error,
        chunks: document.querySelectorAll(".print-chunk").length,
        imagesReady: images.filter((image) => image.complete && image.naturalWidth > 0).length,
        imagesTotal: images.length,
        fonts: document.fonts.status,
      };
    });

    if (snapshot.error) throw new Error(`Reader failed: ${snapshot.error}`);
    const status = `${snapshot.toolbarStatus} | chunks ${snapshot.chunks} | ` +
      `images ${snapshot.imagesReady}/${snapshot.imagesTotal} | fonts ${snapshot.fonts}`;
    if (status !== previousStatus) {
      console.log(`[reader] ${status}`);
      previousStatus = status;
    }
    if (snapshot.toolbarStatus.includes("Ready to print") &&
        snapshot.fonts === "loaded" &&
        snapshot.imagesReady === snapshot.imagesTotal) {
      return snapshot.toolbarStatus;
    }
    await page.waitForTimeout(1_000);
  }
  throw new Error(`Timed out waiting for Ready to print after ${READY_TIMEOUT_MS}ms`);
}

async function exportPdf() {
  let server;
  let browser;
  try {
    server = startServer();
    await waitForServer(server);
    console.log(`[open] ${BASE_URL}`);

    const manifestResponse = await fetch(`${BASE_URL}/processed/html_manifest.json`);
    if (!manifestResponse.ok) {
      throw new Error(
        `HTML manifest unavailable (${manifestResponse.status}). ` +
        "Run scripts/build_html_manifest.py before PDF export.",
      );
    }
    const manifest = await manifestResponse.json();
    if (!Array.isArray(manifest?.chunks) || manifest.chunks.length === 0) {
      throw new Error("HTML manifest contains no chunks");
    }
    console.log(`[manifest] ${manifest.chunks.length} chunks`);

    console.log("[browser] launching Chromium");
    browser = await chromium.launch({
      headless: true,
      channel: "chromium",
      timeout: 30_000,
    });
    console.log("[browser] Chromium launched");
    const page = await browser.newPage();
    page.setDefaultTimeout(READY_TIMEOUT_MS);
    page.on("pageerror", (error) => console.error(`[page error] ${error.message}`));
    page.on("requestfailed", (request) => {
      const errorText = request.failure()?.errorText || "";
      if (errorText === "net::ERR_ABORTED") return;
      console.error(`[request failed] ${request.url()} ${errorText}`);
    });

    console.log("[page] loading Library");
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    const documentCard = page.locator("article").filter({
      has: page.getByText(DOCUMENT_TITLE, { exact: true }),
    });
    await documentCard.waitFor({ state: "visible", timeout: 30_000 });
    await documentCard.getByRole("button", { name: "Open Reader" }).click();
    console.log(`[page] Open Reader clicked: ${DOCUMENT_TITLE}`);

    const readyStatus = await waitForReaderReady(page);
    console.log(`[ready] ${readyStatus}`);

    const chapters = await page.evaluate(() => {
      const clean = (value) => String(value || "").normalize("NFKC").replace(/\s+/g, " ").trim();
      const results = [];
      const seen = new Set();

      for (const chunk of document.querySelectorAll(".print-chunk")) {
        const elements = Array.from(chunk.querySelectorAll("h1, h2, h3, h4, h5, h6, p"));
        for (let index = 0; index < elements.length; index += 1) {
          const chapterText = clean(elements[index].textContent);
          const match = chapterText.match(/^Chapter\s*(\d+)\s*(.*)$/i);
          if (!match || /\bContents\b/i.test(chapterText)) continue;

          const number = Number(match[1]);
          if (seen.has(number)) continue;
          const nextChapterIndex = elements.findIndex((element, candidateIndex) => {
            if (candidateIndex <= index) return false;
            return /^Chapter\s*\d+\s*$/i.test(clean(element.textContent));
          });
          const regionEnd = nextChapterIndex === -1 ? elements.length : nextChapterIndex;
          const markerIndex = elements.findIndex((element, candidateIndex) => {
            return candidateIndex > index && candidateIndex < regionEnd &&
              clean(element.textContent).includes("本章のポイント");
          });
          if (markerIndex === -1) continue;

          let titleText = clean(match[2]);
          if (!titleText) {
            for (let candidateIndex = index + 1; candidateIndex < markerIndex; candidateIndex += 1) {
              const candidate = clean(elements[candidateIndex].textContent);
              if (!candidate || /^Chapter\s*\d+/i.test(candidate)) continue;
              titleText = candidate;
              break;
            }
          }
          if (!titleText) throw new Error(`Chapter ${number} title not found in DOM`);

          seen.add(number);
          results.push({
            number,
            titleText,
            label: `${number} ${titleText}`,
            chunkId: chunk.dataset.chunkId || "",
          });
        }
      }
      return results.sort((left, right) => left.number - right.number);
    });
    if (!chapters.length) throw new Error("No Chapter X + 本章のポイント regions found in Reader DOM");
    console.log(`[chapters] ${chapters.length}`);

    await page.emulateMedia({ media: "print" });
    await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
    await page.pdf({
      path: OUTPUT_PATH,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
    });

    const outputStat = await stat(OUTPUT_PATH);
    if (!outputStat.isFile() || outputStat.size === 0) {
      throw new Error(`PDF output is empty: ${OUTPUT_PATH}`);
    }
    console.log(`[pdf] ${path.relative(PROJECT_ROOT, OUTPUT_PATH)}`);
    console.log(`[size] ${outputStat.size} bytes`);

    const { toc, pageCount } = await findPdfPages(OUTPUT_PATH, chapters);
    await mkdir(path.dirname(TOC_OUTPUT_PATH), { recursive: true });
    await writeFile(TOC_OUTPUT_PATH, `${JSON.stringify(toc, null, 2)}\n`, "utf8");
    for (const item of toc) console.log(`[toc] ${item.title} -> PDF page ${item.page}`);
    console.log(`[toc pdf pages] ${pageCount}`);
    console.log(`[toc write] ${path.relative(PROJECT_ROOT, TOC_OUTPUT_PATH)}`);
  } finally {
    await browser?.close();
    await stopServer(server);
  }
}

exportPdf().catch((error) => {
  console.error(`[error] ${error.stack || error}`);
  process.exitCode = 1;
});
