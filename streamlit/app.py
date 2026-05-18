"""
YouTube Trending Analytics — Streamlit Dashboard
─────────────────────────────────────────────────
Queries the Gold layer (Athena over Parquet in S3) and renders interactive charts.

Tables consumed:
    yt_pipeline_gold.trending_analytics   — daily aggregates per region
    yt_pipeline_gold.channel_analytics    — channel performance per region
    yt_pipeline_gold.category_analytics   — category breakdown per region/day

Run locally:
    streamlit run app.py

AWS credentials are read from the standard boto3 chain
(env vars, ~/.aws/credentials, IAM role).
"""

import os
from datetime import date

import awswrangler as wr
import pandas as pd
import plotly.express as px
import streamlit as st

# ── Config ───────────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
GOLD_DB = os.environ.get("GOLD_DB", "yt_pipeline_gold")
ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "primary")

os.environ["AWS_DEFAULT_REGION"] = AWS_REGION

st.set_page_config(
    page_title="YT Trending Analytics",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Query helpers ────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Querying Athena…")
def run_query(sql: str) -> pd.DataFrame:
    return wr.athena.read_sql_query(
        sql=sql,
        database=GOLD_DB,
        workgroup=ATHENA_WORKGROUP,
        ctas_approach=False,
    )


@st.cache_data(ttl=3600)
def get_regions() -> list[str]:
    df = run_query("SELECT DISTINCT region FROM trending_analytics ORDER BY region")
    return df["region"].tolist()


@st.cache_data(ttl=3600)
def get_date_bounds() -> tuple[date, date]:
    df = run_query(
        "SELECT MIN(trending_date_parsed) AS min_d, MAX(trending_date_parsed) AS max_d "
        "FROM trending_analytics"
    )
    return df["min_d"].iloc[0], df["max_d"].iloc[0]


# ── Sidebar filters ──────────────────────────────────────────────────────────
st.sidebar.title("📺 YT Analytics")
st.sidebar.caption(f"Gold DB: `{GOLD_DB}` · Region: `{AWS_REGION}`")

try:
    all_regions = get_regions()
    min_date, max_date = get_date_bounds()
except Exception as e:
    st.error(f"Could not connect to Athena. Check AWS credentials and IAM permissions.\n\n{e}")
    st.stop()

selected_regions = st.sidebar.multiselect(
    "Regions",
    options=all_regions,
    default=all_regions[:3] if len(all_regions) >= 3 else all_regions,
)

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

if len(date_range) != 2:
    st.warning("Pick a start and end date.")
    st.stop()

start_date, end_date = date_range

if not selected_regions:
    st.warning("Pick at least one region.")
    st.stop()

regions_sql = ", ".join(f"'{r}'" for r in selected_regions)
date_filter = (
    f"trending_date_parsed BETWEEN DATE '{start_date}' AND DATE '{end_date}'"
)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Clear cache"):
    st.cache_data.clear()
    st.rerun()


# ── Main page ────────────────────────────────────────────────────────────────
st.title("YouTube Trending Analytics")
st.caption(
    f"**{len(selected_regions)} region(s)** · "
    f"**{start_date} → {end_date}** · "
    f"data refreshed via Glue Spark job, served from Athena over Parquet."
)

tab1, tab2, tab3 = st.tabs(["📊 Trending Overview", "🎬 Categories", "📡 Channels"])


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Trending Overview
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    df = run_query(f"""
        SELECT region, trending_date_parsed AS date,
               total_videos, total_views, total_likes, total_comments,
               avg_views_per_video, avg_engagement_rate,
               unique_channels, unique_categories
        FROM trending_analytics
        WHERE region IN ({regions_sql})
          AND {date_filter}
        ORDER BY date, region
    """)

    if df.empty:
        st.info("No data for the selected filters.")
    else:
        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Views", f"{df['total_views'].sum():,.0f}")
        k2.metric("Total Videos", f"{df['total_videos'].sum():,.0f}")
        k3.metric("Total Likes", f"{df['total_likes'].sum():,.0f}")
        k4.metric("Avg Engagement %", f"{df['avg_engagement_rate'].mean():.2f}")

        st.subheader("Daily Views by Region")
        fig = px.line(
            df,
            x="date",
            y="total_views",
            color="region",
            markers=True,
            labels={"total_views": "Total Views", "date": "Date"},
        )
        fig.update_layout(height=420, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Avg Engagement Rate by Region")
            agg = (
                df.groupby("region", as_index=False)["avg_engagement_rate"]
                .mean()
                .sort_values("avg_engagement_rate", ascending=False)
            )
            fig2 = px.bar(
                agg,
                x="region",
                y="avg_engagement_rate",
                color="region",
                labels={"avg_engagement_rate": "Avg Engagement %"},
            )
            fig2.update_layout(height=380, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        with c2:
            st.subheader("Unique Channels per Region")
            agg2 = (
                df.groupby("region", as_index=False)["unique_channels"]
                .sum()
                .sort_values("unique_channels", ascending=False)
            )
            fig3 = px.bar(
                agg2,
                x="region",
                y="unique_channels",
                color="region",
                labels={"unique_channels": "Unique Channels"},
            )
            fig3.update_layout(height=380, showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)

        with st.expander("🔍 Raw data"):
            st.dataframe(df, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Categories
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    df = run_query(f"""
        SELECT region, trending_date_parsed AS date,
               category_name, category_id,
               video_count, total_views, total_likes,
               avg_engagement_rate, unique_channels, view_share_pct
        FROM category_analytics
        WHERE region IN ({regions_sql})
          AND {date_filter}
        ORDER BY date, total_views DESC
    """)

    if df.empty:
        st.info("No category data for the selected filters.")
    else:
        st.subheader("Top Categories by Total Views")
        top_cats = (
            df.groupby("category_name", as_index=False)["total_views"]
            .sum()
            .sort_values("total_views", ascending=False)
            .head(15)
        )
        fig = px.bar(
            top_cats,
            x="total_views",
            y="category_name",
            orientation="h",
            color="total_views",
            color_continuous_scale="Viridis",
            labels={"total_views": "Total Views", "category_name": "Category"},
        )
        fig.update_layout(height=500, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Category Share of Views — Region × Category Heatmap")
        share = (
            df.groupby(["region", "category_name"], as_index=False)["total_views"]
            .sum()
        )
        share["share_pct"] = (
            share.groupby("region")["total_views"].transform(lambda s: s / s.sum() * 100)
        )
        pivot = share.pivot(index="category_name", columns="region", values="share_pct").fillna(0)
        fig2 = px.imshow(
            pivot,
            color_continuous_scale="YlOrRd",
            aspect="auto",
            labels={"color": "Share %"},
        )
        fig2.update_layout(height=600)
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Engagement by Category")
        eng = (
            df.groupby("category_name", as_index=False)["avg_engagement_rate"]
            .mean()
            .sort_values("avg_engagement_rate", ascending=False)
            .head(15)
        )
        fig3 = px.bar(
            eng,
            x="category_name",
            y="avg_engagement_rate",
            color="avg_engagement_rate",
            color_continuous_scale="Plasma",
            labels={"avg_engagement_rate": "Avg Engagement %", "category_name": "Category"},
        )
        fig3.update_layout(height=420, xaxis_tickangle=-30)
        st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Channels
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    top_n = st.slider("Top N channels per region", 5, 50, 20, step=5)

    df = run_query(f"""
        SELECT region, channel_title, total_videos, total_views,
               total_likes, avg_views_per_video, avg_engagement_rate,
               peak_views, times_trending, first_trending, last_trending,
               rank_in_region
        FROM channel_analytics
        WHERE region IN ({regions_sql})
          AND rank_in_region <= {top_n}
        ORDER BY region, rank_in_region
    """)

    if df.empty:
        st.info("No channel data for the selected filters.")
    else:
        st.subheader(f"Top {top_n} Channels per Region")
        for region in selected_regions:
            with st.expander(f"🌍 {region.upper()} — top channels", expanded=(region == selected_regions[0])):
                region_df = df[df["region"] == region].head(top_n)
                if region_df.empty:
                    st.caption("No data.")
                    continue
                fig = px.bar(
                    region_df,
                    x="total_views",
                    y="channel_title",
                    orientation="h",
                    color="avg_engagement_rate",
                    color_continuous_scale="Turbo",
                    hover_data=["total_videos", "times_trending", "peak_views"],
                    labels={
                        "total_views": "Total Views",
                        "channel_title": "Channel",
                        "avg_engagement_rate": "Engagement %",
                    },
                )
                fig.update_layout(height=max(300, 24 * len(region_df)),
                                  yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, use_container_width=True)

        st.subheader("Channel Leaderboard")
        st.dataframe(
            df[[
                "region", "rank_in_region", "channel_title",
                "total_views", "total_videos", "times_trending",
                "avg_engagement_rate", "peak_views",
            ]].rename(columns={"rank_in_region": "rank"}),
            use_container_width=True,
            hide_index=True,
        )


# ── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Data pipeline: YouTube API → Lambda → S3 (Bronze) → Glue Spark "
    "(Silver / Gold) → Athena → Streamlit. Charts auto-refresh every 10 min."
)
