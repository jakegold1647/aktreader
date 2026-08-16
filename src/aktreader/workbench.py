"""Local desktop transcription workbench for AKT Reader projects.

The workbench is intentionally a local Tk application, not a browser or a
localhost service.  It displays the imported source image, overlays PAGE XML
line bounds, and appends human transcription revisions to the project store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from aktreader.project import (
    ProjectStoreError,
    list_project_documents,
    list_project_pages,
    load_project_page,
    resolve_review_proposal,
    revise_line_transcription,
)


class WorkbenchError(ValueError):
    """Raised when the local interactive workbench cannot be started."""


def _document_page_groups(
    documents: list[dict[str, object]],
    pages: list[dict[str, object]],
) -> list[tuple[dict[str, object], list[dict[str, object]]]]:
    """Partition stable project pages by their immutable document imports."""

    pages_by_manifest: dict[str, list[dict[str, object]]] = {}
    for page in pages:
        manifest_sha256 = page.get("manifest_sha256")
        page_index = page.get("page_index")
        if not isinstance(manifest_sha256, str) or not isinstance(page_index, int):
            raise WorkbenchError("project page identity is invalid")
        pages_by_manifest.setdefault(manifest_sha256, []).append(page)
    groups: list[tuple[dict[str, object], list[dict[str, object]]]] = []
    seen_manifests: set[str] = set()
    for document in documents:
        manifest_sha256 = document.get("manifest_sha256")
        title = document.get("title")
        page_count = document.get("page_count")
        if (
            not isinstance(manifest_sha256, str)
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(page_count, int)
            or page_count < 1
            or manifest_sha256 in seen_manifests
        ):
            raise WorkbenchError("project document metadata is invalid")
        document_pages = pages_by_manifest.pop(manifest_sha256, [])
        if len(document_pages) != page_count:
            raise WorkbenchError("project document page count is inconsistent")
        groups.append((document, document_pages))
        seen_manifests.add(manifest_sha256)
    if pages_by_manifest:
        raise WorkbenchError("project pages are missing document metadata")
    if not groups:
        raise WorkbenchError("project has no imported documents; import PAGE XML before opening it")
    return groups


class LocalWorkbench:
    """A compact image-and-line transcription editor for one local project."""

    def __init__(
        self,
        project: Path | str,
        *,
        tk: Any,
        ttk: Any,
        messagebox: Any,
        image_tk: Any,
    ) -> None:
        self.project = Path(project)
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.image_tk = image_tk
        self.pages = list_project_pages(self.project)
        self.documents = list_project_documents(self.project)
        self.document_page_groups = _document_page_groups(self.documents, self.pages)
        self.root = tk.Tk()
        self.root.title("AKT Reader Workbench — local-only")
        self.root.minsize(960, 640)
        self.current_document: dict[str, object] | None = None
        self.current_document_pages: list[dict[str, object]] = []
        self.current_page: dict[str, object] | None = None
        self.current_lines: list[dict[str, object]] = []
        self.line_indices: dict[str, int] = {}
        self.photo: Any = None
        self.scale = 1.0
        self._build()
        self._show_document(0)

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        toolbar = self.ttk.Frame(self.root, padding=8)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        toolbar.columnconfigure(3, weight=1)
        self.ttk.Label(toolbar, text="Document").grid(row=0, column=0, sticky="w")
        self.document_selector = self.ttk.Combobox(
            toolbar,
            state="readonly",
            values=[
                f"{index + 1}. {document['title']} ({document['page_count']} pages)"
                for index, (document, _pages) in enumerate(self.document_page_groups)
            ],
        )
        self.document_selector.grid(row=0, column=1, padx=(8, 16), sticky="ew")
        self.document_selector.bind("<<ComboboxSelected>>", self._on_document_changed)
        self.ttk.Label(toolbar, text="Page").grid(row=0, column=2, sticky="w")
        self.page_selector = self.ttk.Combobox(toolbar, state="readonly")
        self.page_selector.grid(row=0, column=3, padx=(8, 16), sticky="ew")
        self.page_selector.bind("<<ComboboxSelected>>", self._on_page_changed)
        self.ttk.Label(toolbar, text="Editor").grid(row=0, column=4, sticky="w")
        self.editor = self.ttk.Entry(toolbar, width=20)
        self.editor.insert(0, "local-user")
        self.editor.grid(row=0, column=5, padx=(8, 0), sticky="e")

        image_frame = self.ttk.Frame(self.root, padding=(8, 0, 4, 8))
        image_frame.grid(row=1, column=0, sticky="nsew")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
        self.canvas = self.tk.Canvas(image_frame, background="#1f2933", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        side = self.ttk.Frame(self.root, padding=(4, 0, 8, 8))
        side.grid(row=1, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=2)
        side.rowconfigure(3, weight=3)
        self.ttk.Label(side, text="Lines").grid(row=0, column=0, sticky="w")
        self.line_list = self.tk.Listbox(side, exportselection=False)
        self.line_list.grid(row=1, column=0, sticky="nsew")
        self.line_list.bind("<<ListboxSelect>>", self._on_line_selected)
        self.ttk.Label(side, text="Transcription").grid(row=2, column=0, pady=(8, 0), sticky="w")
        self.text_editor = self.tk.Text(side, height=7, wrap="word", undo=True)
        self.text_editor.grid(row=3, column=0, sticky="nsew")
        self.suggestion_label = self.ttk.Label(
            side,
            justify="left",
            text="No engine suggestion for the selected line",
            wraplength=360,
        )
        self.suggestion_label.grid(row=4, column=0, pady=(8, 0), sticky="ew")
        self.review_label = self.ttk.Label(
            side,
            justify="left",
            text="No pending reviewer proposal for the selected line",
            wraplength=360,
        )
        self.review_label.grid(row=5, column=0, pady=(6, 0), sticky="ew")
        controls = self.ttk.Frame(side)
        controls.grid(row=6, column=0, pady=(8, 0), sticky="ew")
        controls.columnconfigure(3, weight=1)
        self.save_button = self.ttk.Button(
            controls,
            text="Save human revision",
            command=self._save_revision,
        )
        self.save_button.grid(row=0, column=0, sticky="w")
        self.use_suggestion_button = self.ttk.Button(
            controls,
            command=self._use_suggestion,
            state="disabled",
            text="Use engine suggestion",
        )
        self.use_suggestion_button.grid(row=0, column=1, padx=(8, 0), sticky="w")
        self.accept_review_button = self.ttk.Button(
            controls,
            command=self._accept_review_proposal,
            state="disabled",
            text="Accept reviewer proposal",
        )
        self.accept_review_button.grid(row=0, column=2, padx=(8, 0), sticky="w")
        self.status = self.ttk.Label(controls, text="Local-only; source XML is never overwritten")
        self.status.grid(row=0, column=3, padx=(12, 0), sticky="w")

    def _on_document_changed(self, _event: Any) -> None:
        index = self.document_selector.current()
        if index >= 0:
            self._show_document(index)

    def _show_document(self, document_choice_index: int) -> None:
        if not 0 <= document_choice_index < len(self.document_page_groups):
            raise WorkbenchError("selected project document is unavailable")
        document, pages = self.document_page_groups[document_choice_index]
        self.current_document = document
        self.current_document_pages = pages
        self.document_selector.current(document_choice_index)
        self.page_selector.configure(
            values=[
                (
                    f"{index + 1} of {len(pages)}. {page['page_id']} "
                    f"({page['width_px']}×{page['height_px']})"
                )
                for index, page in enumerate(pages)
            ]
        )
        self._show_page(0)

    def _on_page_changed(self, _event: Any) -> None:
        index = self.page_selector.current()
        if index >= 0:
            self._show_page(index)

    def _show_page(self, page_choice_index: int) -> None:
        if not 0 <= page_choice_index < len(self.current_document_pages):
            raise WorkbenchError("selected document page is unavailable")
        selected = self.current_document_pages[page_choice_index]
        page = load_project_page(
            self.project,
            manifest_sha256=str(selected["manifest_sha256"]),
            page_index=int(selected["page_index"]),
        )
        self.current_page = page
        self.current_lines = list(page["lines"])
        self.line_indices = {
            str(line["source_span_id"]): index for index, line in enumerate(self.current_lines)
        }
        self.page_selector.current(page_choice_index)
        self._draw_page()
        self._populate_lines()
        document_title = (
            str(self.current_document["title"])
            if self.current_document is not None
            else "selected document"
        )
        self.status.configure(
            text=f"Local-only; {document_title}; source XML is never overwritten"
        )

    def _draw_page(self) -> None:
        if self.current_page is None:
            return
        image_path = Path(str(self.current_page["image_path"]))
        try:
            with Image.open(image_path) as source:
                image = source.copy()
        except OSError as error:
            raise WorkbenchError(f"cannot open project image: {image_path}") from error
        image.thumbnail((900, 720))
        self.scale = image.width / int(self.current_page["width_px"])
        self.photo = self.image_tk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.configure(width=image.width, height=image.height)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for line in self.current_lines:
            bbox = line["bbox"]
            x0 = int(bbox["x"] * self.scale)
            y0 = int(bbox["y"] * self.scale)
            x1 = int((bbox["x"] + bbox["width"]) * self.scale)
            y1 = int((bbox["y"] + bbox["height"]) * self.scale)
            span_id = str(line["source_span_id"])
            tag = f"line:{span_id}"
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline="#f6ad55",
                width=2,
                tags=(tag, "line-box"),
            )
            self.canvas.tag_bind(
                tag,
                "<Button-1>",
                lambda _event, value=span_id: self._select_span(value),
            )

    def _populate_lines(self) -> None:
        self.line_list.delete(0, "end")
        self.text_editor.delete("1.0", "end")
        for line in self.current_lines:
            text = line["text"]
            preview = "∅" if text is None else str(text).replace("\n", " ")[:48]
            self.line_list.insert(
                "end",
                f"{line['line_id']}  r{line['revision']}  {preview}",
            )
        if self.current_lines:
            self._select_line(0)

    def _on_line_selected(self, _event: Any) -> None:
        selected = self.line_list.curselection()
        if selected:
            self._select_line(int(selected[0]), select_list=False)

    def _select_span(self, source_span_id: str) -> None:
        index = self.line_indices.get(source_span_id)
        if index is not None:
            self._select_line(index)

    def _select_line(self, index: int, *, select_list: bool = True) -> None:
        if not 0 <= index < len(self.current_lines):
            return
        if select_list:
            self.line_list.selection_clear(0, "end")
            self.line_list.selection_set(index)
            self.line_list.activate(index)
            self.line_list.see(index)
        line = self.current_lines[index]
        self.text_editor.delete("1.0", "end")
        if line["text"] is not None:
            self.text_editor.insert("1.0", str(line["text"]))
        suggestions = list(line["suggestions"])
        if suggestions and suggestions[0]["text"] is not None:
            suggestion = suggestions[0]
            preview = str(suggestion["text"]).replace("\n", " ")[:96]
            self.suggestion_label.configure(
                text=f"{suggestion['engine']} suggestion (review before saving): {preview}"
            )
            self.use_suggestion_button.configure(state="normal")
        elif suggestions:
            self.suggestion_label.configure(
                text=f"{suggestions[0]['engine']} produced no text for this line"
            )
            self.use_suggestion_button.configure(state="disabled")
        else:
            self.suggestion_label.configure(text="No engine suggestion for the selected line")
            self.use_suggestion_button.configure(state="disabled")
        reviews = list(line["review_proposals"])
        pending = next((review for review in reviews if review["state"] == "PENDING"), None)
        if pending is not None:
            preview = str(pending["text"]).replace("\n", " ")[:96]
            self.review_label.configure(
                text=f"Reviewer {pending['contributor']} proposal: {preview}"
            )
            self.accept_review_button.configure(state="normal")
        elif reviews:
            self.review_label.configure(
                text="Reviewer proposal is stale; compare it manually before revising"
            )
            self.accept_review_button.configure(state="disabled")
        else:
            self.review_label.configure(
                text="No pending reviewer proposal for the selected line"
            )
            self.accept_review_button.configure(state="disabled")
        self.canvas.itemconfigure("line-box", outline="#f6ad55")
        self.canvas.itemconfigure(f"line:{line['source_span_id']}", outline="#68d391")

    def _use_suggestion(self) -> None:
        selected = self.line_list.curselection()
        if not selected:
            return
        line = self.current_lines[int(selected[0])]
        suggestions = list(line["suggestions"])
        if not suggestions or suggestions[0]["text"] is None:
            return
        self.text_editor.delete("1.0", "end")
        self.text_editor.insert("1.0", str(suggestions[0]["text"]))
        self.status.configure(
            text="Engine suggestion copied to editor; review it, then save a human revision"
        )

    def _accept_review_proposal(self) -> None:
        selected = self.line_list.curselection()
        if not selected:
            return
        line = self.current_lines[int(selected[0])]
        proposal = next(
            (
                value
                for value in line["review_proposals"]
                if value["state"] == "PENDING"
            ),
            None,
        )
        if proposal is None:
            return
        editor = self.editor.get().strip()
        try:
            result = resolve_review_proposal(
                self.project,
                proposal_sha256=str(proposal["proposal_sha256"]),
                decision="accept",
                editor=editor,
            )
        except ProjectStoreError as error:
            self.messagebox.showerror("AKT Reader", str(error))
            return
        self.status.configure(
            text=(
                "Reviewer proposal became stale; compare it manually"
                if result["status"] == "CONFLICT"
                else f"Accepted reviewer proposal as human revision {result['revision']}"
            )
        )
        page_index = self.page_selector.current()
        self._show_page(page_index)
        self._select_span(str(line["source_span_id"]))

    def _save_revision(self) -> None:
        if self.current_page is None:
            return
        selected = self.line_list.curselection()
        if not selected:
            self.messagebox.showwarning(
                "AKT Reader",
                "Select a line before saving a transcription.",
            )
            return
        line = self.current_lines[int(selected[0])]
        editor = self.editor.get().strip()
        text = self.text_editor.get("1.0", "end-1c")
        try:
            result = revise_line_transcription(
                self.project,
                manifest_sha256=str(self.current_page["manifest_sha256"]),
                source_span_id=str(line["source_span_id"]),
                text=text,
                editor=editor,
            )
        except ProjectStoreError as error:
            self.messagebox.showerror("AKT Reader", str(error))
            return
        self.status.configure(
            text=(
                "No change to save"
                if result["status"] == "UNCHANGED"
                else f"Saved human revision {result['revision']}"
            )
        )
        page_index = self.page_selector.current()
        self._show_page(page_index)
        self._select_span(str(line["source_span_id"]))

    def run(self) -> None:
        """Enter the local desktop event loop."""

        self.root.mainloop()


def launch_workbench(project: Path | str) -> None:
    """Open the local image-and-line transcription workbench."""

    try:
        import tkinter as tk
        from tkinter import messagebox, ttk

        from PIL import ImageTk
    except ImportError as error:
        raise WorkbenchError(
            "this Python installation has no Tk desktop support; install a Python build "
            "with tkinter"
        ) from error
    LocalWorkbench(
        project,
        tk=tk,
        ttk=ttk,
        messagebox=messagebox,
        image_tk=ImageTk,
    ).run()
