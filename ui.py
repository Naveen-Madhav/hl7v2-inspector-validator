"""Presentation helpers. All message-derived HTML is escaped before rendering."""

from html import escape

import streamlit as st

from parser import Inspection, field_rows, segment_tree
from validator import PROFILE_VERSION, ValidationReport


def summary(inspection: Inspection, report: ValidationReport | None) -> None:
    values = [
        ("Segments", str(len(inspection.segments)), "In the active message"),
        ("Errors", str(report.errors) if report else "Pending", "Required corrections"),
        ("Warnings", str(report.warnings) if report else "Pending", "Items to review"),
    ]
    markup = "".join(
        f'<div class="summary-item"><div class="summary-label">{label}</div>'
        f'<div class="summary-value">{value}</div><div class="summary-note">{note}</div></div>'
        for label, value, note in values
    )
    st.html(f'<div class="summary">{markup}</div>')


def inspect_view(inspection: Inspection) -> None:
    st.subheader("Inspect message")
    st.caption("Select a segment occurrence. Field positions and raw values are preserved.")
    if not inspection.segments or not inspection.encoding:
        st.info(
            "Usable header delimiters are needed for field inspection. Review the message or run validation."
        )
        return
    if not inspection.parsed:
        st.warning(
            "Raw inspection only. hl7apy parsing did not succeed; field metadata is available only for recognized versions."
        )
    options = list(range(len(inspection.segments)))
    index = st.selectbox(
        "Segment occurrence",
        options,
        format_func=lambda i: inspection.segments[i].label,
        key="segment_index",
    )
    segment = inspection.segments[index]
    with st.container(border=True, key="inspection_panel"):
        st.code(segment.raw, language=None, wrap_lines=True)
        show_empty = st.checkbox("Show empty fields", value=True, key="show_empty")
        rows = field_rows(segment, inspection.version)
        if not show_empty:
            rows = [row for row in rows if row["State"] != "Empty"]
        head = (
            "<tr>"
            + "".join(
                f'<th scope="col">{name}</th>'
                for name in ("Field", "Name", "Datatype", "Value", "State")
            )
            + "</tr>"
        )
        body = "".join(
            "<tr>"
            + "".join(
                f"<td>{escape(str(row[key]))}</td>"
                for key in ("Field", "Name", "Datatype", "Value", "State")
            )
            + "</tr>"
            for row in rows
        )
        st.html(
            f'<div class="table-scroll"><table class="field-table"><caption>Fields in {escape(segment.label)}</caption><thead>{head}</thead><tbody>{body}</tbody></table></div>'
        )
    with st.expander(
        "Segment, field, repetition, component, and subcomponent tree", expanded=False
    ):
        st.caption(
            "HL7 positions start at 1. Expand repetitions, components, and subcomponents; values remain encoded."
        )
        st.json({segment.label: segment_tree(segment, inspection.encoding)}, expanded=2)


