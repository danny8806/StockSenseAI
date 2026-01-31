import streamlit as st
import sqlite3
import pandas as pd
import json
import plotly.express as px

DB_PATH = "news.db"

# -----------------------
# Page Config
# -----------------------
st.set_page_config(
    page_title="StockSenseAI Dashboard",
    layout="wide"
)

st.title("📊 StockSenseAI – News Intelligence Dashboard")
st.caption("AI-powered stock market intelligence from financial news")

# -----------------------
# Database Loader
# -----------------------
@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql("""
    SELECT
        r.source,
        r.headline,
        r.fetched_at,
        l.event_type,
        l.sentiment,
        l.impact_horizon,
        l.suggestion,
        l.confidence,
        l.reasoning,
        l.stocks
    FROM news_raw r
    JOIN news_llm l
    ON r.news_id = l.news_id
    ORDER BY r.fetched_at DESC
    """, conn)

    conn.close()

    df["stocks"] = df["stocks"].apply(
        lambda x: ", ".join(json.loads(x)) if x else ""
    )
    df["fetched_at"] = pd.to_datetime(df["fetched_at"])

    return df

df = load_data()

# -----------------------
# Sidebar Filters
# -----------------------
st.sidebar.header("🔎 Filters")

event_filter = st.sidebar.multiselect(
    "Event Type",
    options=df["event_type"].unique(),
    default=df["event_type"].unique()
)

sentiment_filter = st.sidebar.multiselect(
    "Sentiment",
    options=df["sentiment"].unique(),
    default=df["sentiment"].unique()
)

suggestion_filter = st.sidebar.multiselect(
    "Suggestion",
    options=df["suggestion"].unique(),
    default=df["suggestion"].unique()
)

confidence_threshold = st.sidebar.slider(
    "Minimum Confidence",
    0.0, 1.0, 0.5
)

filtered = df[
    (df["event_type"].isin(event_filter)) &
    (df["sentiment"].isin(sentiment_filter)) &
    (df["suggestion"].isin(suggestion_filter)) &
    (df["confidence"] >= confidence_threshold)
]

# -----------------------
# KPIs
# -----------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric("📰 Total Signals", len(filtered))
col2.metric("📈 BUY Signals", (filtered["suggestion"] == "BUY").sum())
col3.metric("📉 SELL Signals", (filtered["suggestion"] == "SELL").sum())
col4.metric("🧠 Avg Confidence", round(filtered["confidence"].mean(), 2))

# -----------------------
# Charts
# -----------------------
st.subheader("📊 Signal Distribution")

c1, c2 = st.columns(2)

with c1:
    fig = px.histogram(
        filtered,
        x="event_type",
        color="sentiment",
        title="Event Type vs Sentiment",
        barmode="group"
    )
    st.plotly_chart(fig, use_container_width=True)

with c2:
    fig = px.pie(
        filtered,
        names="suggestion",
        title="BUY / SELL / HOLD Split"
    )
    st.plotly_chart(fig, use_container_width=True)

# -----------------------
# News Table
# -----------------------
st.subheader("🧠 Intelligence Feed")

for _, row in filtered.iterrows():
    with st.expander(row["headline"]):
        st.markdown(f"""
**Source:** {row['source']}  
**Stocks:** {row['stocks']}  
**Event Type:** `{row['event_type']}`  
**Sentiment:** `{row['sentiment']}`  
**Impact Horizon:** `{row['impact_horizon']}`  
**Suggestion:** **{row['suggestion']}**  
**Confidence:** `{row['confidence']}`  

**Why:**  
{row['reasoning']}
        """)

