# Day 2: Securing the Architecture

## Lab Information

| Field | Value |
|-------|-------|
| **Duration** | 5 Hours (300 minutes) |
| **Difficulty** | Intermediate |
| **Region** | ap-south-1 (N. Virginia) |
| **Services** | IAM, Secrets Manager, VPC Endpoints, WAF, KMS, ACM, CloudTrail, CloudWatch, GuardDuty, Config |

## Pre-Built Environment

Your Day 1 architecture is already deployed. Verify it's working:

```bash
# Get ALB URL from CloudFormation outputs
ALB_DNS=$(aws elbv2 describe-load-balancers --names workshop-alb --query 'LoadBalancers[0].DNSName' --output text --region ap-south-1)
curl http://$ALB_DNS/api/health
```

Expected output: `{"database":"connected","service":"cloudkida-workshop-backend","status":"healthy",...}`

## Architecture (Starting State)

```
Internet → ALB (HTTP:80) → ECS Fargate (Port 5000) → RDS MySQL (Port 3306)
              │                    │                         │
         Public Subnet       Private App Subnet        Private Data Subnet
              │                    │                         │
         ALB SG (80)          ECS SG (5000)           RDS SG (3306)
```

## What We'll Add Today

```
┌──────── Edge Security ────────┐
│  WAF Web ACL (SQL injection,  │
│  XSS, rate limiting)         │
└───────────────┬───────────────┘
                ↓
┌──────── Transport Security ───┐
│  ACM Certificate + HTTPS     │
└───────────────┬───────────────┘
                ↓
┌──────── Network Security ─────┐
│  VPC Endpoints (no NAT)      │
│  NACLs (data tier)           │
│  VPC Flow Logs               │
└───────────────┬───────────────┘
                ↓
┌──────── Identity & Secrets ───┐
│  ECS Task Role (least priv)  │
│  Secrets Manager (DB creds)  │
└───────────────┬───────────────┘
                ↓
┌──────── Data Security ────────┐
│  KMS CMK (RDS encryption)    │
│  S3 bucket policy            │
└───────────────┬───────────────┘
                ↓
┌──────── Monitoring ───────────┐
│  CloudTrail, CloudWatch      │
│  GuardDuty, AWS Config       │
└───────────────────────────────┘
```

---

## Part 1: Identity & Secrets Management (90 minutes)

### Step 1.1: Move DB Credentials to Secrets Manager

Currently, the DB password is stored as a plain-text environment variable in the ECS task definition. Let's fix that.

**Console:**
1. Navigate to **Secrets Manager** → **Store a new secret**
2. Secret type: **Credentials for Amazon RDS database**
3. Username: `admin`
4. Password: `WorkshopDB2026!`
5. Database: Select `workshop-db`
6. Secret name: `workshop/db-credentials`
7. Disable automatic rotation (for this lab)
8. Click **Store**

**CLI:**
```bash
# Store DB credentials in Secrets Manager
aws secretsmanager create-secret \
  --name workshop/db-credentials \
  --description "Workshop RDS database credentials" \
  --secret-string '{"username":"admin","password":"WorkshopDB2026!","engine":"mysql","host":"'$(aws rds describe-db-instances --db-instance-identifier workshop-db --query 'DBInstances[0].Endpoint.Address' --output text --region ap-south-1)'","port":3306,"dbname":"cloudkida"}' \
  --region ap-south-1
```

### Step 1.2: Update ECS Task Execution Role for Secrets

The execution role needs permission to read from Secrets Manager:

**Console:**
1. Go to **IAM** → **Roles** → `workshop-ecs-execution-role`
2. Click **Add permissions** → **Create inline policy**
3. JSON:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "secretsmanager:GetSecretValue"
    ],
    "Resource": "arn:aws:secretsmanager:ap-south-1:*:secret:workshop/*"
  }]
}
```
4. Name: `SecretsManagerReadPolicy`
5. Click **Create policy**

**CLI:**
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > /tmp/secrets-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue"],
    "Resource": "arn:aws:secretsmanager:ap-south-1:${ACCOUNT_ID}:secret:workshop/*"
  }]
}
EOF

aws iam put-role-policy --role-name workshop-ecs-execution-role \
  --policy-name SecretsManagerReadPolicy \
  --policy-document file:///tmp/secrets-policy.json
```

### Step 1.3: Update Task Definition to Use Secrets