def validation_view(report: ValidationReport | None) -> None:
    st.subheader("Validation report")
    st.caption("Selected checks for admission and patient laboratory workflows in HL7 v2.5.1.")
    if not report:
        st.info("Run validation on the active message to see issues and coverage.")
        return
    if report.errors:
        st.error(
            "1 error needs attention."
            if report.errors == 1
            else f"{report.errors} errors need attention."
        )
    elif not report.complete:
        st.warning(
            "Validation coverage is limited. A clean issue list does not establish a passing result."
        )
    elif report.warnings:
        st.warning("No errors found. Review the advisory warnings below.")
    else:
        st.success("No issues found in the implemented checks.")
    with st.expander("Coverage and rule execution", expanded=not report.complete):
        st.write(f"Profile: {report.profile} · Definition: {PROFILE_VERSION}")
        st.write("Checked rule families: " + (", ".join(report.checked_rules) or "None"))
        for note in report.coverage_notes:
            st.text("• " + note)
        st.caption(
            "Scope is limited even when all selected checks run: no clinical, terminology, transport, or complete standard conformance certification."
        )
    left, right = st.columns([1, 2])
    severity = left.selectbox("Severity", ["All", "Error", "Warning"], key="severity")
    query = right.text_input(
        "Find an issue", placeholder="Rule, location, or explanation", key="issue_query"
    )
    issues = [
        issue
        for issue in report.issues
        if (severity == "All" or issue.severity == severity)
        and query.casefold() in f"{issue.rule} {issue.location} {issue.explanation}".casefold()
    ]
    with st.container(border=True, key="issues_panel"):
        if not issues:
            st.write(
                "No issues match the current filters."
                if report.issues
                else "No issues were reported. Check coverage above."
            )
        for issue in issues:
            badge = "badge-error" if issue.severity == "Error" else "badge-warning"
            st.html(
                f'<article class="issue"><div class="issue-header"><span class="badge {badge}">{issue.severity}</span>'
                f'<span class="issue-location">{escape(issue.location)}</span></div>'
                f'<p>{escape(issue.explanation)}</p><p class="correction"><strong>Next step:</strong> {escape(issue.correction)}</p>'
                f'<div class="issue-meta">{escape(issue.rule)} · {escape(issue.basis)}</div></article>'
            )
    with st.container(horizontal=True):
        st.download_button(
            "Download JSON report",
            report.to_json(),
            "hl7-validation-report.json",
            "application/json",
        )
        st.download_button(
            "Download CSV report", report.to_csv(), "hl7-validation-report.csv", "text/csv"
        )
    st.caption(
        "Downloads include the full report, regardless of display filters. Reports do not include the raw message."
    )


def guide_view() -> None:
    st.subheader("Troubleshooting guide")
    st.caption(
        "Worked examples use synthetic values. Confirm the sender's specification before changing an interface."
    )
    examples = [
        (
            "Patient identifier missing",
            "PID-3 is empty or contains only assigning-authority metadata.",
            "Without the identifier itself, an otherwise readable message may not identify the intended patient. Supply the identifier in its first component; check the receiver's assigning-authority requirements.",
        ),
        (
            "Timestamp looks numeric but is impossible",
            "EVN-2 contains 20260230120000.",
            "February 30 is not a real date. Validate calendar values as well as digit count. A year-only date can be legitimate where the field permits reduced precision.",
        ),
        (
            "Result datatype does not fit its value",
            "OBX-2 is NM, while OBX-5 contains positive.",
            "NM declares a number. Confirm whether the sender intended a numeric, text, or coded observation. Do not replace the result just to make validation pass.",
        ),
        (
            "Laboratory order segments are reversed",
            "An OBR appears before the first ORC in an ORM-O01 order.",
            "Our patient laboratory profile expects ORC before OBR. Check each order group separately; repeated groups must remain valid.",
        ),
        (
            "Empty and explicit null differ",
            'An empty field is ||; explicit null is |""|.',
            "Preserve the distinction. Explicit null can ask a receiving system to clear a value, subject to the interface agreement. It is not a substitute for a required identifier.",
        ),
    ]
    for title, example, explanation in examples:
        with st.expander(title):
            st.code(example, language=None, wrap_lines=True)
            st.write(explanation)
    with st.container(border=True, key="profiles_panel"):
        st.markdown("### Supported profiles")
        st.write(
            "ADT-A01 admission: MSH, EVN, PID, PV1. ORM-O01 patient laboratory order: MSH, PID, ORC, OBR. ORU-R01 patient laboratory result: MSH, PID, OBR, OBX."
        )
        st.write(
            "The laboratory profiles narrow the use case; their required segments are not universal requirements for every ORM or ORU message. OBX value checks cover NM, ST, TX, CE, and CWE. Other types and additional segments remain visible with limited-coverage notices."
        )
        st.write(
            "One UTF-8, unframed ER7 message per input. Limits: 1 MB, 1,000 segments, and 20,000 separator characters. Escape sequences are preserved rather than decoded. Dates are checked only in documented fields."
        )
        st.write(
            "Use synthetic or de-identified data. Input is processed on the server, held in the current session, and not deliberately saved or logged by this application. Reset clears the workspace; closing the session ends access to it."
        )
