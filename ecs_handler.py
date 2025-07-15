import os
import json
import boto3
import psycopg2

# 1. Read input from environment variable
try:
    payload = os.environ.get("CLAIM_PAYLOAD")
    if not payload:
        raise ValueError("CLAIM_PAYLOAD environment variable not found.")
    event = json.loads(payload)
except Exception as e:
    print(f"❌ Error loading CLAIM_PAYLOAD: {e}")
    raise

# 2. Prepare SageMaker payload
try:
    sm_payload = {
        "claim_amount": event["claim_amount_requested"],
        "estimated_damage": event["estimated_damage_cost"],
        "vehicle_year": event["vehicle_year"],
        "days_since_policy_start": event["days_since_policy_start"],
        "location_risk_score": event["location_risk_score"]
    }
except KeyError as e:
    print(f"❌ Missing key in input event: {e}")
    raise

# 3. Call SageMaker endpoint
try:
    sagemaker = boto3.client("sagemaker-runtime")
    response = sagemaker.invoke_endpoint(
        EndpointName="aicp-fraud-endpoint-1752473908",  # ✅ Replace if needed
        ContentType="application/json",
        Body=json.dumps(sm_payload)
    )
    result = json.loads(response["Body"].read().decode("utf-8"))
except Exception as e:
    print(f"❌ SageMaker endpoint invocation failed: {e}")
    raise

# 4. Connect to Redshift
try:
    conn = psycopg2.connect(
        dbname="aicp_insurance",
        host="redshift-cluster-2.cax5lwhmspd1.us-east-1.redshift.amazonaws.com",
        port=5439,
        user="redshift_admin",
        password="347634M-ulla7710"
    )
    cur = conn.cursor()
except Exception as e:
    print(f"❌ Redshift connection failed: {e}")
    raise

# 5. Insert into Redshift
try:
    cur.execute("""
        INSERT INTO .public.claims_processed (
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
        event.get("claim_id"),
        event.get("policy_number"),
        event.get("claimant_name"),
        event.get("date_of_loss"),
        event.get("type_of_claim"),
        event.get("accident_location"),
        event.get("vehicle_make"),
        event.get("vehicle_model"),
        event.get("vehicle_year"),
        event.get("license_plate"),
        event.get("description_of_damage"),
        event.get("estimated_damage_cost"),
        event.get("claim_amount_requested"),
        event.get("is_valid"),
        event.get("textract_status"),
        event.get("dq_validation_status"),
        result.get("fraud_score"),
        result.get("fraud_prediction"),
        result.get("fraud_explanation"),
        event.get("claim_to_damage_ratio"),
        event.get("days_since_policy_start"),
        event.get("previous_claims_count"),
        event.get("location_risk_score"),
        event.get("vehicle_age"),
        event.get("incident_time"),
        event.get("processed_by")
    ))
    conn.commit()
    print("✅ Inserted fraud result into Redshift.")
except Exception as e:
    print(f"❌ Failed to insert into Redshift: {e}")
    conn.rollback()
    raise
finally:
    cur.close()
    conn.close()
