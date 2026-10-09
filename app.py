"""Streamlit entry point for the HL7v2 Message Inspector and Validator."""

import json
from base64 import b64encode
from html import escape
from pathlib import Path

import streamlit as st

from parser import decode_upload, inspect_message
from ui import guide_view, inspect_view, summary, validation_view
from validator import validate

ROOT = Path(__file__).resolve().parent
LOGO = b64encode((ROOT / "assets" / "logo.svg").read_bytes()).decode("ascii")
SAMPLES = json.loads((ROOT / "samples" / "manifest.json").read_text())

st.set_page_config(page_title="HL7v2 Message Inspector", page_icon="🔎", layout="wide")
st.html(ROOT / "styles.css")
st.html(ROOT / "assets" / "cloud-chrome.html", unsafe_allow_javascript=True)


def invalidate() -> None:
    st.session_state.pop("report", None)
    st.session_state.pop("inspection", None)


def edit_message() -> None:
    st.session_state.active_text = st.session_state.editor
    st.session_state.source = "Edited input"
    invalidate()


def load_sample() -> None:
    entry = SAMPLES[st.session_state.sample_index]
    st.session_state.active_text = (ROOT / "samples" / entry["file"]).read_text()
    st.session_state.editor = st.session_state.active_text
    st.session_state.source = "Synthetic sample: " + entry["label"]
    st.session_state.upload_epoch += 1
    st.session_state.pop("upload_error", None)
    invalidate()


def reset_workspace() -> None:
    st.session_state.active_text = ""
    st.session_state.editor = ""
    st.session_state.source = "Empty workspace"
    st.session_state.upload_epoch += 1
    st.session_state.pop("upload_error", None)
    st.session_state.navigation = "Message"
    invalidate()


def upload_message() -> None:
    uploaded = st.session_state.get(f"upload_{st.session_state.upload_epoch}")
    if uploaded is None:
        return
    try:
        text = decode_upload(uploaded.getvalue())
    except ValueError as exc:
        st.session_state.upload_error = str(exc)
        return
    st.session_state.active_text = text
    st.session_state.editor = text
    st.session_state.source = "Uploaded input"
    st.session_state.pop("upload_error", None)
    invalidate()


if "active_text" not in st.session_state:
    st.session_state.active_text = (ROOT / "samples" / SAMPLES[0]["file"]).read_text()
    st.session_state.editor = st.session_state.active_text
    st.session_state.source = "Synthetic sample: " + SAMPLES[0]["label"]
    st.session_state.upload_epoch = 0
    st.session_state.navigation = "Message"

if "next_view" in st.session_state:
    st.session_state.navigation = st.session_state.pop("next_view")

if "inspection" not in st.session_state:
    st.session_state.inspection = inspect_message(st.session_state.active_text)
inspection = st.session_state.inspection

st.html(
    '<header class="brand"><div class="brand-mark" aria-hidden="true">'
    f'<img src="data:image/svg+xml;base64,{LOGO}" alt=""></div>'
    "<div><h1>Message Inspector</h1><p>HL7v2 inspection and explainable validation</p></div></header>"
)
view = st.segmented_control(
    "Workspace navigation",
    ["Message", "Inspect", "Validate", "Guide"],
    key="navigation",
    required=True,
    label_visibility="collapsed",
    width="content",
    wrap=True,
)

type_label = " / ".join(inspection.message_type[:2]) or "No message type"
version_label = "HL7v2 · " + (inspection.version or "version not declared")
st.html(
    f'<div class="status-line"><span class="badge badge-teal">{escape(version_label)}</span>'
    f'<span class="badge">{escape(type_label)}</span><span class="badge">{escape(st.session_state.source)}</span></div>'
)

if view != "Guide":
    summary(inspection, st.session_state.get("report"))
    with st.container(horizontal=True):
        if st.button(
            "Run validation",
            type="primary",
            disabled=not st.session_state.active_text,
            help="Run the documented rule checks on the active message.",
        ):
            st.session_state.report = validate(inspection)
            # Navigation widget has already rendered. Queue the change for the next run.
            st.session_state.next_view = "Validate"
            st.rerun()
        st.button("Reset workspace", on_click=reset_workspace)

if view == "Message":
    st.subheader("Message workspace")
    st.caption("Load a synthetic example, upload one message, or edit the text directly.")
    left, right = st.columns([1, 2.4], gap="medium")
    with left:
        with st.container(border=True, key="sample_panel"):
            st.markdown("### Sample library")
            index = st.selectbox(
                "Synthetic sample",
                list(range(len(SAMPLES))),
                format_func=lambda i: SAMPLES[i]["label"],
                key="sample_index",
                persist_state="session",
            )
            st.caption(SAMPLES[index]["description"])
            st.button("Load synthetic sample", on_click=load_sample, width="stretch")
            st.caption("All bundled patients, identifiers, orders, and results are synthetic.")
        with st.container(border=True, key="upload_panel"):
            st.markdown("### Upload a message")
            st.file_uploader(
                "HL7 or text file",
                type=["hl7", "txt"],
                max_upload_size=5,
                key=f"upload_{st.session_state.upload_epoch}",
                on_change=upload_message,
            )
            st.caption("5 MB per file • HL7, TXT")
            st.caption("UTF-8 text · one message")
            if st.session_state.get("upload_error"):
                st.error(st.session_state.upload_error)
    with right:
        with st.container(border=True, key="editor_panel"):
            st.text_area(
                "HL7 message",
                key="editor",
                height=360,
                on_change=edit_message,
                placeholder="Paste one message beginning with MSH...",
                persist_state="session",
            )
            st.caption(
                "Changes invalidate the previous report. Use synthetic or de-identified data."
            )
            for note in inspection.notes:
                st.caption(note)
            if inspection.input_error:
                st.info(inspection.input_error)
            elif inspection.parse_error:
                st.warning(inspection.parse_error)
            else:
                st.caption(
                    "Parsed with hl7apy. Parsing success does not establish validation success."
                )
elif view == "Inspect":
    inspect_view(inspection)
elif view == "Validate":
    validation_view(inspection, st.session_state.get("report"))
else:
    guide_view()

st.html(
    '<footer class="footnote">Selected HL7v2 checks · version 2.5.1 · '
    "synthetic samples · no clinical interpretation</footer>"
)
