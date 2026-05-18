# YouTube Trending Analytics, AWS Data Pipeline

🔴 **Live dashboard:** <https://live-youtube-trending-aws-etl-pipeline.streamlit.app/>

A working data pipeline I built on AWS to learn the medallion architecture end to end. An EventBridge schedule kicks off a Step Functions execution every few hours. The first state invokes a Lambda that hits the YouTube Data API and pulls trending video stats plus category mappings for 10 regions, landing raw JSON in a Bronze S3 bucket. From there, two transforms run in parallel: a Glue Spark job reads Bronze, enforces schema, deduplicates, and adds derived metrics like engagement rate before writing Parquet to Silver, while a smaller Lambda processes the category reference JSON into Silver Parquet on the same execution.

After Silver is built, a data quality Lambda runs about 14 checks across both tables using Athena. If anything fails, the pipeline routes to an SNS alert and stops before Gold. If everything passes, a second Glue Spark job aggregates Silver into three Gold tables: daily trending summaries per region, channel rankings, and category breakdowns over time.

The whole flow runs through Step Functions with parallel branches for the transforms, scoped retries on transient errors, and explicit failure paths. Gold tables are registered in the Glue Catalog and queried by a Streamlit dashboard that runs Athena queries through awswrangler and renders Plotly charts. The dashboard ships with a Dockerfile and docker compose for local runs.


## Step-Function

<img width="1088" height="637" alt="image" src="https://github.com/user-attachments/assets/b963924b-060a-4ca0-8e54-89d11dd80c13" />


## Architecture

```
┌──────────────────┐
│  YouTube Data    │
│      API v3      │
└────────┬─────────┘
         │ scheduled (EventBridge cron)
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    AWS Step Functions                       │
│                                                             │
│  ┌──────────────┐    ┌──────────────────────────────────┐   │
│  │ IngestLambda │──▶│ ParallelTransforms                 │   │
│  │ (10 regions) │    │  ├─ TransformReferenceData λ      │   │
│  └──────────────┘    │  └─ Glue Spark: Bronze → Silver  │   │
│                       └──────────────┬──────────────────┘    │
│                                      ▼                       │
│                       ┌────────────────────────────┐         │
│                       │ DataQualityCheck Lambda    │         │
│                       │ 14 checks across tables    │         │
│                       └──────────────┬─────────────┘         │
│                                      ▼                       │
│                            ┌──── Choice ────┐                │
│                       pass │                │ fail           │
│                            ▼                ▼                │
│              ┌───────────────────────┐  ┌────────────────┐   │
│              │ Glue Spark:           │  │ SNS Alert      │   │
│              │ Silver → Gold         │  │ + Fail state   │   │
│              └───────────────────────┘  └────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐        ┌──────────────────┐
│   S3 Data Lake   │◀──────│   Glue Catalog   │
│                  │        │                  │
│ • Bronze (JSON)  │        │ • bronze db      │
│ • Silver (Parq.) │        │ • silver db      │
│ • Gold (Parq.)   │        │ • gold db        │
└────────┬─────────┘        └──────────────────┘
         │                           ▲
         │                           │
         └──────▶  Athena  ◀─────────┘
                    │
                    ▼
            ┌──────────────────┐
            │ Streamlit App    │
            │ (Plotly charts)  │
            └──────────────────┘
```

## Stack

| Layer | Tooling |
|---|---|
| **Scheduling** | Amazon EventBridge (cron rule triggers the Step Function) |
| **Orchestration** | AWS Step Functions |
| **Ingestion** | AWS Lambda (Python) + YouTube Data API v3 |
| **Storage** | S3 (Parquet + Snappy in Silver/Gold, JSON in Bronze) |
| **Processing** | AWS Glue (PySpark) + Lambda (awswrangler/pandas) |
| **Catalog** | AWS Glue Data Catalog |
| **Query** | Amazon Athena |
| **Alerting** | Amazon SNS |
| **Visualization** | Streamlit + Plotly |
| **Container** | Docker |

## Project structure

