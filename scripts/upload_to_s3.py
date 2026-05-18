import boto3
import os

BUCKET = "yt-data-pipeline-bronze-meshal"
CSV_PREFIX = "youtube/raw_statistics"
JSON_PREFIX = "youtube/raw_statistics_ref"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

csv_map = {
    "CAvideos.csv": "ca",
    "USvideos.csv": "us",
    "GBvideos.csv": "gb",
    "DEvideos.csv": "de",
    "FRvideos.csv": "fr",
    "INvideos.csv": "in",
    "JPvideos.csv": "jp",
    "KRvideos.csv": "kr",
    "MXvideos.csv": "mx",
    "RUvideos.csv": "ru",
}

json_map = {
    "CA_category_id.json": "ca",
    "US_category_id.json": "us",
    "GB_category_id.json": "gb",
    "DE_category_id.json": "de",
    "FR_category_id.json": "fr",
    "IN_category_id.json": "in",
    "JP_category_id.json": "jp",
    "KR_category_id.json": "kr",
    "MX_category_id.json": "mx",
    "RU_category_id.json": "ru",
}

s3 = boto3.client("s3")

def upload_files(file_map, s3_prefix):
    for filename, region in file_map.items():
        local_path = os.path.join(DATA_DIR, filename)
        s3_key = f"{s3_prefix}/region={region}/{filename}"

        if not os.path.exists(local_path):
            print(f"SKIP  {filename} (not found)")
            continue

        print(f"Uploading {filename} -> s3://{BUCKET}/{s3_key}")
        s3.upload_file(local_path, BUCKET, s3_key)
        print(f"  Done")

print("--- Uploading CSVs ---")
upload_files(csv_map, CSV_PREFIX)

print("\n--- Uploading JSON category files ---")
upload_files(json_map, JSON_PREFIX)

print("\nAll uploads complete.")
