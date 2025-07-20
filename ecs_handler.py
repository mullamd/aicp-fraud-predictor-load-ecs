import os  
import json
import boto3
import psycopg2

# 0. Setup SNS for Redshift monitoring
sns = boto3.client('sns')
sns_topic = 'arn:aws:sns:us-east-1:461512246753:aicp-redshift-status-topic'

# 1. Read CLAIM_ID from environment
claim_id = os.environ.get("CLAIM_ID")
if not claim_id:
    raise ValueError("CLAIM_ID environment variable not found.")

# 2. Search for matching DQ-validated claim file in S3
s3 = boto3.client('s3')
bucket = 'aicp-claims-data'
prefix = 'processed/DQ-validated-claims-data/'

matched_key = None
try:
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    for obj in response.get('Contents', []):
        key = obj['Key']
        if claim_id in key and key.endswith('.json'):
            matched_key = key
            break
    if not matched_key:
        raise FileNotFoundError(f"No matching claim file found in S3 for {claim_id}")
    
    obj = s3.get_object(Bucket=bucket, Key=matched_key)
    event = json.loads(obj['Body'].read().decode('utf-8'))
    print(f"✅ Loaded claim file from S3: {matched_key}")

except Exception as e:
    print(f"❌ Failed to load claim JSON from S3: {e}")
    raise

# 3. Prepare SageMaker payload
required_keys = [
    "claim_amount_requested", "estimated_damage_cost", "vehicle_year",
    "days_since_policy_start", "location_risk_score"
]

missing_keys = [k for k in required_keys if k not in event]
if missing_keys:
    raise KeyError(f"Missing required keys for SageMaker payload: {missing_keys}")

sm_payload = {
    "claim_amount": event["claim_amount_requested"],
    "estimated_damage": event["estimated_damage_cost"],
    "vehicle_year": event["vehicle_year"],
    "days_since_policy_start": event["days_since_policy_start"],
    "location_risk_score": event["location_risk_score"]
}

# 4. Call SageMaker endpoint
try:
    sagemaker = boto3.client("sagemaker-runtime")
    response = sagemaker.invoke_endpoint(
        EndpointName="aicp-fraud-endpoint-1752473908",
        ContentType="application/json",
        Body=json.dumps(sm_payload)
    )
    result = json.loads(response["Body"].read().decode("utf-8"))
    print("✅ SageMaker response received.")
except Exception as e:
    print(f"❌ SageMaker endpoint invocation failed: {e}")
    raise

# 5. Connect to Redshift
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

# 6. Insert into Redshift
try:
    cur.execute("""
        INSERT INTO public.claims_processed (
            claim_id, policy_number, claimant_name, date_of_loss,
            type_of_claim, accident_location, vehicle_make, vehicle_model,
            vehicle_year, license_plate, description_of_damage,
            estimated_damage_cost, claim_amount_requested,
            is_valid, textract_status, dq_validation_status,
            fraud_score, fraud_prediction, fraud_explanation,
            claim_to_damage_ratio, days_since_policy_start,
            previous_claims_count, location_risk_score, vehicle_age,
            incident_time, processed_by, shap_features
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        event.get("processed_by"),
        ", ".join(result.get("shap_features", []))
    ))
    conn.commit()
    print("✅ Inserted fraud result into Redshift.")

    sns.publish(
        TopicArn=sns_topic,
        Subject="✅ Redshift Insert Succeeded",
        Message=f"Claim ID {event.get('claim_id')} successfully inserted into Redshift table."
    )

except Exception as e:
    print(f"❌ Failed to insert into Redshift: {e}")
    conn.rollback()
    sns.publish(
        TopicArn=sns_topic,
        Subject="❌ Redshift Insert Failed",
        Message=f"Claim ID {event.get('claim_id')} failed to insert.\nError: {str(e)}"
    )
    raise

finally:
    cur.close()
    conn.close()