**Console:**
1. Go to **ECS** → **Task definitions** → `workshop-app` → **Create new revision**
2. In the container definition, change the DB_PASSWORD from **Value** to **ValueFrom**:
   - Remove the `DB_PASSWORD` environment variable
   - Add under **Secrets**: 
     - Key: `DB_PASSWORD`
     - Value: `arn:aws:secretsmanager:ap-south-1:<account-id>:secret:workshop/db-credentials`
     - JSON key: `password`
3. Click **Create**

**CLI:**
```bash
SECRET_ARN=$(aws secretsmanager describe-secret --secret-id workshop/db-credentials --query 'ARN' --output text --region ap-south-1)
RDS_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier workshop-db --query 'DBInstances[0].Endpoint.Address' --output text --region ap-south-1)

cat > /tmp/task-definition-v2.json << EOF
{
  "family": "workshop-app",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/workshop-ecs-execution-role",
  "taskRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/workshop-ecs-task-role",
  "containerDefinitions": [{
    "name": "app",
    "image": "${ACCOUNT_ID}.dkr.ecr.ap-south-1.amazonaws.com/workshop-app:latest",
    "portMappings": [{"containerPort": 5000, "protocol": "tcp"}],
    "environment": [
      {"name": "DB_HOST", "value": "${RDS_ENDPOINT}"},
      {"name": "DB_PORT", "value": "3306"},
      {"name": "DB_NAME", "value": "cloudkida"},
      {"name": "DB_USER", "value": "admin"},
      {"name": "PORT", "value": "5000"}
    ],
    "secrets": [
      {"name": "DB_PASSWORD", "valueFrom": "${SECRET_ARN}:password::"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/workshop-app",
        "awslogs-region": "ap-south-1",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "essential": true
  }]
}
EOF

aws ecs register-task-definition --cli-input-json file:///tmp/task-definition-v2.json --region ap-south-1
```

### Step 1.4: Update ECS Service with New Task Definition

```bash
aws ecs update-service --cluster workshop-cluster \
  --service workshop-service \
  --task-definition workshop-app \
  --force-new-deployment \
  --region ap-south-1
```

### Step 1.5: Harden ECS Task Role (Least Privilege)

**Console:**
1. Go to **IAM** → **Roles** → `workshop-ecs-task-role`
2. Remove any overly broad permissions
3. Add inline policy with only what the app needs:

**CLI:**
```bash
cat > /tmp/task-role-least-privilege.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-south-1:*:log-group:/ecs/workshop-app:*"
    }
  ]
}
EOF

aws iam put-role-policy --role-name workshop-ecs-task-role \
  --policy-name LeastPrivilegePolicy \
  --policy-document file:///tmp/task-role-least-privilege.json
```

### ✅ Checkpoint: Verify Secrets Integration

```bash
# Wait for new task to start (1-2 minutes)
sleep 60

# Test health check - should show "connected"
curl http://$ALB_DNS/api/health

# Verify no plain-text password in task definition
aws ecs describe-task-definition --task-definition workshop-app --query 'taskDefinition.containerDefinitions[0].secrets' --region ap-south-1
```

---

## Part 2: Network Security & Encryption (90 minutes)

### Step 2.1: Create VPC Interface Endpoints

VPC Endpoints allow ECS tasks to access AWS services without going through the NAT Gateway (more secure + cost-effective).

**Console:**
1. Go to **VPC** → **Endpoints** → **Create endpoint**
2. Create endpoints for:
   - `com.amazonaws.ap-south-1.ecr.dkr`
   - `com.amazonaws.ap-south-1.ecr.api`
   - `com.amazonaws.ap-south-1.secretsmanager`
   - `com.amazonaws.ap-south-1.logs`
3. For each:
   - VPC: workshop-vpc
   - Subnets: Private app subnets
   - Security group: Create `workshop-vpce-sg` (allow HTTPS 443 from VPC CIDR)

