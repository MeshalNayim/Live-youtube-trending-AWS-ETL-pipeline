# YouTube Trending Analytics — AWS Data Pipeline

End-to-end serverless data pipeline that ingests YouTube trending data from 10 regions, processes it through a Bronze → Silver → Gold medallion architecture on AWS, validates data quality, and exposes the results via an interactive Streamlit dashboard.

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
| **Ingestion** | AWS Lambda (Python) + YouTube Data API v3 |
| **Storage** | S3 (Parquet + Snappy in Silver/Gold, JSON in Bronze) |
| **Processing** | AWS Glue (PySpark) + Lambda (awswrangler/pandas) |
| **Catalog** | AWS Glue Data Catalog |
| **Query** | Amazon Athena |
| **Orchestration** | AWS Step Functions |
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

The dashboard lives in [`streamlit/`](streamlit/) and has its own README with detailed setup. TL;DR:

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

## AWS resources required

If reproducing in your own account, you'll need (all in `us-west-2`):

- 3 S3 buckets: Bronze, Silver, Gold
- 1 Athena results bucket + workgroup with `EnforceWorkGroupConfiguration=true`
- 3 Glue databases: `yt_pipeline_bronze`, `yt_pipeline_silver`, `yt_pipeline_gold`
- 1 Glue crawler on Bronze
- 2 Glue Spark jobs (`bronze_to_silver`, `silver_to_gold`)
- 3 Lambda functions (ingestion, json→parquet, DQ check)
- 1 Step Functions state machine
- 1 SNS topic for alerts
- IAM roles for each component with scoped permissions

A YouTube Data API v3 key is required for ingestion.

## What's deliberately not here yet

- **Infrastructure as Code (Terraform/CDK)** — pipeline is currently console-deployed
- **CI/CD** — Lambdas/Glue scripts are uploaded manually
- **Unit tests** — DQ logic is pure-functional and would test cleanly
- **Secrets Manager** — YouTube API key currently lives in a Lambda env var

## License

MIT
