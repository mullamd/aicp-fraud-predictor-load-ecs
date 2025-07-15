import os
import json
import boto3
import psycopg2

# 1. Read input from env variable
event = json.loads(os.environ.get("CLAIM_PAYLOAD", "{}"))

# 2. Prepare SageMaker payload
sm_payload = {
    "claim_amount": event["claim_amount_requested"],
    "estimated_damage": event["estimated_damage_cost"],
    "vehicle_year": event["vehicle_year"],
    "days_since_policy_start": event["days_since_policy_start"],
    "location_risk_score": event["location_risk_score"]
}

# 3. Call SageMaker endpoint
sagemaker = boto3.client("sagemaker-runtime")
response = sagemaker.invoke_endpoint(
    EndpointName="aicp-fraud-endpoint-1752473908",  # replace with your endpoint
    ContentType="application/json",
    Body=json.dumps(sm_payload)
)
result = json.loads(response["Body"].read().decode("utf-8"))

# 4. Connect to Redshift
conn = psycopg2.connect(
    dbname="dev",
    host="your-redshift-cluster.cax5lwhmspd1.us-east-1.redshift.amazonaws.com",
    port=5439,
    user="youruser",
    password="yourpassword"
)
cur = conn.cursor()

# 5. Insert into Redshift
cur.execute("""
    INSERT INTO auto_insurance_data.claims_processed (
        claim_id, policy_number, claimant_name, date_of_loss,
        type_of_claim, accident_location, vehicle_make, vehicle_model,
        vehicle_year, license_plate, description_of_damage,
        estimated_damage_cost, claim_amount_requested,
        is_valid, textract_status, dq_validation_status,
        fraud_score, fraud_prediction, fraud_explanation,
        claim_to_damage_ratio, days_since_policy_start,
        previous_claims_count, location_risk_score, vehicle_age,
        incident_time, processed_by
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""", (
    event["claim_id"],
    event["policy_number"],
    event["claimant_name"],
    event["date_of_loss"],
    event["type_of_claim"],
    event["accident_location"],
    event["vehicle_make"],
    event["vehicle_model"],
    event["vehicle_year"],
    event["license_plate"],
    event["description_of_damage"],
    event["estimated_damage_cost"],
    event["claim_amount_requested"],
    event["is_valid"],
    event["textract_status"],
    event["dq_validation_status"],
    result["fraud_score"],
    result["fraud_prediction"],
    result["fraud_explanation"],
    event["claim_to_damage_ratio"],
    event["days_since_policy_start"],
    event["previous_claims_count"],
    event["location_risk_score"],
    event["vehicle_age"],
    event["incident_time"],
    event["processed_by"]
))

conn.commit()
cur.close()
conn.close()
print("✅ Inserted fraud result into Redshift.")