**CLI:**
```bash
# Get VPC ID
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=workshop-vpc" --query 'Vpcs[0].VpcId' --output text --region ap-south-1)

# Create security group for VPC endpoints
VPCE_SG=$(aws ec2 create-security-group --group-name workshop-vpce-sg \
  --description "VPC Endpoints - Allow HTTPS from VPC" \
  --vpc-id $VPC_ID --query 'GroupId' --output text --region ap-south-1)

aws ec2 create-tags --resources $VPCE_SG --tags Key=Name,Value=workshop-vpce-sg --region ap-south-1
aws ec2 authorize-security-group-ingress --group-id $VPCE_SG \
  --protocol tcp --port 443 --cidr 10.0.0.0/16 --region ap-south-1

# Get private app subnet IDs
APP_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-app-1" --query 'Subnets[0].SubnetId' --output text --region ap-south-1)
APP_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-app-2" --query 'Subnets[0].SubnetId' --output text --region ap-south-1)

# Create VPC Endpoints
for SERVICE in com.amazonaws.ap-south-1.ecr.dkr com.amazonaws.ap-south-1.ecr.api com.amazonaws.ap-south-1.secretsmanager com.amazonaws.ap-south-1.logs; do
  echo "Creating endpoint for $SERVICE..."
  aws ec2 create-vpc-endpoint \
    --vpc-id $VPC_ID \
    --vpc-endpoint-type Interface \
    --service-name $SERVICE \
    --subnet-ids $APP_SUBNET_1 $APP_SUBNET_2 \
    --security-group-ids $VPCE_SG \
    --private-dns-enabled \
    --region ap-south-1
done

# Also create S3 Gateway Endpoint (free, no NAT needed for S3)
PRIV_RT=$(aws ec2 describe-route-tables --filters "Name=tag:Name,Values=workshop-private-rt" --query 'RouteTables[0].RouteTableId' --output text --region ap-south-1)

aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --vpc-endpoint-type Gateway \
  --service-name com.amazonaws.ap-south-1.s3 \
  --route-table-ids $PRIV_RT \
  --region ap-south-1
```

### Step 2.2: Add NACLs for Data Tier

NACLs add an extra layer of defense (stateless). Add them to the data subnets:

**Console:**
1. Go to **VPC** → **Network ACLs** → **Create network ACL**
2. Name: `workshop-data-nacl`
3. VPC: workshop-vpc
4. Edit inbound rules:
   - Rule 100: Allow MySQL (3306) from 10.0.10.0/24 (app subnet 1)
   - Rule 110: Allow MySQL (3306) from 10.0.11.0/24 (app subnet 2)
   - Rule 200: Allow ephemeral ports (1024-65535) from 10.0.0.0/16
   - Rule *: Deny all
5. Edit outbound rules:
   - Rule 100: Allow ephemeral ports (1024-65535) to 10.0.10.0/24
   - Rule 110: Allow ephemeral ports (1024-65535) to 10.0.11.0/24
   - Rule *: Deny all
6. Associate with data subnets

**CLI:**
```bash
# Create NACL
DATA_NACL=$(aws ec2 create-network-acl --vpc-id $VPC_ID \
  --tag-specifications 'ResourceType=network-acl,Tags=[{Key=Name,Value=workshop-data-nacl}]' \
  --query 'NetworkAcl.NetworkAclId' --output text --region ap-south-1)

# Inbound rules
aws ec2 create-network-acl-entry --network-acl-id $DATA_NACL --ingress \
  --rule-number 100 --protocol tcp --port-range From=3306,To=3306 \
  --cidr-block 10.0.10.0/24 --rule-action allow --region ap-south-1

aws ec2 create-network-acl-entry --network-acl-id $DATA_NACL --ingress \
  --rule-number 110 --protocol tcp --port-range From=3306,To=3306 \
  --cidr-block 10.0.11.0/24 --rule-action allow --region ap-south-1

aws ec2 create-network-acl-entry --network-acl-id $DATA_NACL --ingress \
  --rule-number 200 --protocol tcp --port-range From=1024,To=65535 \
  --cidr-block 10.0.0.0/16 --rule-action allow --region ap-south-1

# Outbound rules
aws ec2 create-network-acl-entry --network-acl-id $DATA_NACL --egress \
  --rule-number 100 --protocol tcp --port-range From=1024,To=65535 \
  --cidr-block 10.0.10.0/24 --rule-action allow --region ap-south-1

aws ec2 create-network-acl-entry --network-acl-id $DATA_NACL --egress \
  --rule-number 110 --protocol tcp --port-range From=1024,To=65535 \
  --cidr-block 10.0.11.0/24 --rule-action allow --region ap-south-1

# Associate with data subnets
DATA_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-data-1" --query 'Subnets[0].SubnetId' --output text --region ap-south-1)
DATA_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-data-2" --query 'Subnets[0].SubnetId' --output text --region ap-south-1)

# Get current NACL associations for data subnets and replace
for SUBNET in $DATA_SUBNET_1 $DATA_SUBNET_2; do
  ASSOC_ID=$(aws ec2 describe-network-acls --filters "Name=association.subnet-id,Values=$SUBNET" --query 'NetworkAcls[0].Associations[?SubnetId==`'$SUBNET'`].NetworkAclAssociationId' --output text --region ap-south-1)
  aws ec2 replace-network-acl-association --association-id $ASSOC_ID --network-acl-id $DATA_NACL --region ap-south-1
done
```

