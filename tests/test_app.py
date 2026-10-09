from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.cases import sample

APP = Path(__file__).resolve().parents[1] / "app.py"


def start() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=15).run()


def click_label(app: AppTest, label: str) -> AppTest:
    return next(button for button in app.button if button.label == label).click().run()


def test_baseline_validation_and_reset() -> None:
    app = start()
    assert not app.exception
    click_label(app, "Run validation")
    assert not app.exception and app.success
    assert app.session_state["navigation"] == "Validate"
    click_label(app, "Reset workspace")
    assert app.session_state["active_text"] == "" and not app.exception
    assert next(button for button in app.button if button.label == "Run validation").disabled


def test_samples_and_editor_invalidate_report() -> None:
    app = start()
    app.selectbox(key="sample_index").set_value(5).run()
    click_label(app, "Load synthetic sample")
    assert "positive" in app.session_state["active_text"]
    click_label(app, "Run validation")
    assert app.session_state["report"].errors == 1 and not app.exception
    app.session_state["navigation"] = "Message"
    app.run()
    assert app.selectbox(key="sample_index").value == 5
    app.text_area(key="editor").set_value(sample("adt_a01_baseline")).run()
    assert "report" not in app.session_state and not app.exception
    click_label(app, "Run validation")
    assert app.session_state["report"].errors == 0


def test_views_and_issue_filters() -> None:
    app = start()
    app.session_state["navigation"] = "Inspect"
    app.run()
    app.selectbox(key="segment_index").set_value(2).run()
    assert app.code[0].value.startswith("PID") and not app.exception
    app.session_state["navigation"] = "Guide"
    app.run()
    assert len(app.expander) == 5 and not app.exception
    app.session_state["navigation"] = "Message"
    app.run()
    app.text_area(key="editor").set_value(sample("adt_a01_broken")).run()
    click_label(app, "Run validation")
    app.text_input(key="issue_query").set_value("does not exist").run()
    assert any("No issues match" in text.value for text in app.markdown)
    assert app.session_state["report"].errors == 2 and not app.exception


def test_malformed_input_is_explained() -> None:
    app = start()
    app.text_area(key="editor").set_value("MSH|").run()
    click_label(app, "Run validation")
    assert app.error and not app.exception
    assert not app.session_state["report"].complete


def test_validation_context_and_plural_severity_labels() -> None:
    app = start()
    app.selectbox(key="sample_index").set_value(2).run()
    click_label(app, "Load synthetic sample")
    click_label(app, "Run validation")
    assert any("ORU-R01 patient laboratory results" in caption.value for caption in app.caption)
    assert not any("admission" in caption.value for caption in app.caption)
    assert app.selectbox(key="severity").options == ["All", "Errors", "Warnings"]
    app.selectbox(key="severity").set_value("Warning").run()
    click_label(app, "Reset workspace")
    app.selectbox(key="sample_index").set_value(0).run()
    click_label(app, "Load synthetic sample")
    click_label(app, "Run validation")
    assert any("ADT-A01 admission messages" in caption.value for caption in app.caption)
    assert not app.exception
