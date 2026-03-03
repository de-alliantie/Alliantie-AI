import os
from pathlib import Path

import streamlit as st
from helpers_webapp import set_styling

set_styling()
text = (Path(__file__).parent / "informatie_en_privacy.md").read_text()
text = text.format(OTAP=os.environ.get("OTAP", "no env"), tag=os.environ.get("BUILD_TAG", "no tag"))
st.write(text)