### Step 2.3: Enable VPC Flow Logs

**Console:**
1. Go to **VPC** → **Your VPCs** → Select workshop-vpc
2. **Actions** → **Create flow log**
3. Filter: All
4. Destination: CloudWatch Logs
5. Log group: `/vpc/workshop-flow-logs`
6. IAM role: Create new role (or create manually)
7. Click **Create**

**CLI:**
```bash
# Create log group
aws logs create-log-group --log-group-name /vpc/workshop-flow-logs --region ap-south-1

# Create IAM role for Flow Logs
cat > /tmp/flow-logs-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "vpc-flow-logs.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role --role-name workshop-flow-logs-role \
  --assume-role-policy-document file:///tmp/flow-logs-trust.json

cat > /tmp/flow-logs-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","logs:DescribeLogGroups","logs:DescribeLogStreams"],
    "Resource": "*"
  }]
}
EOF

aws iam put-role-policy --role-name workshop-flow-logs-role \
  --policy-name FlowLogsPolicy \
  --policy-document file:///tmp/flow-logs-policy.json

# Create Flow Log
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=workshop-vpc" --query 'Vpcs[0].VpcId' --output text --region ap-south-1)

aws ec2 create-flow-logs \
  --resource-type VPC \
  --resource-ids $VPC_ID \
  --traffic-type ALL \
  --log-destination-type cloud-watch-logs \
  --log-group-name /vpc/workshop-flow-logs \
  --deliver-logs-permission-arn arn:aws:iam::${ACCOUNT_ID}:role/workshop-flow-logs-role \
  --region ap-south-1
```

### Step 2.4: Create KMS Key for Encryption

**Console:**
1. Go to **KMS** → **Customer managed keys** → **Create key**
2. Key type: Symmetric
3. Alias: `workshop-key`
4. Key administrators: Your IAM user
5. Key usage: Your IAM user + ECS execution role
6. Click **Finish**

**CLI:**
```bash
KMS_KEY_ID=$(aws kms create-key \
  --description "Workshop encryption key" \
  --query 'KeyMetadata.KeyId' --output text --region ap-south-1)

aws kms create-alias --alias-name alias/workshop-key \
  --target-key-id $KMS_KEY_ID --region ap-south-1

echo "KMS Key ID: $KMS_KEY_ID"
```

### Step 2.5: Create Encrypted S3 Bucket

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="workshop-secure-${ACCOUNT_ID}"

# Create bucket
aws s3api create-bucket --bucket $BUCKET_NAME --region ap-south-1

# Block all public access
aws s3api put-public-access-block --bucket $BUCKET_NAME \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Enable default encryption with KMS
aws s3api put-bucket-encryption --bucket $BUCKET_NAME \
  --server-side-encryption-configuration '{
    "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms", "KMSMasterKeyID": "'$KMS_KEY_ID'"}, "BucketKeyEnabled": true}]
  }'