```
yt_project/
├── lambda/
│   ├── lambda_ytapi_ingestion        # Pulls trending videos + categories from YT API → Bronze S3
│   └── lambda_json_to_parquet        # S3 event → cleans category JSON → Silver Parquet
├── spark_jobs/
│   ├── bronze_to_silver.py           # Glue PySpark: cleanse stats, dedup, derive metrics
│   └── silver_to_gold.py             # Glue PySpark: aggregate to 3 analytics tables
├── data_quality/
│   └── dq_lambda.py                  # 5 categories × N columns of DQ checks via Athena
├── step_function/
│   └── orchestration.json            # ASL state machine: ingest → transform → DQ → gold
├── streamlit/                        # Interactive dashboard over Gold layer
│   ├── app.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── README.md
├── scripts/                          # One-off helpers
└── data/                             # Local Kaggle CSVs / JSONs (gitignored)
```

## Medallion layers

| Layer | Bucket | Format | Grain | Created by |
|---|---|---|---|---|
| **Bronze** | `yt-data-pipeline-bronze-meshal` | JSON (raw API response) | Per region, per ingestion run | Ingestion Lambda |
| **Silver** | `yt-data-pipeline-silver-meshal` | Parquet + Snappy, partitioned by region | One row per (video, region, date) | Glue Spark + JSON→Parquet Lambda |
| **Gold** | `yt-data-pipeline-gold-meshal` | Parquet + Snappy, partitioned by region | Aggregated for analytics | Glue Spark |

### Gold tables

| Table | Grain | Used for |
|---|---|---|
| `trending_analytics` | one row per (region, date) | KPIs, daily trend lines |
| `category_analytics` | one row per (region, date, category) | Category breakdowns, share-of-views |
| `channel_analytics` | one row per (region, channel) | Channel leaderboards |

## Data quality framework

Runs after every Silver build, before Gold. Returns `quality_passed: false` if any check fails, which triggers a Step Functions `Choice` state to skip the Gold transform and fire an SNS alert.

| Check | What it validates |
|---|---|
| `row_count` | Table has ≥ N rows (configurable) |
| `null_pct` | Critical columns have < 5% nulls |
| `schema` | Expected columns are present |
| `value_range` | Numeric fields within sane bounds (no negative views, no `> 50B`) |
| `freshness` | Latest record is within 48h |

## Running the dashboard

A live version is hosted at <https://live-youtube-trending-aws-etl-pipeline.streamlit.app/>. To run it yourself, the code lives in [`streamlit/`](streamlit/) and has its own README with detailed setup. TL;DR:

**Local with Python:**

```powershell
cd streamlit
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

**Local with Docker:**

```powershell
cd streamlit
docker compose up --build
```

Both open the dashboard at <http://localhost:8501>. AWS credentials are read from your standard boto3 chain (`~/.aws/credentials`, env vars, or IAM role).

### Caching

Every chart on the dashboard is backed by an Athena query, and Athena charges per terabyte scanned. To keep cost and load times sane, the app caches query results in memory using Streamlit's `@st.cache_data` decorator:

| What is cached | TTL | Reason |
|---|---|---|
| Each tab's main query result | 10 minutes | The Gold layer only refreshes when the Step Function runs, so frequent re-queries on the same filter combo would be wasted scans. |
| Region list and date bounds | 1 hour | These change only when a new region is ingested or a new day's data lands, both rare events. |

The cache key is the SQL string itself. Changing region selection or date range produces a different SQL, which misses the cache and triggers a fresh Athena query. Selecting the same filters again within 10 minutes returns the cached pandas DataFrame instantly with no Athena call.

If you need to force fresh data (for example right after the Step Function finishes a new run), use the **🔄 Clear cache** button in the sidebar. This calls `st.cache_data.clear()` and reruns the app, so the next query hits Athena directly.

In practice this means the dashboard costs almost nothing to host. A typical day with a few dozen visitors triggers maybe 20 to 30 Athena queries against compressed Parquet, well within the AWS free tier.

## AWS resources required

If reproducing in your own account, you'll need (all in `us-west-2`):

- 3 S3 buckets: Bronze, Silver, Gold
- 1 Athena results bucket + workgroup with `EnforceWorkGroupConfiguration=true`
- 3 Glue databases: `yt_pipeline_bronze`, `yt_pipeline_silver`, `yt_pipeline_gold`
- 1 Glue crawler on Bronze
- 2 Glue Spark jobs (`bronze_to_silver`, `silver_to_gold`)
- 3 Lambda functions (ingestion, json to parquet, DQ check)
- 1 Step Functions state machine
- 1 EventBridge rule (cron schedule that starts the Step Function)
- 1 SNS topic for alerts
- IAM roles for each component with scoped permissions

A YouTube Data API v3 key is required for ingestion.



## License

MIT
