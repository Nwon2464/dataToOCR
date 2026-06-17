import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import ocr_tool.pipeline.run_ocr as run_ocr
from ocr_tool.pipeline.run_ocr import (
    MISSING_PADDLEOCR_MESSAGE,
    build_paddle_ocr_options,
    create_paddle_ocr_engine,
    extract_ordered_text_lines_from_paddle_result,
    extract_text_lines_from_paddle_result,
    flatten_ocr_lines,
    normalize_box,
    run_ocr_with_engine,
    run_paddle_ocr,
    validate_page_number,
)


class FakeBox:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, index):
        return self.values[index]

    def __len__(self):
        return len(self.values)


class FakeBoxArray:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, index):
        return self.rows[index]

    def __len__(self):
        return len(self.rows)


def test_flatten_ocr_lines_strips_whitespace():
    assert flatten_ocr_lines(["  財務会計  "]) == "財務会計"


def test_flatten_ocr_lines_removes_empty_lines():
    assert flatten_ocr_lines(["売上", "", "   ", "費用"]) == "売上\n費用"


def test_flatten_ocr_lines_joins_lines_with_newline():
    assert flatten_ocr_lines(["line 1", "line 2", "line 3"]) == "line 1\nline 2\nline 3"


def test_flatten_ocr_lines_returns_empty_string_for_all_empty_input():
    assert flatten_ocr_lines(["", "  ", "\t"]) == ""


def test_validate_page_number_accepts_one():
    assert validate_page_number(1) == 1


@pytest.mark.parametrize("page_number", [0, -1])
def test_validate_page_number_rejects_non_positive_values(page_number):
    with pytest.raises(ValueError):
        validate_page_number(page_number)


def test_extract_text_lines_from_paddle_result_parses_page_result():
    result = [
        [
            [[[0, 0], [1, 0], [1, 1], [0, 1]], (" 売上高 ", 0.98)],
            [[[0, 2], [1, 2], [1, 3], [0, 3]], ("費用", 0.95)],
        ]
    ]

    assert extract_text_lines_from_paddle_result(result) == ["売上高", "費用"]


def test_extract_text_lines_from_paddle_result_parses_flat_result():
    result = [
        [[[0, 0], [1, 0], [1, 1], [0, 1]], ("資産", 0.99)],
        [[[0, 2], [1, 2], [1, 3], [0, 3]], ("負債", 0.97)],
    ]

    assert extract_text_lines_from_paddle_result(result) == ["資産", "負債"]


def test_extract_text_lines_from_paddle_result_ignores_malformed_items():
    result = [None, ["not text score"], [("valid", 0.9)], [(" ", 0.5)]]

    assert extract_text_lines_from_paddle_result(result) == ["valid"]


def test_extract_text_lines_from_paddle_result_parses_rec_texts_list_in_dict():
    result = [{"rec_texts": [" A ", "", "B"]}]

    assert extract_text_lines_from_paddle_result(result) == ["A", "B"]


def test_extract_text_lines_from_paddle_result_parses_single_rec_texts_dict():
    result = {"rec_texts": ["line1", "line2"]}

    assert extract_text_lines_from_paddle_result(result) == ["line1", "line2"]


def test_extract_text_lines_from_paddle_result_ignores_dict_without_rec_texts():
    result = {"rec_scores": [0.9, 0.8]}

    assert extract_text_lines_from_paddle_result(result) == []


def test_extract_text_lines_from_paddle_result_ignores_non_string_rec_texts():
    result = {"rec_texts": ["line1", None, 123, "  ", "line2"]}

    assert extract_text_lines_from_paddle_result(result) == ["line1", "line2"]


def test_extract_text_lines_from_paddle_result_parses_dict_like_ocr_result():
    class FakeOCRResult:
        def __getitem__(self, key):
            if key == "rec_texts":
                return ["REG1 1-3 不法行為", " b)不法行為の種類 "]
            raise KeyError(key)

    assert extract_text_lines_from_paddle_result([FakeOCRResult()]) == [
        "REG1 1-3 不法行為",
        "b)不法行為の種類",
    ]


def test_extract_ordered_text_lines_from_paddle_result_separates_side_notes():
    result = [
        {
            "rec_texts": ["main 1", "side 1", "main 2", "side 2"],
            "rec_boxes": [
                [100, 100, 900, 130],
                [1800, 110, 2100, 140],
                [100, 200, 900, 230],
                [1800, 210, 2100, 240],
            ],
        }
    ]

    assert extract_ordered_text_lines_from_paddle_result(result) == [
        "main 1",
        "main 2",
        "",
        "[SIDE NOTE]",
        "side 1",
        "side 2",
    ]


