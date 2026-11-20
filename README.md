# Agentic FacilityOps AI Platform – Energy Intelligence & Monitoring

An enterprise-grade, agentic AI platform designed for facility operations, intelligent energy monitoring, anomaly detection, automated root-cause analysis, and autonomous optimization recommendations.

---

## 🎯 Project Overview

Modern commercial and industrial facilities generate continuous telemetry across electrical meters, HVAC systems, chillers, and submeters. The **Agentic FacilityOps AI Platform** combines automated time-series data pipelines, statistical and machine learning models, and autonomous multi-agent reasoning to provide real-time visibility, early anomaly alerts, and actionable energy-saving recommendations.

---

## 🛠️ Technology Stack (Milestone 1)

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | React.js (Vite) | High-performance, reactive operational dashboard and intelligence portal |
| **Backend** | Python FastAPI | Asynchronous, modular REST API and backend orchestration layer |
| **Database** | PostgreSQL + SQLAlchemy | Relational persistence, facility metadata, time-series telemetry, and audit logs |
| **AI Orchestration** | LangGraph & LangChain | Stateful multi-agent reasoning, diagnostic graphs, and automated facility workflows |
| **Machine Learning** | Scikit-learn | Baseline energy modeling, anomaly detection (e.g., Isolation Forest), and regression |
| **Data Processing** | Pandas & NumPy | High-throughput telemetry ingestion, windowing, aggregation, and feature transformations |

---

## 📁 Repository Structure

```text
facilityops-ai/
├── .gitignore                      # Git ignore rules for Python, Node.js, venvs, and secrets
├── README.md                       # Comprehensive platform documentation
├── backend/                        # Backend service root
│   ├── .env.example                # Template for backend environment variables
│   ├── requirements.txt            # Python dependencies (FastAPI, SQLAlchemy, LangGraph, etc.)
│   └── app/                        # Application package
│       ├── __init__.py             # App package initialization
│       ├── config.py               # Pydantic environment settings configuration
│       ├── main.py                 # FastAPI application entrypoint & middleware setup
│       ├── agents/                 # LangGraph workflows and autonomous agents
│       │   └── __init__.py
│       ├── database/               # Database connection, session management, and Base models
│       │   └── __init__.py
│       ├── ml/                     # ML models, feature engineering, and anomaly detectors
│       │   └── __init__.py
│       ├── models/                 # SQLAlchemy ORM models and Pydantic schemas
│       │   └── __init__.py
│       ├── routes/                 # FastAPI routers and REST endpoints
│       │   └── __init__.py
│       └── services/               # Core business logic and analytics services
│           └── __init__.py
└── frontend/                       # Frontend application root (React + Vite)
    ├── .env.example                # Template for frontend environment variables
    ├── index.html                  # HTML entry document
    ├── package.json                # Frontend package configuration and scripts
    ├── vite.config.js              # Vite configuration and backend API proxy
    ├── public/                     # Static assets
    └── src/                        # Source code
        ├── App.css                 # Root component styles
        ├── App.jsx                 # Main application view
        ├── index.css               # Global CSS styling
        ├── main.jsx                # React DOM mounting entry point
        ├── components/             # Reusable UI widgets and monitoring cards
        └── services/               # API clients and data-fetching helpers
```

---

## 🏛️ Directory Purpose & Architectural Responsibilities

### Backend (`/backend`)
- **`app/main.py`**: Initializes the FastAPI app instance, registers CORS middleware, attaches global routers, and exposes service health checks.
- **`app/config.py`**: Manages environment-driven configurations (database connection strings, LLM keys, API prefixes) using Pydantic Settings.
- **`app/database/`**: Handles the database engine, SQLAlchemy session factory (`get_db` dependency), and declarative base definitions.
- **`app/models/`**: Defines SQLAlchemy ORM database models (facilities, meters, energy readings, alerts) and data validation schemas.
- **`app/routes/`**: Houses versioned API endpoints grouped by domain (e.g., telemetry ingestion, anomaly reports, agent queries).
- **`app/services/`**: Encapsulates business logic, analytical computations, and interactions between routes, ML models, and the database.
- **`app/agents/`**: Houses LangGraph state machines, multi-agent reasoning loops, and decision tools that triage anomalies and formulate recommendations.
- **`app/ml/`**: Implements Scikit-learn pipelines for baseline consumption modeling, drift detection, and automated anomaly classification.

### Frontend (`/frontend`)
- **`src/`**: Houses the React application source code.
  - **`components/`**: Modular, reusable UI components (time-series charts, KPI widgets, alert badges).
  - **`services/`**: Client-side API service wrappers interacting with the FastAPI backend.
- **`vite.config.js`**: Configures Vite build tooling and development proxy forwarding `/api` requests to the FastAPI backend.

---

## 🚀 Getting Started (Step-by-Step)

### 1. Prerequisites
- **Python**: 3.11+
- **Node.js**: 18+ (Node 22 LTS recommended)
- **PostgreSQL**: 15+ (local or containerized)

### 2. Backend Setup
1. Open a terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux/macOS
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   ```bash
   cp .env.example .env
   # Update .env with your PostgreSQL credentials and API keys
   ```
5. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   API interactive documentation will be accessible at: `http://localhost:8000/docs`

### 3. Frontend Setup
1. Open a terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Configure frontend environment variables:
   ```bash
   cp .env.example .env
   ```
3. Install dependencies:
   ```bash
   npm install
   ```
4. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The web application will be accessible at: `http://localhost:5173`

---

## 📋 Implementation Roadmap

- [x] **Milestone 1 - Step 1: Initial Architecture & Scaffolding** (Completed)
- [ ] **Milestone 1 - Step 2: Database Schema & SQLAlchemy Models** (Facility, Meter, Telemetry, Anomalies)
- [ ] **Milestone 1 - Step 3: Data Ingestion & Preprocessing Services** (Pandas & NumPy pipelines)
- [ ] **Milestone 1 - Step 4: Machine Learning Anomaly Detection** (Scikit-learn baseline & isolation algorithms)
- [ ] **Milestone 1 - Step 5: LangGraph Multi-Agent Orchestration** (Reasoning, triage, and recommendation workflows)
- [ ] **Milestone 1 - Step 6: FastAPI REST Endpoints** (Data querying, alert streaming, and agent endpoints)
- [ ] **Milestone 1 - Step 7: Frontend Operational Dashboard** (Vite + React UI integration)
