import streamlit as st

st.set_page_config(page_title="HL7v2 Inspector and Validator", page_icon="🔎", layout="wide")
st.title("HL7v2 Inspector and Validator")
st.caption("A workspace for inspecting healthcare interface messages.")
message = st.text_area("HL7v2 message", height=240)
if message.strip():
    st.code(message, language="text")
else:
    st.info("Paste an HL7v2 message to begin.")