def test_extract_ordered_text_lines_from_paddle_result_falls_back_on_length_mismatch():
    result = {
        "rec_texts": ["main 1", "side 1"],
        "rec_boxes": [[100, 100, 900, 130]],
    }

    assert extract_ordered_text_lines_from_paddle_result(result) == [
        "main 1",
        "side 1",
    ]


def test_extract_ordered_text_lines_from_paddle_result_returns_main_lines_without_side_notes():
    result = {
        "rec_texts": ["main 2", "main 1"],
        "rec_boxes": [
            [100, 200, 900, 230],
            [100, 100, 900, 130],
        ],
    }

    assert extract_ordered_text_lines_from_paddle_result(result) == ["main 1", "main 2"]


def test_extract_ordered_text_lines_from_paddle_result_ignores_empty_non_string_texts():
    result = {
        "rec_texts": [" main ", "", None, 123, " side "],
        "rec_boxes": [
            [100, 100, 900, 130],
            [100, 150, 900, 180],
            [100, 200, 900, 230],
            [100, 250, 900, 280],
            [1800, 300, 2100, 330],
        ],
    }

    assert extract_ordered_text_lines_from_paddle_result(result) == [
        "main",
        "",
        "[SIDE NOTE]",
        "side",
    ]


def test_extract_ordered_text_lines_from_paddle_result_accepts_numpy_like_boxes():
    result = [
        {
            "rec_texts": ["main 1", "side 1", "main 2", "side 2"],
            "rec_boxes": FakeBoxArray(
                [
                    FakeBox([100, 100, 900, 130]),
                    FakeBox([1800, 110, 2100, 140]),
                    FakeBox([100, 200, 900, 230]),
                    FakeBox([1800, 210, 2100, 240]),
                ]
            ),
        }
    ]

    assert extract_ordered_text_lines_from_paddle_result(result) == [
        "main 1",
        "main 2",
        "",
        "[SIDE NOTE]",
        "side 1",
        "side 2",
    ]


def test_extract_ordered_text_lines_from_paddle_result_ignores_one_malformed_box():
    result = {
        "rec_texts": ["main 1", "bad box", "side 1"],
        "rec_boxes": [
            [100, 100, 900, 130],
            ["bad"],
            [1800, 210, 2100, 240],
        ],
    }

    assert extract_ordered_text_lines_from_paddle_result(result) == [
        "main 1",
        "",
        "[SIDE NOTE]",
        "side 1",
    ]


def test_extract_ordered_text_lines_from_paddle_result_falls_back_if_all_boxes_malformed():
    result = {
        "rec_texts": ["main 1", "side 1"],
        "rec_boxes": [["bad"], ["also bad"]],
    }

    assert extract_ordered_text_lines_from_paddle_result(result) == [
        "main 1",
        "side 1",
    ]


def test_normalize_box_accepts_numpy_like_box():
    assert normalize_box(FakeBox([1, 2, 3, 4])) == (1.0, 2.0, 3.0, 4.0)


def test_run_paddle_ocr_rejects_invalid_page_number_before_ocr_import(tmp_path):
    image_path = tmp_path / "page_0001.png"

    with pytest.raises(ValueError):
        run_paddle_ocr("doc123", 0, image_path)


