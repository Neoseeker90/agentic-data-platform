#!/usr/bin/env bash
set -euo pipefail

echo "Initialising LocalStack S3 bucket..."
awslocal s3 mb s3://agent-artifacts --region us-east-1 || true
echo "LocalStack S3 ready."
