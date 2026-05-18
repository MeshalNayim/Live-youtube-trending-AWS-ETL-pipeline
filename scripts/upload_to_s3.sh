#!/bin/bash

BUCKET="yt-data-pipeline-brozne-ap-south-1-dev"
CSV_PREFIX="youtube/raw_statistics"
JSON_PREFIX="youtube/raw_statistics_ref"
DATA_DIR="$(dirname "$0")/../data"

declare -A csv_regions=(
    ["CAvideos.csv"]="ca"
    ["USvideos.csv"]="us"
    ["GBvideos.csv"]="gb"
    ["DEvideos.csv"]="de"
    ["FRvideos.csv"]="fr"
    ["INvideos.csv"]="in"
    ["JPvideos.csv"]="jp"
    ["KRvideos.csv"]="kr"
    ["MXvideos.csv"]="mx"
    ["RUvideos.csv"]="ru"
)

declare -A json_regions=(
    ["CA_category_id.json"]="ca"
    ["US_category_id.json"]="us"
    ["GB_category_id.json"]="gb"
    ["DE_category_id.json"]="de"
    ["FR_category_id.json"]="fr"
    ["IN_category_id.json"]="in"
    ["JP_category_id.json"]="jp"
    ["KR_category_id.json"]="kr"
    ["MX_category_id.json"]="mx"
    ["RU_category_id.json"]="ru"
)

echo "--- Uploading CSVs ---"
for filename in "${!csv_regions[@]}"; do
    region="${csv_regions[$filename]}"
    local_path="$DATA_DIR/$filename"

    if [ ! -f "$local_path" ]; then
        echo "SKIP  $filename (not found)"
        continue
    fi

    echo "Uploading $filename -> s3://$BUCKET/$CSV_PREFIX/region=$region/$filename"
    aws s3 cp "$local_path" "s3://$BUCKET/$CSV_PREFIX/region=$region/$filename"
done

echo ""
echo "--- Uploading JSON category files ---"
for filename in "${!json_regions[@]}"; do
    region="${json_regions[$filename]}"
    local_path="$DATA_DIR/$filename"

    if [ ! -f "$local_path" ]; then
        echo "SKIP  $filename (not found)"
        continue
    fi

    echo "Uploading $filename -> s3://$BUCKET/$JSON_PREFIX/region=$region/$filename"
    aws s3 cp "$local_path" "s3://$BUCKET/$JSON_PREFIX/region=$region/$filename"
done

echo ""
echo "All uploads complete."
