import os
import json
import boto3
import psycopg2
from datetime import datetime

# --- Config --- #
bucket = "aicp-claims-data"
prefix = "processed/fraud-predicted-claims-data/"
claim_id = os.environ.get("CLAIM_ID")  # Passed via ECS override or CLI

# Redshift connection
redshift_host = "redshift-cluster-2.cax5lwhmspd1.us-east-1.redshift.amazonaws.com"
redshift_user = "redshift_admin"
redshift_pass = "347634M-ulla7710"
redshift_db = "dev"
redshift_port = 5439

# --- Find Matching File in S3 --- #
s3 = boto3.client("s3")
matched_key = None

response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
for obj in response.get("Contents", []):
    if claim_id in obj["Key"] and obj["Key"].endswith(".json"):
        matched_key = obj["Key"]
        break

if not matched_key:
    raise ValueError(f"❌ No fraud result found in S3 for claim ID: {claim_id}")

# --- Load Fraud JSON --- #
file_obj = s3.get_object(Bucket=bucket, Key=matched_key)
content = file_obj["Body"].read().decode("utf-8")
fraud_data = json.loads(content)

# --- Extract raw input features --- #
raw = fraud_data.get("raw_features", {})
claim_status = fraud_data.get("claim_status", "Manual Review")

# --- Connect to Redshift --- #
try:
    conn = psycopg2.connect(
        dbname=redshift_db,
        host=redshift_host,
        port=redshift_port,
        user=redshift_user,
        password=redshift_pass
    )
    cursor = conn.cursor()
except Exception as e:
    raise RuntimeError(f"❌ Failed to connect to Redshift: {e}")

# --- Insert into Redshift using raw_features --- #
sql = """
INSERT INTO aicp_insurance.claims_processed (
    claim_id,
    fraud_prediction,
    fraud_score,
    fraud_explanation,
    claim_to_damage_ratio,
    vehicle_age,
    previous_claims_count,
    days_since_policy_start,
    location_risk_score,
    incident_time_hour,
    claim_status,
    inserted_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

cursor.execute(sql, (
    fraud_data["claim_id"],
    fraud_data["fraud_prediction"],
    fraud_data["fraud_score"],
    fraud_data["fraud_explanation"],
    raw.get("claim_to_damage_ratio"),
    raw.get("vehicle_age"),
    raw.get("previous_claims_count"),
    raw.get("days_since_policy_start"),
    raw.get("location_risk_score"),
    raw.get("incident_time_hour"),
    claim_status,
    datetime.utcnow()
))

# --- Commit and Close --- #
conn.commit()
cursor.close()
conn.close()

print(f"✅ Inserted fraud result for {fraud_data['claim_id']} into Redshift.")