def test_run_paddle_ocr_rejects_missing_image_before_ocr_import(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_paddle_ocr("doc123", 1, tmp_path / "missing.png")


def test_run_paddle_ocr_missing_paddleocr_raises_runtime_error(tmp_path, monkeypatch):
    image_path = tmp_path / "page_0001.png"
    image_path.write_bytes(b"image")
    monkeypatch.setitem(sys.modules, "paddleocr", None)

    with pytest.raises(RuntimeError, match=MISSING_PADDLEOCR_MESSAGE):
        run_paddle_ocr("doc123", 1, image_path)


def test_create_paddle_ocr_engine_uses_lazy_import(monkeypatch):
    created_options = []

    class FakePaddleOCR:
        def __init__(
            self,
            lang,
            use_doc_orientation_classify,
            use_doc_unwarping,
            use_textline_orientation,
        ):
            created_options.append(
                {
                    "lang": lang,
                    "use_doc_orientation_classify": use_doc_orientation_classify,
                    "use_doc_unwarping": use_doc_unwarping,
                    "use_textline_orientation": use_textline_orientation,
                }
            )

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )

    engine = create_paddle_ocr_engine("japan")

    assert isinstance(engine, FakePaddleOCR)
    assert created_options == [
        {
            "lang": "japan",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
    ]


def test_build_paddle_ocr_options_skips_unsupported_lightweight_kwargs():
    class FakePaddleOCR:
        def __init__(self, lang):
            self.lang = lang

    assert build_paddle_ocr_options(FakePaddleOCR, "japan", True) == {
        "lang": "japan"
    }


def test_build_paddle_ocr_options_disables_supported_lightweight_models():
    class FakePaddleOCR:
        def __init__(
            self,
            lang,
            use_doc_orientation_classify,
            use_doc_unwarping,
            use_textline_orientation,
        ):
            self.lang = lang

    assert build_paddle_ocr_options(FakePaddleOCR, "japan", True) == {
        "lang": "japan",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }


def test_create_paddle_ocr_engine_falls_back_when_kwargs_rejected(monkeypatch):
    created_options = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            created_options.append(kwargs)
            if len(kwargs) > 1:
                raise TypeError("unsupported kwargs")

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )

    create_paddle_ocr_engine("japan", lightweight=True)

    assert created_options == [
        {
            "lang": "japan",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {"lang": "japan"},
    ]


def test_run_ocr_with_engine_uses_provided_engine(tmp_path, monkeypatch):
    image_path = tmp_path / "page_0001.png"
    image_path.write_bytes(b"image")
    saved_calls = []
    engine_calls = []

    class FakeEngine:
        def ocr(self, image_path_arg):
            engine_calls.append(image_path_arg)
            return {"rec_texts": [" reused ", " engine "]}

    def fake_save_raw_ocr_text(document_id, page_number, text):
        saved_calls.append((document_id, page_number, text))
        return tmp_path / "ocr_raw" / document_id / f"page_{page_number:04d}.txt"

    monkeypatch.setattr(run_ocr, "save_raw_ocr_text", fake_save_raw_ocr_text)

    text = run_ocr_with_engine(FakeEngine(), "doc123", 1, image_path)

    assert text == "reused\nengine"
    assert engine_calls == [str(image_path)]
    assert saved_calls == [("doc123", 1, "reused\nengine")]


def test_run_paddle_ocr_uses_engine_factory(tmp_path, monkeypatch):
    image_path = tmp_path / "page_0001.png"
    image_path.write_bytes(b"image")
    calls = []
    fake_engine = object()

    def fake_create_paddle_ocr_engine(lang, lightweight):
        calls.append(("create", lang, lightweight))
        return fake_engine

    def fake_run_ocr_with_engine(engine, document_id, page_number, image_path_arg):
        calls.append(("run", engine, document_id, page_number, image_path_arg))
        return "raw text"

    monkeypatch.setattr(
        run_ocr,
        "create_paddle_ocr_engine",
        fake_create_paddle_ocr_engine,
    )
    monkeypatch.setattr(
        run_ocr,
        "run_ocr_with_engine",
        fake_run_ocr_with_engine,
    )

    text = run_paddle_ocr("doc123", 1, image_path, lang="japan")

    assert text == "raw text"
    assert calls == [
        ("create", "japan", True),
        ("run", fake_engine, "doc123", 1, image_path),
    ]


def test_run_paddle_ocr_saves_raw_text_and_returns_text(tmp_path, monkeypatch):
    image_path = tmp_path / "page_0001.png"
    image_path.write_bytes(b"image")
    saved_calls = []

    class FakePaddleOCR:
        def __init__(self, lang):
            assert lang == "japan"

        def ocr(self, image_path_arg):
            assert image_path_arg == str(image_path)
            return [
                [
                    [[[0, 0], [1, 0], [1, 1], [0, 1]], ("売上", 0.98)],
                    [[[0, 2], [1, 2], [1, 3], [0, 3]], (" 費用 ", 0.95)],
                ]
            ]

    def fake_save_raw_ocr_text(document_id, page_number, text):
        saved_calls.append((document_id, page_number, text))
        return tmp_path / "ocr_raw" / document_id / f"page_{page_number:04d}.txt"

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )
    monkeypatch.setattr(run_ocr, "save_raw_ocr_text", fake_save_raw_ocr_text)

    text = run_paddle_ocr("doc123", 1, image_path)

    assert text == "売上\n費用"
    assert saved_calls == [("doc123", 1, "売上\n費用")]
