"""
Test script to verify AWS S3 configuration for stock list storage.
Run from the project root: py tests/test_s3_config.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def read_config_value(key):
    """Read KEY=VALUE from privatesettings/config.ini"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "privatesettings", "config.ini")
    try:
        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
    except Exception as e:
        print(f"  FAIL: Could not read config.ini: {e}")
    return ""

def main():
    print("=" * 60)
    print("AWS S3 Configuration Test")
    print("=" * 60)

    # Step 1: Check config.ini values
    print("\n[1/5] Reading config.ini...")
    access_key = read_config_value("AWS_ACCESS_KEY_ID")
    secret_key = read_config_value("AWS_SECRET_ACCESS_KEY")
    region = read_config_value("AWS_REGION") or "us-east-1"

    if not access_key:
        print("  FAIL: AWS_ACCESS_KEY_ID is empty or missing in privatesettings/config.ini")
        return
    if not secret_key:
        print("  FAIL: AWS_SECRET_ACCESS_KEY is empty or missing in privatesettings/config.ini")
        return
    print(f"  OK: Access Key = {access_key[:8]}...{access_key[-4:]}")
    print(f"  OK: Secret Key = ****...{secret_key[-4:]}")
    print(f"  OK: Region = {region}")

    # Step 2: Check boto3 import
    print("\n[2/5] Importing boto3...")
    try:
        import boto3
        from botocore.exceptions import ClientError
        print(f"  OK: boto3 {boto3.__version__}")
    except ImportError:
        print("  FAIL: boto3 is not installed. Run: pip install boto3")
        return

    # Step 3: Test authentication by listing buckets
    print("\n[3/5] Testing AWS authentication (listing buckets)...")
    try:
        s3 = boto3.client('s3',
                          region_name=region,
                          aws_access_key_id=access_key,
                          aws_secret_access_key=secret_key)
        response = s3.list_buckets()
        bucket_names = [b['Name'] for b in response['Buckets']]
        print(f"  OK: Authentication successful. Found {len(bucket_names)} bucket(s):")
        for name in bucket_names:
            print(f"       - {name}")
    except ClientError as e:
        print(f"  FAIL: AWS authentication error: {e}")
        return
    except Exception as e:
        print(f"  FAIL: Unexpected error: {e}")
        return

    # Step 4: Check if a specific bucket is configured in stockTickerConfig.json
    print("\n[4/5] Checking stockTickerConfig.json for S3 location...")
    bucket_name = None
    key_name = None
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "privatesettings", "stockTickerConfig.json")
    try:
        import json
        with open(config_path, "r") as f:
            config = json.load(f)
        for locn in config.get("ConfigLocations", []):
            if locn.get("getUsing") == "s3" or locn.get("putUsing") == "s3":
                bucket_name = locn.get("bucket", "")
                key_name = locn.get("key", "stocklist.json")
                print(f"  OK: Found S3 location: bucket={bucket_name} key={key_name}")
                break
        if not bucket_name:
            print("  SKIP: No S3 entry in ConfigLocations yet.")
            print("         Add one to privatesettings/stockTickerConfig.json to enable S3 storage.")
            print("         Example:")
            print('         {"getUsing":"s3","putUsing":"s3","bucket":"YOUR_BUCKET","key":"stocklist.json","sourceName":"s3"}')
            print("\n  Try a manual bucket test instead...")
            if bucket_names:
                bucket_name = bucket_names[0]
                key_name = "_s3_test_probe.json"
                print(f"  Using first available bucket: {bucket_name}")
            else:
                print("  FAIL: No buckets available to test with. Create one in the AWS Console first.")
                return
    except Exception as e:
        print(f"  WARN: Could not read stockTickerConfig.json: {e}")
        if bucket_names:
            bucket_name = bucket_names[0]
            key_name = "_s3_test_probe.json"
            print(f"  Using first available bucket for test: {bucket_name}")
        else:
            return

    # Step 5: Test read/write to the bucket
    print(f"\n[5/5] Testing read/write to bucket={bucket_name}...")
    test_key = "_s3_connection_test.json"
    test_data = '{"test": true, "message": "QtStockTicker S3 connectivity test"}'
    try:
        # Write
        s3.put_object(Bucket=bucket_name, Key=test_key,
                      Body=test_data.encode('utf-8'), ContentType='application/json')
        print(f"  OK: Write succeeded ({test_key})")

        # Read back
        response = s3.get_object(Bucket=bucket_name, Key=test_key)
        body = response['Body'].read().decode('utf-8')
        etag = response.get('ETag', 'N/A')
        version_id = response.get('VersionId', 'N/A (versioning not enabled)')
        print(f"  OK: Read succeeded, ETag={etag}")
        print(f"  OK: VersionId={version_id}")
        if body == test_data:
            print("  OK: Data roundtrip verified")
        else:
            print("  WARN: Data mismatch on read-back")

        # Clean up test object
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        print(f"  OK: Cleaned up test object ({test_key})")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            print(f"  FAIL: Bucket '{bucket_name}' does not exist. Create it in the AWS Console.")
        elif error_code == 'AccessDenied':
            print(f"  FAIL: Access denied to bucket '{bucket_name}'. Check IAM permissions.")
        else:
            print(f"  FAIL: S3 error: {e}")
        return
    except Exception as e:
        print(f"  FAIL: Unexpected error: {e}")
        return

    print("\n" + "=" * 60)
    print("All tests passed! S3 configuration is working.")
    if version_id and version_id != 'N/A (versioning not enabled)':
        print("Bucket versioning is ENABLED (recommended).")
    else:
        print("NOTE: Bucket versioning is NOT enabled.")
        print("      Enable it for conflict detection and history:")
        print(f"      aws s3api put-bucket-versioning --bucket {bucket_name} \\")
        print("        --versioning-configuration Status=Enabled")
    print("=" * 60)

if __name__ == "__main__":
    main()
