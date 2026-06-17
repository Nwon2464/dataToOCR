"""Minimal Streamlit entrypoint for PDF upload and page extraction."""

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from ocr_tool.pipeline.extract_pages import extract_pages_from_pdf
from ocr_tool.pipeline.run_ocr import run_paddle_ocr
from ocr_tool.search import search_corrected_text
from ocr_tool.batch_ocr import (
    BATCH_OCR_MODE_RANGE,
    BATCH_OCR_MODES,
    BatchOCRFailure,
    DEFAULT_MAX_PAGES_PER_BATCH,
    MAX_PAGES_PER_BATCH,
    limit_pages_for_batch_ocr,
    run_batch_ocr_pages,
    run_page_ocr_subprocess,
    select_pages_for_batch_ocr,
)
from ocr_tool.models import (
    LAYOUT_TYPE_DIAGRAM,
    LAYOUT_TYPE_MIXED,
    LAYOUT_TYPE_QUESTION,
    LAYOUT_TYPE_TABLE,
    LAYOUT_TYPE_TEXT,
    LAYOUT_TYPE_TEXT_WITH_SIDEBAR,
    LAYOUT_TYPE_UNKNOWN,
    OCR_MODE_AUTO,
    OCR_MODE_MANUAL,
    OCR_MODE_ORIGINAL_ORDER,
    OCR_MODE_SIDEBAR_SPLIT,
    REVIEW_STATUS_CHECKED,
    REVIEW_STATUS_NEEDS_REVIEW,
    REVIEW_STATUS_REVIEWING,
    REVIEW_STATUS_UNCHECKED,
)
from ocr_tool.storage.db import (
    find_next_page_for_review,
    get_page_review_summary,
    initialize_database,
    insert_document,
    insert_pages,
    list_pages,
    update_page_review_metadata,
)
from ocr_tool.storage.files import (
    get_raw_ocr_text_path,
    load_corrected_text,
    load_raw_ocr_text,
    raw_ocr_exists,
    save_corrected_text,
    save_uploaded_file,
)


MISSING_PYMUPDF_MESSAGE = (
    "PyMuPDF is not installed. Install project dependencies before extracting "
    "pages."
)
REVIEW_STATUS_OPTIONS = [
    REVIEW_STATUS_UNCHECKED,
    REVIEW_STATUS_REVIEWING,
    REVIEW_STATUS_CHECKED,
    REVIEW_STATUS_NEEDS_REVIEW,
]
LAYOUT_TYPE_OPTIONS = [
    LAYOUT_TYPE_UNKNOWN,
    LAYOUT_TYPE_TEXT,
    LAYOUT_TYPE_TEXT_WITH_SIDEBAR,
    LAYOUT_TYPE_TABLE,
    LAYOUT_TYPE_DIAGRAM,
    LAYOUT_TYPE_MIXED,
    LAYOUT_TYPE_QUESTION,
]
OCR_MODE_OPTIONS = [
    OCR_MODE_AUTO,
    OCR_MODE_ORIGINAL_ORDER,
    OCR_MODE_SIDEBAR_SPLIT,
    OCR_MODE_MANUAL,
]
POST_CORRECTED_SAVE_KEEP = "keep current review status"
POST_CORRECTED_SAVE_REVIEWING = "mark as reviewing"
POST_CORRECTED_SAVE_CHECKED = "mark as checked"
POST_CORRECTED_SAVE_OPTIONS = [
    POST_CORRECTED_SAVE_KEEP,
    POST_CORRECTED_SAVE_REVIEWING,
    POST_CORRECTED_SAVE_CHECKED,
]
SELECTED_PAGE_NUMBER_KEY = "selected_page_number"
SEARCH_QUERY_KEY = "search_query"
SEARCH_RESULTS_KEY = "search_results"
SEARCH_PERFORMED_KEY = "search_performed"
LAST_SEARCH_DOCUMENT_ID_KEY = "last_search_document_id"


