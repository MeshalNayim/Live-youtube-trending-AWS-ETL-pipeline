# YouTube Trending Analytics, Streamlit Dashboard

🔴 **Live:** <https://live-youtube-trending-aws-etl-pipeline.streamlit.app/>

Interactive dashboard over the Gold layer of the YT pipeline. Queries Athena directly. No data is loaded into the app. Every chart is computed by Athena scanning Parquet in S3, with results cached in the app for 10 minutes to avoid repeat scans.

## Tables consumed

All in the `yt_pipeline_gold` database (Glue Catalog, us-west-2):

| Table | Grain | Used for |
|---|---|---|
| `trending_analytics` | one row per `(region, date)` | Overview tab — KPIs, daily trend lines |
| `category_analytics` | one row per `(region, date, category)` | Categories tab — top categories, share heatmap |
| `channel_analytics` | one row per `(region, channel)` | Channels tab — leaderboard, per-region top N |

## Prerequisites

1. **Python 3.10+** installed
2. **AWS credentials** configured locally — any of:
   - `aws configure` (writes to `~/.aws/credentials`)
   - Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-west-2`
   - SSO profile: `aws sso login --profile <profile>` + `$env:AWS_PROFILE = "<profile>"`
3. **IAM permissions** for the user/role — same set the DQ Lambda has:
   - `athena:StartQueryExecution`, `athena:GetQueryExecution`, `athena:GetQueryResults`, `athena:GetWorkGroup`
   - `glue:GetDatabase`, `glue:GetTable`, `glue:GetPartitions`
   - `s3:GetObject`, `s3:ListBucket` on the Gold bucket (`yt-data-pipeline-gold-meshal`)
   - `s3:GetObject`, `s3:PutObject` on the Athena results bucket (`yt-athena-q-results`)

## Setup

From this folder:

```powershell
# Create + activate venv (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

## Run

```powershell
streamlit run app.py
```

The dashboard opens at <http://localhost:8501>.

## Configuration (optional)

Override defaults via environment variables before running:

| Variable | Default | What it does |
|---|---|---|
| `AWS_REGION` | `us-west-2` | AWS region for Athena/Glue |
| `GOLD_DB` | `yt_pipeline_gold` | Glue database to query |
| `ATHENA_WORKGROUP` | `primary` | Athena workgroup (must have a results location) |

Example:

```powershell
$env:GOLD_DB = "yt_pipeline_gold_prod"
streamlit run app.py
```

## Caching behaviour

Athena charges per terabyte scanned, and a cold query against partitioned Parquet still takes a couple of seconds. To keep both cost and latency low, the app wraps every query in Streamlit's `@st.cache_data`:

| What is cached | TTL | Why |
|---|---|---|
| Each tab's main query result | 10 minutes | Gold data only changes when the Step Function runs. Re-querying the same filter combo within 10 minutes returns the cached DataFrame with zero Athena cost. |
| Region list and date bounds | 1 hour | These change only when a new region is ingested or a new day's data lands. |

The cache key is the full SQL string. Changing region selection or date range generates different SQL, misses the cache, and triggers a fresh Athena query. Selecting the same filters again returns instantly.

If you need to force fresh data (for example right after a pipeline run completes), click **🔄 Clear cache** in the sidebar. This calls `st.cache_data.clear()` and reruns the app so the next query hits Athena directly.

In practice this keeps hosting costs near zero. A typical day with a few dozen visitors triggers maybe 20 to 30 Athena queries against compressed Parquet, well inside the AWS free tier.

## Deploying to Streamlit Cloud (optional)

1. Push this folder to a GitHub repo.
2. Sign in to <https://streamlit.io/cloud>, "New app", point at `streamlit/app.py`.
3. In **Settings → Secrets**, add your AWS credentials as TOML:
   ```toml
   AWS_ACCESS_KEY_ID = "AKIA…"
   AWS_SECRET_ACCESS_KEY = "…"
   AWS_REGION = "us-west-2"
   ```
4. The app picks them up automatically via the boto3 default credential chain.

⚠️ **Use a read-only IAM user for deployment** — never push long-lived admin credentials. The IAM permissions listed above are sufficient.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Could not connect to Athena` on the sidebar | AWS creds not loaded | Run `aws sts get-caller-identity` to verify; set `AWS_PROFILE` if needed |
| `AccessDenied` on S3 | IAM missing Gold bucket read | Add `s3:GetObject` + `s3:ListBucket` on `yt-data-pipeline-gold-meshal` |
| `TABLE_NOT_FOUND` | Gold layer not built yet | Trigger the Step Function or run the `silver_to_gold` Glue job |
| Charts empty after filter change | No data for that region/date | Widen the date range or pick a different region |
