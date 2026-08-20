# Day 1: Three-Tier Web Application on AWS

## Lab Information

| Field | Value |
|-------|-------|
| **Duration** | 5 Hours (300 minutes) |
| **Difficulty** | Intermediate |
| **Region** | us-east-1 (N. Virginia) |
| **Services** | VPC, ECS Fargate, RDS MySQL, ALB, ECR, CloudWatch |

## Learning Objectives

By the end of this lab, you will be able to:
- Design and build a VPC with multi-tier subnet architecture
- Deploy a containerized application on ECS Fargate
- Configure RDS MySQL as the data tier
- Set up an Application Load Balancer for public access
- Implement security group chaining between tiers
- Push Docker images to Amazon ECR

## Architecture

```
Internet
    │
    ▼
┌──────────────────────────────────────────┐
│  Application Load Balancer (Public)       │  ← Public Subnets
│  Port 80 → Target Group (Port 5000)      │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│  ECS Fargate Service (App Tier)          │  ← Private App Subnets
│  Flask API Container (Port 5000)         │
│  Connected to RDS MySQL                  │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│  RDS MySQL (Data Tier)                   │  ← Private Data Subnets
│  Database: cloudkida                     │
│  Encrypted at rest                       │
└──────────────────────────────────────────┘
```

## Prerequisites

- AWS Account access (provided via CloudKida)
- Basic understanding of Docker
- Basic networking knowledge (IP addresses, subnets)
- AWS CloudShell access (no local tools needed)

---

## Part 1: VPC & Networking (90 minutes)

### Step 1.1: Create the VPC

