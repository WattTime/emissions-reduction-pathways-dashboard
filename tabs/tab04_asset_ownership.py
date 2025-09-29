import streamlit as st
import duckdb
import re
import pandas as pd
from config import CONFIG
from utils.utils import *
from utils.queries import *


def show_ownership_module():
    st.markdown(
        """
        <style>
        /* Hide the sidebar completely */
        section[data-testid="stSidebar"] {
            display: none;
        }
        /* Hide the sidebar collapse/expand arrow */
        [data-testid="collapsedControl"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    ## start here