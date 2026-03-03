"""Statistics are present on the datalake, they are stored as a separate .json file for each chat.

When the statistics page is loaded, we check if there is a local statistics file present for the current date:
- If there is no statistics file present, a new one will be created.
- If there already is a statistics file present,
  it will retrieve only new statistics (up to yesterday) and append these to the existing file.

Once the statistics are present/updated, they are loaded and aggregated by date.
The aggregated data is visualized.
"""
import os
from datetime import datetime

import pandas as pd
import streamlit as st
from helpers_webapp import set_styling

from shared.utils import update_usage_statistics

set_styling()

st.markdown("# Statistieken")


stats_updating_placeholder = st.empty()


def stats_are_up_to_date() -> bool:
    """Checks if the usage_statistics file has the most recent data."""
    if os.path.exists("data/usage_statistics"):
        files = [
            f for f in os.listdir("data/usage_statistics/") if os.path.isfile(os.path.join("data/usage_statistics/", f))
        ]
        for file in files:
            date_last_update = datetime.strptime(file.split("_")[0], "%Y%m%d")
            if (datetime.now().date()) == date_last_update.date():
                return True
        return False
    else:
        return False


def load_stats() -> pd.DataFrame | None:
    """Loads the most recent usage statistics file."""
    print("Loading stats...")
    if os.path.exists("data/usage_statistics"):
        files = [
            f for f in os.listdir("data/usage_statistics/") if os.path.isfile(os.path.join("data/usage_statistics/", f))
        ]
        for file in files:
            df = pd.read_parquet(os.path.join("data/usage_statistics/", file))
            return df


if "stats" not in st.session_state:
    if not stats_are_up_to_date():
        with stats_updating_placeholder.container():
            with st.spinner("Statistieken worden bijgewerkt, dit kan enkele ogenblikken duren..."):
                update_usage_statistics()
    st.session_state["stats"] = load_stats()
    st.session_state["stats"]["timestamp_last_chat"] = pd.to_datetime(st.session_state["stats"]["timestamp_last_chat"])

if "from_date" not in st.session_state:
    st.session_state["from_date"] = None

if "to_date" not in st.session_state:
    st.session_state["to_date"] = None


# Aggregate data by day, for each day show the num_rows, unique num_user
if not st.session_state["stats"].empty:

    # Extract date from timestamp
    st.session_state["stats"]["date"] = pd.to_datetime(st.session_state["stats"]["timestamp_last_chat"]).dt.date

    # First and last date in data
    st.session_state["first_date"] = st.session_state["stats"]["date"].min()
    st.session_state["last_date"] = st.session_state["stats"]["date"].max()

    # Aggregate per day
    st.session_state.agg_df = (
        st.session_state["stats"]
        .groupby("date")
        .agg(
            Gebruikers=("hashed_user", "nunique"),
            Berichten=("timestamp_last_chat", "count"),
        )
        .reset_index()
    )

    # Set date as index for plotting
    st.session_state["agg_df"].set_index("date", inplace=True)

    stats_time_filtered = st.session_state["stats"]

    # Filter user metrics based on selected date range
    if st.session_state["from_date"] is not None:
        st.session_state["agg_df"] = st.session_state.agg_df[
            st.session_state.agg_df.index >= st.session_state.from_date
        ]

    if st.session_state["to_date"] is not None:
        st.session_state["agg_df"] = st.session_state.agg_df[st.session_state.agg_df.index <= st.session_state.to_date]

    if st.session_state["from_date"] is not None and st.session_state["to_date"] is not None:
        stats_time_filtered = st.session_state["stats"][
            (st.session_state["stats"]["timestamp_last_chat"].dt.date <= st.session_state["to_date"])
            & (st.session_state["stats"]["timestamp_last_chat"].dt.date >= st.session_state["from_date"])
        ]
        unique_users_over_time = stats_time_filtered["hashed_user"].nunique()
        st.session_state.unique_users_over_time = unique_users_over_time
    else:
        unique_users_over_time = st.session_state["stats"]["hashed_user"].nunique()
        st.session_state.unique_users_over_time = unique_users_over_time

    # Show line chart
    st.line_chart(data=st.session_state["agg_df"], color=[(13, 93, 191, 0.7), (253, 46, 48, 0.7)])

    # Show overall stats
    col1_metric, col2_metric = st.columns(2)

    col1_metric.metric(label="Berichten", value=st.session_state["agg_df"]["Berichten"].sum())

    col2_metric.metric(label="Gebruikers", value=st.session_state.unique_users_over_time)


col1_date, col2_date = st.columns(2)

from_date = col1_date.date_input(
    label="Begindatum",
    min_value=st.session_state["first_date"],
    max_value=st.session_state["last_date"],
    format="YYYY/MM/DD",
    key="from_date",
)

to_date = col2_date.date_input(
    label="Eindatum", min_value=st.session_state["first_date"], max_value=st.session_state["last_date"], key="to_date"
)
