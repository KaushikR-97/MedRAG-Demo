# MedRAG Demo

MedRAG Demo is a healthcare application prototype with a FastAPI backend and a React TypeScript frontend. It includes workflows for patient onboarding, clinician support, hospital scheduling, document intake, consent-aware access, audit trails, care coordination, and retrieval-oriented clinical assistance.

## Repository Layout

```text
apps/
  api/   Backend application, service layer, database models, API routes, and migrations
  web/   Frontend application built with React and TypeScript
```

## High-Level Architecture

MedRAG Demo is organized as a two-tier application with supporting data and retrieval services:

- The frontend provides patient, doctor, hospital, document, consultation, and care-coordination workflows.
- The backend exposes FastAPI route modules for authentication, clinical assistance, hospital scheduling, document handling, compliance, public-health features, and shared patient/clinician actions.
- The service layer contains the core business logic for consent checks, audit events, document processing, retrieval, clinical generation, safety policy, communications, hospital workflows, and care-agent actions.
- The database layer uses PostgreSQL with SQLAlchemy models and Alembic migrations for users, patient profiles, medical documents, consent grants, audit events, appointments, hospital resources, answer traces, and feature-specific records.
- The retrieval layer uses Qdrant for vector search and combines indexed clinical or patient-approved context with query routing, rewriting, ranking, evidence preparation, and source-aware response generation.
- The model layer is designed around BioMistral as the clinical LLM, with support for QLoRA-based fine-tuning and adapter loading for domain-specific response behavior.
- Background workers support longer-running document workflows such as malware checks, OCR, extraction, indexing, and status updates.

## RAG And Model Pipeline

- Source documents are prepared for retrieval through the ingestion code in `apps/api/training/ingest_rag_sources.py`.
- Text is chunked, embedded, and written into Qdrant-backed collections for retrieval.
- Clinical questions are routed through the backend safety and retrieval workflow before generation.
- Retrieved evidence is ranked and passed into the generation layer so responses can be grounded in selected context.
- BioMistral can be used as the local base model, and `apps/api/training/train_lora.py` shows the QLoRA fine-tuning path for producing a domain adapter.
- Fine-tuning helper scripts are included under `apps/api/training`; datasets and medical sample files are intentionally not included.

## High-Level Workflow

1. A user enters through the web app as a patient, clinician, or hospital user.
2. The backend authenticates the user and applies role-aware access rules before returning or modifying records.
3. Patient onboarding and document upload workflows store metadata, queue document processing, and create audit entries.
4. Document processing extracts text or structured findings, marks review states, and indexes verified content for retrieval when appropriate.
5. Clinical questions pass through safety and policy checks before retrieval or generation runs.
6. The retrieval workflow decides which sources are needed, gathers relevant context, ranks evidence, and prepares source-grounded inputs.
7. The response layer generates patient-education or clinician-support output according to role, consent, and safety policy.
8. Clinical interactions are logged through answer traces and audit events so access and generated outputs remain reviewable.
9. Appointment, hospital, reminder, family, consent, and care-agent workflows use the same API/service/model pattern and share the audit and compliance boundaries.

## Included

- Backend API source code
- Frontend source code
- Database models and migration files
- RAG ingestion and QLoRA fine-tuning scripts
- Application configuration files needed for the demo codebase

## Not Included

- Medical datasets
- Training datasets
- Evaluation datasets
- Test fixtures
- Deployment guides
- Architecture documents
- Internal implementation notes
