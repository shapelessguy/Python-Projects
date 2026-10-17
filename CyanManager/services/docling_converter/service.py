"""Docling (IBM), document conversion on the GPU: PDF, Office files, HTML and images to Markdown.

Like Whisper in the STT service, the models run in this process: enabling the
service loads them onto CUDA (downloading them the first time, into
HuggingFace's cache), disabling it frees the VRAM.

Everyone, this PC included, reaches it through the API server
(services/api_server): POST /docling/start with the document as the body,
then GET /docling/status/{job_id} until it is done.
"""
import gc
import threading
import time
from utils import Parameter, wait
from PyQt5.QtWidgets import QCheckBox


NAME = "Docling"
PARAMETERS = {
    # Read at load: toggling it takes effect when the service is re-enabled.
    "OCR": Parameter(True, QCheckBox),
}

FORMATS = ("markdown", "html", "json", "text")


def build_converter(ocr: bool):
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=ocr,
        # Its "auto" OCR would take a CPU onnxruntime first, if one is installed.
        ocr_options=RapidOcrOptions(backend="torch"),
        do_table_structure=True,
        # Pictures cropped out of the page, for ?images=embedded; at 2x the 72 dpi page.
        generate_picture_images=True,
        images_scale=2.0,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CUDA),
    )
    converter = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
    })
    # Layout, table and OCR models now rather than on the first document.
    converter.initialize_pipeline(InputFormat.PDF)
    return converter


def convert(thread_manager, path: str, fmt: str = "markdown", images: bool = False,
            progress: dict | None = None) -> dict | None:
    """Converts the file at path; None if the service is not loaded.

    images puts the pictures into Markdown and HTML as base64 PNGs instead of
    <!-- image --> placeholders (JSON always carries them). One document at a
    time on the GPU: the others wait as "queued".
    """
    from docling_core.types.doc import ImageRefMode
    signal = thread_manager.signal if thread_manager else None
    if not signal or not getattr(signal, "docling_converter", None):
        return None

    with signal.docling_lock:
        converter = signal.docling_converter
        if converter is None:  # disabled while this one was queued
            return None
        if progress is not None:
            progress["status"] = "running"
            progress["started"] = time.time()
        document = converter.convert(path).document

    image_mode = ImageRefMode.EMBEDDED if images else ImageRefMode.PLACEHOLDER
    if fmt == "html":
        content = document.export_to_html(image_mode=image_mode)
    elif fmt == "json":
        content = document.export_to_dict()
    elif fmt == "text":
        content = document.export_to_text()
    else:
        content = document.export_to_markdown(image_mode=image_mode)
    return {"content": content, "pages": len(document.pages)}


def entrypoint(thread_manager):
    import torch
    signal = thread_manager.signal

    if not torch.cuda.is_available():
        print("Docling: CUDA is not available, not loading")
        return

    signal.docling_lock = threading.Lock()
    signal.docling_converter = build_converter(bool(thread_manager.get_param("OCR")))
    print("Docling loaded")

    while signal.is_alive() and not thread_manager.to_kill:
        wait(signal, 100)

    with signal.docling_lock:  # not under a conversion still running
        signal.docling_converter = None
    gc.collect()
    torch.cuda.empty_cache()

    print(f"{thread_manager.name} thread down..")
