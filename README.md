# AWS Three-Tier Workshop Application

A full-stack web application for the **AWS Architecting & Security 2-Day Workshop**.

This application demonstrates a production-style three-tier architecture deployed on AWS ECS Fargate with RDS MySQL.

## Architecture

```
┌─────────────────────────────────────────┐
│        Application Load Balancer         │
│              (Port 80)                   │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│     ECS Fargate Container               │
│     ┌────────────────────────────┐      │
│     │  Flask API (Port 5000)     │      │
│     │  + Static Frontend         │      │
│     └────────────────────────────┘      │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│         RDS MySQL Database              │
│         (Port 3306)                     │
└─────────────────────────────────────────┘
```

## Repository Structure

```
├── Dockerfile              # Container image definition
├── buildspec.yml           # AWS CodeBuild specification
├── .env.example            # Environment variable template
├── backend/
│   ├── app.py              # Flask API application
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── index.html          # Main website page
│   └── assets/
│       ├── css/style.css   # Styles
│       └── js/main.js      # JavaScript
└── db/
    └── init_db.sql         # Database schema & seed data
```

## Quick Start (Local with Docker)

```bash
# Build the image
docker build -t workshop-app .

# Run without database (API-only mode)
docker run -p 5000:5000 workshop-app

# Run with database
docker run -p 5000:5000 \
  -e DB_HOST=host.docker.internal \
  -e DB_PORT=3306 \
  -e DB_NAME=cloudkida \
  -e DB_USER=admin \
  -e DB_PASSWORD=your-password \
  workshop-app
```

Open http://localhost:5000 for the frontend, or http://localhost:5000/api/health for the API.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Frontend website |
| GET | `/api/health` | Health check (includes DB status) |
| GET | `/api/info` | Application information |
| GET | `/api/labs` | List all labs |
| POST | `/api/labs` | Create a new lab |
| GET | `/api/stats` | Platform statistics |
| POST | `/api/contact` | Submit contact form |
| GET | `/api/contacts` | List contacts (admin) |
| POST | `/api/visitors` | Track page visit |
| GET | `/api/visitors/count` | Total visitor count |
| POST | `/api/feedback` | Submit lab feedback |

## Database Setup

Connect to your RDS instance and run the initialization script:

```bash
mysql -h <rds-endpoint> -u admin -p < db/init_db.sql
```

Or let the application auto-initialize tables on first startup (seed data won't be inserted via auto-init, only table creation).

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | RDS endpoint | localhost |
| `DB_PORT` | MySQL port | 3306 |
| `DB_NAME` | Database name | cloudkida |
| `DB_USER` | Database username | admin |
| `DB_PASSWORD` | Database password | (required) |
| `PORT` | Application port | 5000 |
| `ALLOWED_ORIGINS` | CORS origins | * |
| `FLASK_ENV` | Flask environment | production |

## Deploying to ECS

1. Create ECR repository
2. Build and push Docker image:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
   docker build -t <account-id>.dkr.ecr.us-east-1.amazonaws.com/workshop-app:latest .
   docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/workshop-app:latest
   ```
3. Create ECS task definition with environment variables pointing to RDS
4. Create ECS service behind an ALB

## Workshop Usage

This repository is used in the **AWS Architecting & Security 2-Day Workshop**:
- **Day 1:** Students build the VPC, RDS, ECS, and ALB infrastructure, then deploy this app
- **Day 2:** Students secure the deployed architecture with WAF, KMS, Secrets Manager, etc.
