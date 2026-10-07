# SentinelOps 🛡️

### Intelligent Industrial Service Operations Platform

**QR Machine → Digital Passport → Service Request → Validation → SLA/Readiness → Technician Matching → Manager Approval → Assignment**

## Why SentinelOps?

Most maintenance systems are **ticket-first**. SentinelOps is **machine-first**.

* 📱 **QR-driven:** Scan a machine to open its digital passport and service workflow.
* 🧠 **Validated requests:** Priority, readiness and SLA context are evaluated before assignment.
* 👨‍🔧 **Explainable matching:** Managers get **Best Fit, Fastest Recovery, and Least Disruptive** options.
* 👔 **Human-in-the-loop:** The system supports the manager; the manager makes the final decision.
* 🔐 **Role-based:** Customer, Technician, Supervisor, Manager and Admin have dedicated workspaces.

### What makes it innovative?

SentinelOps bridges the **factory floor and digital operations**. A QR code turns a physical asset into an actionable service workflow, while explainable matching helps managers balance **skill, speed and workload**.

> \\\*\\\*Identify the machine. Validate the problem. Understand the urgency. Find the right technician. Make the right decision.\\\*\\\*

## Demo Flow

```text
Customer
   ↓
M-104 Machine Passport / QR
   ↓
Raise Service Request
   ↓
Validation + SLA + Readiness
   ↓
Manager
   ↓
3 Matching Plans
   ↓
Best Fit
   ↓
Approve \\\& Assign
```

## Tech Stack

* **Frontend:** React + Vite
* **Backend:** Python + FastAPI
* **Database:** SQLite
* **Authentication:** JWT + bcrypt
* **Communication:** REST + WebSocket
* **Machine Identification:** QR-based Digital Passport

## Run Locally

### Backend

```bash
cd backend
python -m venv venv
venv\\\\Scripts\\\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`

## Deployment

Set the production frontend URL in the backend:

```env
FRONTEND\\\_URL=https://YOUR-FRONTEND-URL
```

Configure the frontend:

```env
VITE\\\_API\\\_URL=https://YOUR-BACKEND-URL/api
VITE\\\_WS\\\_URL=wss://YOUR-BACKEND-URL/api/ws
```

**Important:** Regenerate QR codes after deployment so they point to the deployed application instead of `localhost`.

## Test Credentials

|Role|Email|Password|
|-|-|-|
|Customer|`customer@apex.com`|`customer123`|
|Manager|`manager@sentinelops.com`|`manager123`|
|Supervisor|`supervisor@sentinelops.com`|`supervisor123`|
|Technician|`tech07@sentinelops.com`|`tech123`|
|Admin|`admin@sentinelops.com`|`admin123`|

## Hackathon

**DataQuest 3.0 — SentinelOps**

> \\\*\\\*From machine identification to intelligent service assignment — SentinelOps makes industrial maintenance faster, more structured, and more explainable.\\\*\\\*