# Bucket policy: allow Config delivery + deny unencrypted uploads from others
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > /tmp/bucket-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AWSConfigBucketPermissionsCheck",
      "Effect": "Allow",
      "Principal": {"Service": "config.amazonaws.com"},
      "Action": "s3:GetBucketAcl",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}"
    },
    {
      "Sid": "AWSConfigBucketExistenceCheck",
      "Effect": "Allow",
      "Principal": {"Service": "config.amazonaws.com"},
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}"
    },
    {
      "Sid": "AWSConfigBucketDelivery",
      "Effect": "Allow",
      "Principal": {"Service": "config.amazonaws.com"},
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/AWSLogs/${ACCOUNT_ID}/Config/*",
      "Condition": {
        "StringEquals": {
          "s3:x-amz-acl": "bucket-owner-full-control"
        }
      }
    }
  ]
}
EOF

aws s3api put-bucket-policy --bucket $BUCKET_NAME --policy file:///tmp/bucket-policy.json
```

---

## Part 3: Edge Security — WAF (45 minutes)

### Step 3.1: Create WAF Web ACL

**Console:**
1. Navigate to **WAF & Shield** → **Web ACLs** → **Create web ACL**
2. Name: `workshop-waf`
3. Resource type: Regional
4. Associated resources: Add `workshop-alb`
5. Add managed rule groups:
   - **AWS Managed Rules → Core rule set** (AWSManagedRulesCommonRuleSet)
   - **AWS Managed Rules → SQL database** (AWSManagedRulesSQLiRuleSet)
   - **AWS Managed Rules → Known bad inputs** (AWSManagedRulesKnownBadInputsRuleSet)
6. Add custom rule:
   - Name: `RateLimit`
   - Type: Rate-based
   - Rate limit: 100 requests per 5 minutes
   - Action: Block
7. Default action: Allow
8. Click **Create web ACL**

**CLI:**
```bash
ALB_ARN=$(aws elbv2 describe-load-balancers --names workshop-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text --region ap-south-1)

cat > /tmp/waf-rules.json << 'EOF'
[
  {
    "Name": "AWS-AWSManagedRulesCommonRuleSet",
    "Priority": 1,
    "OverrideAction": {"None": {}},
    "Statement": {
      "ManagedRuleGroupStatement": {
        "VendorName": "AWS",
        "Name": "AWSManagedRulesCommonRuleSet"
      }
    },
    "VisibilityConfig": {
      "SampledRequestsEnabled": true,
      "CloudWatchMetricsEnabled": true,
      "MetricName": "CommonRuleSet"
    }
  },
  {
    "Name": "AWS-AWSManagedRulesSQLiRuleSet",
    "Priority": 2,
    "OverrideAction": {"None": {}},
    "Statement": {
      "ManagedRuleGroupStatement": {
        "VendorName": "AWS",
        "Name": "AWSManagedRulesSQLiRuleSet"
      }
    },
    "VisibilityConfig": {
      "SampledRequestsEnabled": true,
      "CloudWatchMetricsEnabled": true,
      "MetricName": "SQLiRuleSet"
    }
  },
  {
    "Name": "RateLimit",
    "Priority": 3,
    "Action": {"Block": {}},
    "Statement": {
      "RateBasedStatement": {
        "Limit": 100,
        "AggregateKeyType": "IP"
      }
    },
    "VisibilityConfig": {
      "SampledRequestsEnabled": true,
      "CloudWatchMetricsEnabled": true,
      "MetricName": "RateLimit"
    }
  }
]
EOF

aws wafv2 create-web-acl \
  --name workshop-waf \
  --scope REGIONAL \
  --default-action '{"Allow":{}}' \
  --rules file:///tmp/waf-rules.json \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=workshop-waf \
  --region ap-south-1

# Associate with ALB
WAF_ARN=$(aws wafv2 list-web-acls --scope REGIONAL --query 'WebACLs[?Name==`workshop-waf`].ARN' --output text --region ap-south-1)

# Wait for WAF to propagate (takes ~10-15 seconds)
echo "Waiting for WAF Web ACL to propagate..."
sleep 15

aws wafv2 associate-web-acl --web-acl-arn $WAF_ARN --resource-arn $ALB_ARN --region ap-south-1
```

### Step 3.2: Test WAF Rules

```bash
# Test SQL Injection - should be BLOCKED (403)
curl -s -o /dev/null -w "%{http_code}" "http://$ALB_DNS/api/labs?category=1'%20OR%201=1--"

# Test normal request - should PASS (200)
curl -s -o /dev/null -w "%{http_code}" "http://$ALB_DNS/api/health"

# Test XSS - should be BLOCKED (403)
curl -s -o /dev/null -w "%{http_code}" "http://$ALB_DNS/api/labs?category=<script>alert(1)</script>"
```

---

## Part 4: Monitoring & Detection (45 minutes)

### Step 4.1: Create CloudWatch Alarms

**Console:**
1. Go to **CloudWatch** → **Alarms** → **Create alarm**

**CLI:**
```bash
# Create SNS topic for alerts
TOPIC_ARN=$(aws sns create-topic --name workshop-alerts --query 'TopicArn' --output text --region ap-south-1)

# Subscribe your email
aws sns subscribe --topic-arn $TOPIC_ARN \
  --protocol email --notification-endpoint your-email@example.com --region ap-south-1

# Alarm: ALB 5xx errors
aws cloudwatch put-metric-alarm \
  --alarm-name workshop-alb-5xx \
  --alarm-description "ALB 5xx errors > 10 in 5 minutes" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions $TOPIC_ARN \
  --dimensions Name=LoadBalancer,Value=$(aws elbv2 describe-load-balancers --names workshop-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text --region ap-south-1 | cut -d'/' -f2-) \
  --region ap-south-1

# Alarm: ECS CPU > 80%
aws cloudwatch put-metric-alarm \
  --alarm-name workshop-ecs-cpu-high \
  --alarm-description "ECS CPU > 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions $TOPIC_ARN \
  --dimensions Name=ClusterName,Value=workshop-cluster Name=ServiceName,Value=workshop-service \
  --region ap-south-1

# Alarm: RDS connections > 20
aws cloudwatch put-metric-alarm \
  --alarm-name workshop-rds-connections \
  --alarm-description "RDS connections > 20" \
  --metric-name DatabaseConnections \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 20 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions $TOPIC_ARN \
  --dimensions Name=DBInstanceIdentifier,Value=workshop-db \
  --region ap-south-1
```

### Step 4.2: Enable GuardDuty

**Console:**
1. Navigate to **GuardDuty** → **Get Started** → **Enable GuardDuty**

**CLI:**
```bash
aws guardduty create-detector --enable --region ap-south-1
```

> GuardDuty has a 30-day free trial. It monitors VPC Flow Logs, DNS logs, and CloudTrail for threats.

### Step 4.3: Enable AWS Config

**Console:**
1. Navigate to **AWS Config** → **Get started**
2. Recording: All resources in this region
3. S3 bucket: Create new or use existing
4. SNS topic: workshop-alerts
5. Click **Confirm**

**CLI:**
```bash
# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create Config role
cat > /tmp/config-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "config.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role --role-name workshop-config-role \
  --assume-role-policy-document file:///tmp/config-trust.json

aws iam attach-role-policy --role-name workshop-config-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWS_ConfigRole

# Add S3 delivery permissions to the role
cat > /tmp/config-s3-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetBucketAcl"],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "${TOPIC_ARN}"
    }
  ]
}
EOF

aws iam put-role-policy --role-name workshop-config-role \
  --policy-name ConfigDeliveryPolicy \
  --policy-document file:///tmp/config-s3-policy.json

# Wait for IAM role propagation
echo "Waiting for IAM role to propagate..."
sleep 15

# Create Config recorder
aws configservice put-configuration-recorder \
  --configuration-recorder name=default,roleARN=arn:aws:iam::${ACCOUNT_ID}:role/workshop-config-role \
  --recording-group allSupported=true,includeGlobalResourceTypes=true \
  --region ap-south-1

# Create delivery channel
aws configservice put-delivery-channel \
  --delivery-channel name=default,s3BucketName=${BUCKET_NAME},snsTopicARN=${TOPIC_ARN} \
  --region ap-south-1

# Start recorder
aws configservice start-configuration-recorder --configuration-recorder-name default --region ap-south-1

# Add Config rule: check S3 encryption
aws configservice put-config-rule --config-rule '{
  "ConfigRuleName": "s3-bucket-server-side-encryption-enabled",
  "Source": {
    "Owner": "AWS",
    "SourceIdentifier": "S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED"
  }
}' --region ap-south-1
```

### Step 4.4: Review CloudTrail Events

CloudTrail is enabled by default for management events. Let's review:

```bash
# Look at recent API calls (last hour)
aws cloudtrail lookup-events \
  --max-results 20 \
  --query 'Events[*].{Time:EventTime,Event:EventName,User:Username}' \
  --output table --region ap-south-1
```

---

## Part 5: Architecture Review (30 minutes)

### Security Layers Summary

| Layer | Service | Protection |
|-------|---------|-----------|
| Edge | WAF | SQL injection, XSS, rate limiting |
| Transport | ACM/HTTPS | Encryption in transit |
| Network | Security Groups | Stateful firewall per tier |
| Network | NACLs | Stateless firewall (data tier) |
| Network | VPC Endpoints | Private AWS API access |
| Identity | IAM Task Roles | Least privilege for containers |
| Secrets | Secrets Manager | No plain-text credentials |
| Data | KMS | Encryption at rest |
| Monitoring | CloudWatch | Alarms and metrics |
| Detection | GuardDuty | Threat intelligence |
| Compliance | AWS Config | Configuration drift |
| Audit | CloudTrail | API activity logging |
| Network Visibility | VPC Flow Logs | Network traffic analysis |

### Final Verification

```bash
# 1. App still works
curl http://$ALB_DNS/api/health

# 2. WAF is blocking attacks
curl -s -o /dev/null -w "%{http_code}" "http://$ALB_DNS/?id=1'+OR+1=1--"

# 3. Secrets Manager is used (no plain password in task def)
aws ecs describe-task-definition --task-definition workshop-app \
  --query 'taskDefinition.containerDefinitions[0].{env:environment,secrets:secrets}' \
  --region ap-south-1

# 4. VPC Endpoints exist
aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'VpcEndpoints[*].{Service:ServiceName,State:State}' --output table --region ap-south-1

# 5. GuardDuty enabled
aws guardduty list-detectors --region ap-south-1

# 6. CloudWatch alarms exist
aws cloudwatch describe-alarms --alarm-name-prefix workshop \
  --query 'MetricAlarms[*].{Name:AlarmName,State:StateValue}' --output table --region ap-south-1
```

---

## Cleanup

```bash
# 1. Delete WAF
WAF_ARN=$(aws wafv2 list-web-acls --scope REGIONAL --query 'WebACLs[?Name==`workshop-waf`].ARN' --output text --region ap-south-1)
aws wafv2 disassociate-web-acl --resource-arn $ALB_ARN --region ap-south-1
LOCK_TOKEN=$(aws wafv2 get-web-acl --name workshop-waf --scope REGIONAL --id $(echo $WAF_ARN | rev | cut -d'/' -f1 | rev) --query 'LockToken' --output text --region ap-south-1)
aws wafv2 delete-web-acl --name workshop-waf --scope REGIONAL --id $(echo $WAF_ARN | rev | cut -d'/' -f1 | rev) --lock-token $LOCK_TOKEN --region ap-south-1

# 2. Delete VPC Endpoints
for VPCE in $(aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" --query 'VpcEndpoints[*].VpcEndpointId' --output text --region ap-south-1); do
  aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $VPCE --region ap-south-1
done

# 3. Disable GuardDuty
DETECTOR_ID=$(aws guardduty list-detectors --query 'DetectorIds[0]' --output text --region ap-south-1)
aws guardduty delete-detector --detector-id $DETECTOR_ID --region ap-south-1

# 4. Delete Config (wait between calls - Config API has low rate limits)
aws configservice stop-configuration-recorder --configuration-recorder-name default --region ap-south-1
sleep 5
aws configservice delete-delivery-channel --delivery-channel-name default --region ap-south-1
sleep 5
aws configservice delete-configuration-recorder --configuration-recorder-name default --region ap-south-1

# 5. Delete CloudWatch Alarms
aws cloudwatch delete-alarms --alarm-names workshop-alb-5xx workshop-ecs-cpu-high workshop-rds-connections --region ap-south-1

# 6. Delete SNS Topic
aws sns delete-topic --topic-arn $TOPIC_ARN --region ap-south-1

# 7. Delete Secrets Manager secret
aws secretsmanager delete-secret --secret-id workshop/db-credentials --force-delete-without-recovery --region ap-south-1

# 8. Delete KMS key (scheduled)
aws kms schedule-key-deletion --key-id $KMS_KEY_ID --pending-window-in-days 7 --region ap-south-1

# 9. Delete S3 bucket
aws s3 rb s3://$BUCKET_NAME --force

# 10. Delete Day 1 infrastructure (ECS, ALB, RDS, VPC)
# (Same as Day 1 cleanup)
```

---

## 🎉 Congratulations!

You have successfully secured a production AWS architecture with:
- ✅ Secrets Manager (no plain-text credentials)
- ✅ IAM least privilege (Task Roles)
- ✅ VPC Endpoints (private AWS API access)
- ✅ NACLs (defense in depth for data tier)
- ✅ VPC Flow Logs (network visibility)
- ✅ WAF (SQL injection, XSS, rate limiting protection)
- ✅ KMS encryption (S3 bucket with enforced encryption)
- ✅ CloudWatch Alarms (automated alerting)
- ✅ GuardDuty (threat detection)
- ✅ AWS Config (compliance monitoring)
- ✅ CloudTrail (API audit logging)

**This is a production-grade security posture aligned with the AWS Well-Architected Framework Security Pillar!**
