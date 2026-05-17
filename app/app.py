"""Streamlit entry point for California Sail."""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from app.ui.layout import run


def _page_background(image_url: str) -> None:
    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: linear-gradient(
                rgba(255, 255, 255, 0.55),
                rgba(255, 255, 255, 0.55)
            ), url("{image_url}");
            background-size: cover;
            background-position: center center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }}
        [data-testid="stHeader"] {{
            background: rgba(255, 255, 255, 0.55);
        }}
        section[data-testid="stSidebar"] > div {{
            background-color: rgba(250, 250, 250, 0.94);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


_PAGE_BG_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Golden_Gate_Bridge_and_fog%2C_January_2013.jpg/1280px-Golden_Gate_Bridge_and_fog%2C_January_2013.jpg"

st.set_page_config(
    page_title="California Sail — Forecast",
    page_icon="⛵",
    layout="wide",
)
_page_background(_PAGE_BG_URL)
st.markdown("# ⛵ California Sail")
st.markdown("Select a sailing region and see the next 1–7 days of wind, weather, and sailability forecast.")

run(_project_root / "data" / "sailing_areas.yaml")