**Console:**
1. Navigate to **VPC** → **Your VPCs** → **Create VPC**
2. Select **VPC and more**
3. Configure:
   - Name tag: `workshop`
   - IPv4 CIDR: `10.0.0.0/16`
   - Number of AZs: `2`
   - Number of public subnets: `2`
   - Number of private subnets: `4` (2 app + 2 data — we'll use 4 private)
   - NAT gateways: `In 1 AZ`
   - VPC endpoints: None (we'll add on Day 2)
4. Click **Create VPC**

> ⚠️ **Note:** The "VPC and more" wizard creates subnets, route tables, IGW, and NAT GW automatically. If you prefer manual control, follow the CLI method below.

**CLI (Alternative — manual creation):**
```bash
# Create VPC
aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=workshop-vpc}]' \
  --region us-east-1

# Save VPC ID
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=workshop-vpc" --query 'Vpcs[0].VpcId' --output text --region us-east-1)

# Enable DNS hostnames
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames '{"Value":true}' --region us-east-1

# Create Public Subnets
aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=workshop-public-1}]' --region us-east-1

aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.2.0/24 --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=workshop-public-2}]' --region us-east-1

# Create Private App Subnets
aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.10.0/24 --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=workshop-private-app-1}]' --region us-east-1

aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.11.0/24 --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=workshop-private-app-2}]' --region us-east-1

# Create Private Data Subnets
aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.20.0/24 --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=workshop-private-data-1}]' --region us-east-1

aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.21.0/24 --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=workshop-private-data-2}]' --region us-east-1
```

### Step 1.2: Create Internet Gateway

**CLI:**
```bash
# Create IGW
aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=workshop-igw}]' \
  --region us-east-1

IGW_ID=$(aws ec2 describe-internet-gateways --filters "Name=tag:Name,Values=workshop-igw" --query 'InternetGateways[0].InternetGatewayId' --output text --region us-east-1)

# Attach to VPC
aws ec2 attach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID --region us-east-1
```

### Step 1.3: Create NAT Gateway

**Console:**
1. Go to **VPC** → **NAT Gateways** → **Create NAT gateway**
2. Name: `workshop-nat-gw`
3. Subnet: Select `workshop-public-1`
4. Connectivity type: Public
5. Click **Allocate Elastic IP** → then **Create NAT gateway**

**CLI:**
```bash
# Allocate Elastic IP
ALLOC_ID=$(aws ec2 allocate-address --domain vpc --query 'AllocationId' --output text --region us-east-1)

# Get public subnet ID
PUB_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-public-1" --query 'Subnets[0].SubnetId' --output text --region us-east-1)

# Create NAT Gateway
aws ec2 create-nat-gateway --subnet-id $PUB_SUBNET_1 --allocation-id $ALLOC_ID \
  --tag-specifications 'ResourceType=natgateway,Tags=[{Key=Name,Value=workshop-nat-gw}]' \
  --region us-east-1
```

### Step 1.4: Configure Route Tables

**Console:**
1. Go to **VPC** → **Route Tables**
2. Create **Public Route Table:**
   - Name: `workshop-public-rt`
   - VPC: workshop-vpc
   - Add route: `0.0.0.0/0` → Internet Gateway
   - Associate with: `workshop-public-1`, `workshop-public-2`
3. Create **Private Route Table:**
   - Name: `workshop-private-rt`
   - VPC: workshop-vpc
   - Add route: `0.0.0.0/0` → NAT Gateway
   - Associate with: all 4 private subnets

**CLI:**
```bash
# Create Public Route Table
PUB_RT=$(aws ec2 create-route-table --vpc-id $VPC_ID --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=workshop-public-rt}]' --query 'RouteTable.RouteTableId' --output text --region us-east-1)

# Add internet route
aws ec2 create-route --route-table-id $PUB_RT --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID --region us-east-1

# Associate public subnets
PUB_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-public-2" --query 'Subnets[0].SubnetId' --output text --region us-east-1)
aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_SUBNET_1 --region us-east-1
aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_SUBNET_2 --region us-east-1

# Enable auto-assign public IP on public subnets
aws ec2 modify-subnet-attribute --subnet-id $PUB_SUBNET_1 --map-public-ip-on-launch --region us-east-1
aws ec2 modify-subnet-attribute --subnet-id $PUB_SUBNET_2 --map-public-ip-on-launch --region us-east-1

# Create Private Route Table
NAT_GW_ID=$(aws ec2 describe-nat-gateways --filter "Name=tag:Name,Values=workshop-nat-gw" --query 'NatGateways[0].NatGatewayId' --output text --region us-east-1)

PRIV_RT=$(aws ec2 create-route-table --vpc-id $VPC_ID --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=workshop-private-rt}]' --query 'RouteTable.RouteTableId' --output text --region us-east-1)

# Wait for NAT Gateway to be available
echo "Waiting for NAT Gateway..."
aws ec2 wait nat-gateway-available --nat-gateway-ids $NAT_GW_ID --region us-east-1

aws ec2 create-route --route-table-id $PRIV_RT --destination-cidr-block 0.0.0.0/0 --nat-gateway-id $NAT_GW_ID --region us-east-1

# Associate private subnets
for SUBNET_NAME in workshop-private-app-1 workshop-private-app-2 workshop-private-data-1 workshop-private-data-2; do
  SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=$SUBNET_NAME" --query 'Subnets[0].SubnetId' --output text --region us-east-1)
  aws ec2 associate-route-table --route-table-id $PRIV_RT --subnet-id $SUBNET_ID --region us-east-1
done
```

### ✅ Checkpoint: Verify VPC Setup

```bash
# Verify VPC
aws ec2 describe-vpcs --filters "Name=tag:Name,Values=workshop-vpc" --query 'Vpcs[0].{VpcId:VpcId,CidrBlock:CidrBlock,State:State}' --region us-east-1

# Verify Subnets (should show 6)
aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].{Name:Tags[?Key==`Name`].Value|[0],CIDR:CidrBlock,AZ:AvailabilityZone}' --output table --region us-east-1
```

---

## Part 2: Data Tier — RDS MySQL (45 minutes)

### Step 2.1: Create DB Subnet Group

**Console:**
1. Navigate to **RDS** → **Subnet groups** → **Create DB subnet group**
2. Name: `workshop-db-subnet-group`
3. Description: Workshop DB subnet group
4. VPC: workshop-vpc
5. Add subnets: Select the 2 data subnets (`10.0.20.0/24` and `10.0.21.0/24`)
6. Click **Create**

**CLI:**
```bash
DATA_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-data-1" --query 'Subnets[0].SubnetId' --output text --region us-east-1)
DATA_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-data-2" --query 'Subnets[0].SubnetId' --output text --region us-east-1)

aws rds create-db-subnet-group \
  --db-subnet-group-name workshop-db-subnet-group \
  --db-subnet-group-description "Workshop DB subnet group" \
  --subnet-ids $DATA_SUBNET_1 $DATA_SUBNET_2 \
  --region us-east-1
```

### Step 2.2: Create RDS Security Group

**Console:**
1. Go to **VPC** → **Security Groups** → **Create security group**
2. Name: `workshop-rds-sg`
3. Description: RDS - Allow MySQL from ECS tasks only
4. VPC: workshop-vpc
5. Inbound rules: Add rule → MySQL/Aurora (3306) → Source: (we'll update after creating ECS SG)
6. Click **Create**

**CLI:**
```bash
RDS_SG=$(aws ec2 create-security-group --group-name workshop-rds-sg \
  --description "RDS - Allow MySQL from ECS only" \
  --vpc-id $VPC_ID --query 'GroupId' --output text --region us-east-1)

aws ec2 create-tags --resources $RDS_SG --tags Key=Name,Value=workshop-rds-sg --region us-east-1
```

> We'll add the inbound rule after creating the ECS security group (security group chaining).

### Step 2.3: Launch RDS Instance

**Console:**
1. Go to **RDS** → **Databases** → **Create database**
2. Configuration:
   - Engine: **MySQL 8.0**
   - Template: **Free tier** (or Dev/Test for Multi-AZ discussion)
   - DB instance identifier: `workshop-db`
   - Master username: `admin`
   - Master password: `WorkshopDB2026!` (choose your own)
   - Instance class: `db.t3.micro`
   - Storage: 20 GB, GP3
   - VPC: workshop-vpc
   - Subnet group: workshop-db-subnet-group
   - Public access: **No**
   - Security group: workshop-rds-sg
   - Database name: `cloudkida`
   - Enable encryption: ✅
   - Backup retention: 1 day
3. Click **Create database**

**CLI:**
```bash
aws rds create-db-instance \
  --db-instance-identifier workshop-db \
  --engine mysql \
  --engine-version 8.0 \
  --db-instance-class db.t3.micro \
  --allocated-storage 20 \
  --storage-type gp3 \
  --master-username admin \
  --master-user-password 'WorkshopDB2026!' \
  --db-name cloudkida \
  --vpc-security-group-ids $RDS_SG \
  --db-subnet-group-name workshop-db-subnet-group \
  --no-publicly-accessible \
  --storage-encrypted \
  --backup-retention-period 1 \
  --no-multi-az \
  --region us-east-1
```

> ⏳ RDS takes 5-10 minutes to create. Continue with the next steps while it provisions.

---

## Part 3: App Tier — ECS Fargate (90 minutes)

### Step 3.1: Create ECR Repository

**Console:**
1. Navigate to **ECR** → **Repositories** → **Create repository**
2. Repository name: `workshop-app`
3. Image scan on push: ✅ Enabled
4. Click **Create repository**

**CLI:**
```bash
aws ecr create-repository \
  --repository-name workshop-app \
  --image-scanning-configuration scanOnPush=true \
  --region us-east-1
```

### Step 3.2: Build and Push Docker Image

Open **AWS CloudShell** and run:

```bash
# Create app directory
mkdir -p ~/workshop-app && cd ~/workshop-app

# Create requirements.txt
cat > requirements.txt << 'EOF'
flask==3.0.3
flask-cors==4.0.1
mysql-connector-python==8.4.0
python-dotenv==1.0.1
gunicorn==22.0.0
EOF

# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
EOF

# Create app.py (Flask backend)
cat > app.py << 'PYEOF'
import os
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()
app = Flask(__name__)
CORS(app, origins=os.getenv('ALLOWED_ORIGINS', '*').split(','))

def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 3306)),
            database=os.getenv('DB_NAME', 'cloudkida'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', ''),
            connect_timeout=5
        )
    except Error as e:
        print(f"[DB ERROR] {e}")
        return None

def init_database():
    connection = get_db_connection()
    if not connection:
        return False
    try:
        cursor = connection.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS contacts (
            id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL,
            email VARCHAR(150) NOT NULL, subject VARCHAR(200) NOT NULL,
            message TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS visitors (
            id INT AUTO_INCREMENT PRIMARY KEY, ip_address VARCHAR(45),
            user_agent TEXT, page_visited VARCHAR(200),
            visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS labs (
            id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(200) NOT NULL,
            category VARCHAR(50) NOT NULL, duration VARCHAR(50),
            level VARCHAR(50), description TEXT, is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("SELECT COUNT(*) FROM labs")
        if cursor.fetchone()[0] == 0:
            labs = [('EC2 Instance Management','aws','45 mins','Beginner','Launch and manage EC2 instances.'),
                    ('S3 Website Hosting','aws','30 mins','Beginner','Host a static website on S3.'),
                    ('Linux Administration','linux','60 mins','Intermediate','Linux system admin commands.'),
                    ('Container Orchestration','docker','90 mins','Advanced','Docker containers and compose.'),
                    ('VPC Networking','aws','75 mins','Intermediate','VPC networking in AWS.'),
                    ('Kubernetes Basics','docker','120 mins','Advanced','K8s container management.')]
            cursor.executemany("INSERT INTO labs (title,category,duration,level,description) VALUES (%s,%s,%s,%s,%s)", labs)
        connection.commit()
        return True
    except Error as e:
        print(f"[DB ERROR] Init failed: {e}")
        return False
    finally:
        cursor.close()
        connection.close()

@app.route('/')
def home():
    return jsonify({'app':'CloudKida Workshop API','version':'2.0','status':'running'})

@app.route('/api/health')
def health():
    db_status = 'disconnected'
    conn = get_db_connection()
    if conn:
        db_status = 'connected'
        conn.close()
    return jsonify({'status':'healthy','version':'2.0','timestamp':datetime.utcnow().isoformat(),'database':db_status})

@app.route('/api/labs')
def get_labs():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error':'Database unavailable'}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM labs WHERE is_active = TRUE ORDER BY id")
        labs = cursor.fetchall()
        for lab in labs:
            if lab.get('created_at'):
                lab['created_at'] = lab['created_at'].isoformat()
        return jsonify({'labs':labs,'total':len(labs)})
    except Error as e:
        return jsonify({'error':str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/stats')
def get_stats():
    conn = get_db_connection()
    if not conn:
        return jsonify({'students_enrolled':1098,'labs_available':6,'database':'disconnected'})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM labs WHERE is_active = TRUE")
        labs_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM visitors")
        visitors_count = cursor.fetchone()[0]
        return jsonify({'students_enrolled':1098,'labs_available':labs_count,'total_visitors':visitors_count,'database':'connected'})
    except Error as e:
        return jsonify({'error':str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/contact', methods=['POST'])
def submit_contact():
    data = request.get_json()
    for field in ['name','email','subject','message']:
        if not data or not data.get(field):
            return jsonify({'error':f'Field "{field}" is required'}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({'error':'Database unavailable'}), 503
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO contacts (name,email,subject,message) VALUES (%s,%s,%s,%s)",
                      (data['name'],data['email'],data['subject'],data['message']))
        conn.commit()
        return jsonify({'message':'Thank you! We will get back to you soon.','id':cursor.lastrowid}), 201
    except Error as e:
        return jsonify({'error':str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error':'Not found'}), 404

if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
PYEOF

# Login to ECR
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t workshop-app .
docker tag workshop-app:latest $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/workshop-app:latest
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/workshop-app:latest

echo "✅ Image pushed successfully!"
echo "Image URI: $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/workshop-app:latest"
```

### Step 3.3: Create ECS Cluster

**Console:**
1. Navigate to **ECS** → **Clusters** → **Create cluster**
2. Cluster name: `workshop-cluster`
3. Infrastructure: **AWS Fargate (serverless)**
4. Click **Create**

**CLI:**
```bash
aws ecs create-cluster --cluster-name workshop-cluster \
  --settings name=containerInsights,value=enabled \
  --region us-east-1
```

### Step 3.4: Create ECS Task Execution Role

**Console:**
1. Go to **IAM** → **Roles** → **Create role**
2. Trusted entity: AWS service → **Elastic Container Service Task**
3. Attach policy: `AmazonECSTaskExecutionRolePolicy`
4. **Expand "Set permissions boundary"** → Select `workshop-permission-boundary`
5. Role name: `workshop-ecs-execution-role` or `ecsTaskExecutionRole`
6. Click **Create role**

> ⚠️ **Important:** You MUST set the permission boundary when creating roles. Without it, the role creation will be denied. The ECS Console may offer to auto-create `ecsTaskExecutionRole` — this will work as long as you set the permission boundary.

**CLI:**
```bash
# Create trust policy
cat > /tmp/ecs-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role --role-name workshop-ecs-execution-role \
  --assume-role-policy-document file:///tmp/ecs-trust-policy.json \
  --permissions-boundary arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/workshop-permission-boundary

aws iam attach-role-policy --role-name workshop-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

### Step 3.5: Create ECS Task Role

**Console:**
1. Go to **IAM** → **Roles** → **Create role**
2. Trusted entity: AWS service → **Elastic Container Service Task**
3. Skip attaching managed policies (we'll add inline policy)
4. **Expand "Set permissions boundary"** → Select `workshop-permission-boundary`
5. Role name: `workshop-ecs-task-role` or `ecsTaskRole`
6. Click **Create role**
7. Open the role → **Add permissions** → **Create inline policy** → JSON:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
    "Resource": "*"
  }]
}
```

**CLI:**
```bash
aws iam create-role --role-name workshop-ecs-task-role \
  --assume-role-policy-document file:///tmp/ecs-trust-policy.json \
  --permissions-boundary arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/workshop-permission-boundary

# Add CloudWatch Logs permission
cat > /tmp/task-role-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
    "Resource": "*"
  }]
}
EOF

aws iam put-role-policy --role-name workshop-ecs-task-role \
  --policy-name TaskLogsPolicy \
  --policy-document file:///tmp/task-role-policy.json
```

### Step 3.6: Create CloudWatch Log Group

```bash
aws logs create-log-group --log-group-name /ecs/workshop-app --region us-east-1
```

### Step 3.7: Create Task Definition

**Console:**
1. Go to **ECS** → **Task definitions** → **Create new task definition**
2. Configuration:
   - Family: `workshop-app`
   - Launch type: **Fargate**
   - CPU: 0.25 vCPU
   - Memory: 0.5 GB
   - Task execution role: `workshop-ecs-execution-role`
   - Task role: `workshop-ecs-task-role`
3. Container:
   - Name: `app`
   - Image URI: `<account-id>.dkr.ecr.us-east-1.amazonaws.com/workshop-app:latest`
   - Port: 5000
   - Environment variables:
     - `DB_HOST` = (your RDS endpoint)
     - `DB_PORT` = `3306`
     - `DB_NAME` = `cloudkida`
     - `DB_USER` = `admin`
     - `DB_PASSWORD` = `WorkshopDB2026!`
     - `PORT` = `5000`
   - Log configuration: awslogs → `/ecs/workshop-app`

**CLI:**
```bash
# Get RDS endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier workshop-db --query 'DBInstances[0].Endpoint.Address' --output text --region us-east-1)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > /tmp/task-definition.json << EOF
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
    "image": "${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/workshop-app:latest",
    "portMappings": [{"containerPort": 5000, "protocol": "tcp"}],
    "environment": [
      {"name": "DB_HOST", "value": "${RDS_ENDPOINT}"},
      {"name": "DB_PORT", "value": "3306"},
      {"name": "DB_NAME", "value": "cloudkida"},
      {"name": "DB_USER", "value": "admin"},
      {"name": "DB_PASSWORD", "value": "WorkshopDB2026!"},
      {"name": "PORT", "value": "5000"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/workshop-app",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "essential": true
  }]
}
EOF

aws ecs register-task-definition --cli-input-json file:///tmp/task-definition.json --region us-east-1
```

### Step 3.8: Create Security Groups for ECS

```bash
# Get VPC ID (if not already set)
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=workshop-vpc" --query 'Vpcs[0].VpcId' --output text --region us-east-1)

# Get RDS Security Group ID (created in Step 2.2)
RDS_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=workshop-rds-sg" --query 'SecurityGroups[0].GroupId' --output text --region us-east-1)

# ECS Security Group (allows traffic from ALB only)
ECS_SG=$(aws ec2 create-security-group --group-name workshop-ecs-sg \
  --description "ECS Tasks - Allow from ALB only" \
  --vpc-id $VPC_ID --query 'GroupId' --output text --region us-east-1)

aws ec2 create-tags --resources $ECS_SG --tags Key=Name,Value=workshop-ecs-sg --region us-east-1

# Now add RDS inbound rule from ECS SG
aws ec2 authorize-security-group-ingress --group-id $RDS_SG \
  --protocol tcp --port 3306 --source-group $ECS_SG --region us-east-1
```

---

## Part 4: Web Tier — Load Balancer (45 minutes)

### Step 4.1: Create ALB Security Group

```bash
# Get VPC ID and ECS SG (if not already set)
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=workshop-vpc" --query 'Vpcs[0].VpcId' --output text --region us-east-1)
ECS_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=workshop-ecs-sg" --query 'SecurityGroups[0].GroupId' --output text --region us-east-1)

ALB_SG=$(aws ec2 create-security-group --group-name workshop-alb-sg \
  --description "ALB - Allow HTTP from internet" \
  --vpc-id $VPC_ID --query 'GroupId' --output text --region us-east-1)

aws ec2 create-tags --resources $ALB_SG --tags Key=Name,Value=workshop-alb-sg --region us-east-1

# Allow HTTP from anywhere
aws ec2 authorize-security-group-ingress --group-id $ALB_SG \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region us-east-1

# Now add ECS inbound rule from ALB SG
aws ec2 authorize-security-group-ingress --group-id $ECS_SG \
  --protocol tcp --port 5000 --source-group $ALB_SG --region us-east-1
```

### Step 4.2: Create Application Load Balancer

**Console:**
1. Navigate to **EC2** → **Load Balancers** → **Create Load Balancer**
2. Type: **Application Load Balancer**
3. Name: `workshop-alb`
4. Scheme: Internet-facing
5. Listeners: HTTP (80)
6. VPC: workshop-vpc
7. Subnets: Both public subnets
8. Security group: workshop-alb-sg
9. Create Target Group:
   - Name: `workshop-tg`
   - Target type: **IP addresses**
   - Port: 5000
   - Health check path: `/api/health`
10. Click **Create**

**CLI:**
```bash
# Get public subnet IDs
PUB_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-public-1" --query 'Subnets[0].SubnetId' --output text --region us-east-1)
PUB_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-public-2" --query 'Subnets[0].SubnetId' --output text --region us-east-1)
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=workshop-vpc" --query 'Vpcs[0].VpcId' --output text --region us-east-1)
ALB_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=workshop-alb-sg" --query 'SecurityGroups[0].GroupId' --output text --region us-east-1)

# Create ALB
ALB_ARN=$(aws elbv2 create-load-balancer --name workshop-alb \
  --subnets $PUB_SUBNET_1 $PUB_SUBNET_2 \
  --security-groups $ALB_SG \
  --scheme internet-facing \
  --type application \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text --region us-east-1)

# Create Target Group
TG_ARN=$(aws elbv2 create-target-group --name workshop-tg \
  --protocol HTTP --port 5000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /api/health \
  --health-check-interval-seconds 30 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --query 'TargetGroups[0].TargetGroupArn' --output text --region us-east-1)

# Create Listener
aws elbv2 create-listener --load-balancer-arn $ALB_ARN \
  --protocol HTTP --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN \
  --region us-east-1
```

### Step 4.3: Create ECS Service

> ⚠️ **IMPORTANT: Use CLI (CloudShell) for this step.** The ECS Console uses CloudFormation internally to create services, which may fail due to permissions. Use the CLI method below instead — it works reliably.

**CLI (Recommended — use CloudShell):**
```bash
# Get subnet IDs
APP_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-app-1" --query 'Subnets[0].SubnetId' --output text --region us-east-1)
APP_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=workshop-private-app-2" --query 'Subnets[0].SubnetId' --output text --region us-east-1)

# Get security group ID
ECS_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=workshop-ecs-sg" --query 'SecurityGroups[0].GroupId' --output text --region us-east-1)

# Get target group ARN
TG_ARN=$(aws elbv2 describe-target-groups --names workshop-tg --query 'TargetGroups[0].TargetGroupArn' --output text --region us-east-1)

# Create the service
aws ecs create-service --cluster workshop-cluster \
  --service-name workshop-service \
  --task-definition workshop-app \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$APP_SUBNET_1,$APP_SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=app,containerPort=5000" \
  --region us-east-1
```

**Console (Alternative — only if CLI is not preferred):**
1. Go to **ECS** → **Clusters** → `workshop-cluster` → **Services** → **Create**
2. Configuration:
   - Launch type: Fargate
   - Task definition: workshop-app (latest)
   - Service name: `workshop-service`
   - Desired tasks: 1
   - Networking:
     - VPC: workshop-vpc
     - Subnets: Private app subnets
     - Security group: workshop-ecs-sg
     - Public IP: DISABLED
   - Load balancer:
     - Type: ALB
     - Select: workshop-alb
     - Container: app:5000
     - Target group: workshop-tg
3. Click **Create**

---

## Part 5: Verify & Test (30 minutes)

### Step 5.1: Get ALB URL

```bash
ALB_DNS=$(aws elbv2 describe-load-balancers --names workshop-alb --query 'LoadBalancers[0].DNSName' --output text --region us-east-1)
echo "Application URL: http://$ALB_DNS"
```

### Step 5.2: Test Endpoints

```bash
# Health check
curl http://$ALB_DNS/api/health

# Get labs
curl http://$ALB_DNS/api/labs

# Get stats
curl http://$ALB_DNS/api/stats

# Submit contact
curl -X POST http://$ALB_DNS/api/contact \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Student","email":"test@example.com","subject":"Workshop Test","message":"Hello from ECS!"}'
```

### Step 5.3: Verify Security Group Chain

```
Internet (0.0.0.0/0) → ALB SG (Port 80)
                              ↓
ALB SG → ECS SG (Port 5000)
                              ↓
ECS SG → RDS SG (Port 3306)
```

### Step 5.4: Check ECS Task Logs

```bash
# View recent logs
aws logs get-log-events --log-group-name /ecs/workshop-app \
  --log-stream-name $(aws logs describe-log-streams --log-group-name /ecs/workshop-app --order-by LastEventTime --descending --max-items 1 --query 'logStreams[0].logStreamName' --output text --region us-east-1) \
  --limit 20 --region us-east-1 --query 'events[*].message' --output text
```

---

## Discussion Points

### What happens if an AZ goes down?
- ALB routes traffic to healthy targets in the other AZ
- RDS failover (if Multi-AZ was enabled)
- ECS can launch tasks in the surviving AZ

### How to add caching?
- ElastiCache Redis between ECS and RDS
- Reduces database load for read-heavy workloads

### How to add CDN?
- CloudFront in front of ALB
- Caches static responses, reduces latency

---

## Cleanup

> ⚠️ **Important:** Delete resources in reverse order to avoid dependency errors.

```bash
# 1. Delete ECS Service
aws ecs update-service --cluster workshop-cluster --service workshop-service --desired-count 0 --region us-east-1
aws ecs delete-service --cluster workshop-cluster --service workshop-service --force --region us-east-1

# 2. Delete ALB resources
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN --region us-east-1
aws elbv2 delete-target-group --target-group-arn $TG_ARN --region us-east-1

# 3. Delete ECS Cluster
aws ecs delete-cluster --cluster workshop-cluster --region us-east-1

# 4. Delete RDS
aws rds delete-db-instance --db-instance-identifier workshop-db --skip-final-snapshot --region us-east-1

# 5. Delete NAT Gateway (costs money even when idle!)
aws ec2 delete-nat-gateway --nat-gateway-id $NAT_GW_ID --region us-east-1
aws ec2 release-address --allocation-id $ALLOC_ID --region us-east-1

# 6. Delete ECR repository
aws ecr delete-repository --repository-name workshop-app --force --region us-east-1

# 7. Delete VPC (after all resources are removed)
# Delete security groups, subnets, route tables, IGW, then VPC
```

---

## 🎉 Congratulations!

You have successfully built a production-style three-tier web application on AWS:
- ✅ VPC with multi-tier subnet architecture
- ✅ RDS MySQL database (encrypted, isolated)
- ✅ Containerized Flask API on ECS Fargate
- ✅ Application Load Balancer (public access)
- ✅ Security group chaining between all tiers
- ✅ CloudWatch Logs for container monitoring

**Tomorrow (Day 2):** We'll secure this architecture with WAF, encryption, secrets management, and monitoring!