def main() -> None:
    st.title("Japanese Accounting OCR Review Tool")
    st.write("Upload a PDF, extract page images, and later review OCR text.")

    try:
        initialize_database()
    except Exception as error:
        st.error(f"Database initialization failed: {error}")
        return
    st.caption("Database initialized")

    uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])
    if uploaded_file is None:
        return

    uploaded_bytes = uploaded_file.getvalue()
    upload_key = f"{uploaded_file.name}:{len(uploaded_bytes)}"
    if st.session_state.get("upload_key") != upload_key:
        document = save_uploaded_file(uploaded_file.name, uploaded_bytes)
        try:
            insert_document(document)
        except Exception as error:
            st.error(f"Document metadata save failed: {error}")
            return
        st.session_state["upload_key"] = upload_key
        st.session_state["document"] = document
        st.session_state.pop("pages", None)
        st.session_state.pop("ocr_results", None)
        st.session_state.pop("corrected_results", None)
        st.session_state["document_metadata_saved"] = True
        st.session_state.pop("page_metadata_saved", None)

    document = st.session_state["document"]
    st.subheader("Saved document")
    st.write(f"document_id: {document.id}")
    st.write(f"original_filename: {document.original_filename}")
    st.write(f"input_path: {document.input_path}")
    if st.session_state.get("document_metadata_saved"):
        st.caption("Document metadata saved")

    if "pages" not in st.session_state:
        try:
            persisted_pages = list_pages(document.id)
        except Exception as error:
            st.error(f"Page metadata load failed: {error}")
            return
        if persisted_pages:
            st.session_state["pages"] = persisted_pages

    if st.button("Extract pages"):
        try:
            pages = extract_pages_from_pdf(
                document_id=document.id,
                pdf_path=document.input_path,
                dpi=300,
                image_format="png",
            )
        except ImportError as error:
            if error.name == "fitz":
                st.error(MISSING_PYMUPDF_MESSAGE)
                return
            raise
        except Exception as error:
            st.error(f"Page extraction failed: {error}")
            return

        try:
            insert_pages(pages)
        except Exception as error:
            st.error(f"Page metadata save failed: {error}")
            return
        st.session_state["pages"] = pages
        st.session_state["page_metadata_saved"] = True

    pages = st.session_state.get("pages", [])
    if not pages:
        return
    page_numbers = [page.page_number for page in pages]

    st.subheader("Extracted pages")
    st.write(f"pages_extracted: {len(pages)}")
    for page in pages:
        st.write(f"page {page.page_number}: {page.image_path}")
    if st.session_state.get("page_metadata_saved"):
        st.caption("Page metadata saved")

    try:
        progress_summary = get_page_review_summary(document.id)
    except Exception as error:
        st.error(f"Review progress load failed: {error}")
        return

    review_counts = progress_summary["review_status_counts"]
    layout_counts = progress_summary["layout_type_counts"]
    st.subheader("Review progress")
    metric_columns = st.columns(5)
    metric_columns[0].metric("Total", progress_summary["total_pages"])
    metric_columns[1].metric(
        "Checked",
        review_counts.get(REVIEW_STATUS_CHECKED, 0),
    )
    metric_columns[2].metric(
        "Unchecked",
        review_counts.get(REVIEW_STATUS_UNCHECKED, 0),
    )
    metric_columns[3].metric(
        "Needs review",
        review_counts.get(REVIEW_STATUS_NEEDS_REVIEW, 0),
    )
    metric_columns[4].metric(
        "Manual",
        progress_summary["needs_manual_review_count"],
    )
    if layout_counts:
        layout_summary = ", ".join(
            f"{layout_type}: {count}"
            for layout_type, count in sorted(layout_counts.items())
        )
        st.caption(f"Layout counts: {layout_summary}")

    st.subheader("Batch OCR")
    batch_mode = st.selectbox("OCR target", BATCH_OCR_MODES)
    batch_start_page = None
    batch_end_page = None
    if batch_mode == BATCH_OCR_MODE_RANGE:
        range_columns = st.columns(2)
        with range_columns[0]:
            batch_start_page = st.number_input(
                "Start page",
                min_value=min(page_numbers),
                max_value=max(page_numbers),
                value=min(page_numbers),
                step=1,
            )
        with range_columns[1]:
            batch_end_page = st.number_input(
                "End page",
                min_value=min(page_numbers),
                max_value=max(page_numbers),
                value=max(page_numbers),
                step=1,
            )

    overwrite_existing_raw_ocr = st.checkbox(
        "Overwrite existing raw OCR",
        value=False,
    )
    max_pages_per_batch = st.number_input(
        "Max pages per batch",
        min_value=1,
        max_value=MAX_PAGES_PER_BATCH,
        value=DEFAULT_MAX_PAGES_PER_BATCH,
        step=1,
    )
    st.warning(
        "Batch OCR runs PaddleOCR in isolated worker processes. For large PDFs, "
        "use small ranges first."
    )

    if st.button("Run batch OCR"):
        pages_to_run, pages_to_skip = select_pages_for_batch_ocr(
            pages=pages,
            mode=batch_mode,
            start_page=(
                int(batch_start_page) if batch_start_page is not None else None
            ),
            end_page=int(batch_end_page) if batch_end_page is not None else None,
            overwrite_existing_raw_ocr=overwrite_existing_raw_ocr,
            raw_ocr_exists_func=raw_ocr_exists,
        )
        selected_count = len(pages_to_run)
        pages_to_run, original_selected_count = limit_pages_for_batch_ocr(
            pages_to_run,
            int(max_pages_per_batch),
        )
        if original_selected_count > len(pages_to_run):
            st.info(
                f"Selected {original_selected_count} pages; running first "
                f"{len(pages_to_run)} pages. Increase the limit or use a "
                "smaller range."
            )
        progress = st.progress(0.0)
        status_message = st.empty()
        total_to_run = len(pages_to_run)

        if total_to_run == 0:
            status_message.info("No pages selected for OCR.")
            batch_result = None
        else:
            def update_batch_progress(index, total_pages, page):
                status_message.write(
                    f"Running OCR for page {page.page_number} "
                    f"({index}/{total_pages})"
                )
                progress.progress((index - 1) / total_pages)

            try:
                batch_result = run_batch_ocr_pages(
                    pages_to_run,
                    run_page_ocr_subprocess,
                    lang="japan",
                    progress_callback=update_batch_progress,
                )
            except RuntimeError as error:
                st.error(str(error))
                return
            ocr_results = st.session_state.setdefault("ocr_results", {})
            for page in batch_result.successful_pages:
                ocr_key = f"{document.id}:{page.page_number}"
                try:
                    ocr_results[ocr_key] = load_raw_ocr_text(
                        document.id,
                        page.page_number,
                    )
                except Exception as error:
                    batch_result.failures.append(
                        BatchOCRFailure(
                            page_number=page.page_number,
                            error=f"Raw OCR reload failed: {error}",
                        )
                    )
            progress.progress(1.0)

        if total_to_run:
            status_message.write("Batch OCR complete.")

        success_count = batch_result.success_count if batch_result is not None else 0
        failures = batch_result.failures if batch_result is not None else []
        st.write(f"selected_count: {selected_count}")
        st.write(f"run_count: {total_to_run}")
        st.write(f"success_count: {success_count}")
        st.write(f"skipped_count: {len(pages_to_skip)}")
        st.write(f"failure_count: {len(failures)}")
        if failures:
            st.write("Failures")
            for failure in failures:
                st.error(f"Page {failure.page_number}: {failure.error}")

    st.subheader("Search corrected text")
    if st.session_state.get(LAST_SEARCH_DOCUMENT_ID_KEY) != document.id:
        st.session_state[SEARCH_QUERY_KEY] = ""
        st.session_state[SEARCH_RESULTS_KEY] = []
        st.session_state[SEARCH_PERFORMED_KEY] = False
        st.session_state[LAST_SEARCH_DOCUMENT_ID_KEY] = document.id

    search_query = st.text_input("Search query", key=SEARCH_QUERY_KEY)
    if st.button("Search corrected text"):
        try:
            st.session_state[SEARCH_RESULTS_KEY] = search_corrected_text(
                document.id,
                search_query,
            )
        except Exception as error:
            st.error(f"Corrected text search failed: {error}")
            return
        st.session_state[SEARCH_PERFORMED_KEY] = True

    search_results = st.session_state.get(SEARCH_RESULTS_KEY, [])
    if search_results:
        for index, result in enumerate(search_results):
            st.write(
                f"Page {result['page_number']} "
                f"({result['review_status']}, {result['layout_type']}, "
                f"manual_review={result['needs_manual_review']})"
            )
            st.caption(str(result["snippet"]))
            if st.button(
                f"Go to page {result['page_number']}",
                key=(
                    "search_go_to_page_"
                    f"{document.id}_{result['page_number']}_{index}"
                ),
            ):
                st.session_state[SELECTED_PAGE_NUMBER_KEY] = result["page_number"]
                st.rerun()
    elif st.session_state.get(SEARCH_PERFORMED_KEY):
        st.info("No matches found in corrected text.")

    st.subheader("Page Review")
    if (
        SELECTED_PAGE_NUMBER_KEY not in st.session_state
        or st.session_state[SELECTED_PAGE_NUMBER_KEY] not in page_numbers
    ):
        st.session_state[SELECTED_PAGE_NUMBER_KEY] = page_numbers[0]

    if st.button("Go to next page for review"):
        try:
            next_page = find_next_page_for_review(
                document.id,
                current_page_number=st.session_state[SELECTED_PAGE_NUMBER_KEY],
            )
        except Exception as error:
            st.error(f"Next review page lookup failed: {error}")
            return
        if next_page is None:
            st.info("All pages are checked or no review target remains.")
        else:
            st.session_state[SELECTED_PAGE_NUMBER_KEY] = next_page.page_number
            st.rerun()

    selected_page_number = st.selectbox(
        "Select page",
        page_numbers,
        index=page_numbers.index(st.session_state[SELECTED_PAGE_NUMBER_KEY]),
        key=SELECTED_PAGE_NUMBER_KEY,
    )
    selected_page = next(
        page for page in pages if page.page_number == selected_page_number
    )

    if st.session_state.pop("review_metadata_saved", False):
        st.success("Saved review metadata")
    corrected_saved_path = st.session_state.pop("corrected_text_saved_path", None)
    if corrected_saved_path is not None:
        st.success(f"Saved corrected text: {corrected_saved_path}")

    st.write("Review metadata")
    if (
        selected_page.needs_manual_review
        or selected_page.review_status == REVIEW_STATUS_NEEDS_REVIEW
    ):
        st.warning("This page is marked as needing manual review.")
    elif selected_page.review_status == REVIEW_STATUS_CHECKED:
        st.success("This page is marked as checked.")

    review_status_index = (
        REVIEW_STATUS_OPTIONS.index(selected_page.review_status)
        if selected_page.review_status in REVIEW_STATUS_OPTIONS
        else 0
    )
    layout_type_index = (
        LAYOUT_TYPE_OPTIONS.index(selected_page.layout_type)
        if selected_page.layout_type in LAYOUT_TYPE_OPTIONS
        else 0
    )
    ocr_mode_index = (
        OCR_MODE_OPTIONS.index(selected_page.ocr_mode)
        if selected_page.ocr_mode in OCR_MODE_OPTIONS
        else 0
    )

    metadata_column_1, metadata_column_2 = st.columns(2)
    with metadata_column_1:
        review_status = st.selectbox(
            "Review status",
            REVIEW_STATUS_OPTIONS,
            index=review_status_index,
            key=f"review_status_{document.id}_{selected_page.page_number}",
        )
        layout_type = st.selectbox(
            "Layout type",
            LAYOUT_TYPE_OPTIONS,
            index=layout_type_index,
            key=f"layout_type_{document.id}_{selected_page.page_number}",
        )
    with metadata_column_2:
        ocr_mode = st.selectbox(
            "OCR mode",
            OCR_MODE_OPTIONS,
            index=ocr_mode_index,
            key=f"ocr_mode_{document.id}_{selected_page.page_number}",
        )
        needs_manual_review = st.checkbox(
            "Needs manual review",
            value=selected_page.needs_manual_review,
            key=f"needs_manual_review_{document.id}_{selected_page.page_number}",
        )

    if st.button("Save review metadata"):
        try:
            update_page_review_metadata(
                document_id=document.id,
                page_number=selected_page.page_number,
                review_status=review_status,
                layout_type=layout_type,
                ocr_mode=ocr_mode,
                needs_manual_review=needs_manual_review,
            )
            pages = list_pages(document.id)
        except Exception as error:
            st.error(f"Review metadata save failed: {error}")
            return
        st.session_state["pages"] = pages
        selected_page = next(
            page for page in pages if page.page_number == selected_page_number
        )
        st.session_state["review_metadata_saved"] = True
        st.rerun()

    ocr_key = f"{document.id}:{selected_page.page_number}"
    ocr_results = st.session_state.get("ocr_results", {})
    has_ocr_result = ocr_key in ocr_results

    image_column, ocr_column = st.columns(2)

    with image_column:
        st.write(f"Page {selected_page.page_number}")
        st.image(
            str(selected_page.image_path),
            caption=f"image_path: {selected_page.image_path}",
        )

    with ocr_column:
        st.write("Raw OCR text")
        if has_ocr_result:
            st.text_area(
                "Raw OCR text",
                value=ocr_results[ocr_key],
                height=420,
                disabled=True,
            )
            st.write(
                "raw_ocr_path: "
                f"{get_raw_ocr_text_path(document.id, selected_page.page_number)}"
            )
            button_label = "Run OCR again for selected page"
            st.caption("Rerun overwrites raw OCR text only.")
        else:
            st.info(
                "OCR has not been run for this page yet. Run OCR first, then "
                "edit corrected text."
            )
            button_label = "Run OCR for selected page"

        if st.button(button_label):
            try:
                raw_ocr_text = run_paddle_ocr(
                    document_id=document.id,
                    page_number=selected_page.page_number,
                    image_path=selected_page.image_path,
                    lang="japan",
                )
            except RuntimeError as error:
                st.error(str(error))
                return
            except Exception as error:
                st.error(f"OCR failed: {error}")
                return

            ocr_results = st.session_state.setdefault("ocr_results", {})
            ocr_results[ocr_key] = raw_ocr_text
            st.rerun()

        if has_ocr_result:
            corrected_results = st.session_state.setdefault("corrected_results", {})
            corrected_widget_key = (
                f"corrected_text_{document.id}_{selected_page.page_number}"
            )
            corrected_text_exists = False
            try:
                existing_corrected_text = load_corrected_text(
                    document.id,
                    selected_page.page_number,
                )
                corrected_text_exists = True
            except FileNotFoundError:
                existing_corrected_text = corrected_results.get(
                    ocr_key,
                    ocr_results[ocr_key],
                )

            if corrected_widget_key not in st.session_state:
                corrected_results[ocr_key] = existing_corrected_text
                st.session_state[corrected_widget_key] = corrected_results[ocr_key]

            if corrected_text_exists:
                st.caption("Corrected text exists for this page.")

            corrected_text = st.text_area(
                "Corrected text",
                key=corrected_widget_key,
                height=420,
            )
            post_save_action = st.selectbox(
                "After saving corrected text",
                POST_CORRECTED_SAVE_OPTIONS,
                key=(
                    "post_corrected_save_action_"
                    f"{document.id}_{selected_page.page_number}"
                ),
            )
            if st.button("Save corrected text"):
                try:
                    saved_path = save_corrected_text(
                        document.id,
                        selected_page.page_number,
                        corrected_text,
                    )
                    if post_save_action == POST_CORRECTED_SAVE_REVIEWING:
                        update_page_review_metadata(
                            document.id,
                            selected_page.page_number,
                            review_status=REVIEW_STATUS_REVIEWING,
                        )
                    elif post_save_action == POST_CORRECTED_SAVE_CHECKED:
                        update_page_review_metadata(
                            document.id,
                            selected_page.page_number,
                            review_status=REVIEW_STATUS_CHECKED,
                            needs_manual_review=False,
                        )
                    pages = list_pages(document.id)
                except Exception as error:
                    st.error(f"Corrected text save failed: {error}")
                    return
                corrected_results[ocr_key] = corrected_text
                st.session_state["pages"] = pages
                st.session_state["corrected_text_saved_path"] = str(saved_path)
                st.rerun()


if __name__ == "__main__":
    main()
