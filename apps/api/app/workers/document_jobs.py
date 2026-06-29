from app.db.session import SessionLocal
from app.models.document import MedicalDocument
from app.models.jobs import IngestionJob
from app.rag.clinical_timeline import build_document_timeline_context, extract_document_clinical_datetime, infer_lab_group
from app.rag.indexer import MedicalVectorIndexer
from app.services.image_embedding_service import BioMedClipImageIndexer
from app.services.malware_service import MalwareScanner
from app.services.medical_image_service import MedicalImageService
from app.services.ocr_service import OcrService
from app.services.storage_service import ObjectStorageService


def process_document_pipeline(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if job is None:
            return
        doc = db.get(MedicalDocument, job.document_id)
        if doc is None:
            job.status = "failed"
            job.error = "Document not found"
            db.commit()
            return

        job.status = "running"
        job.attempts += 1
        db.commit()

        if job.job_type == "document_rag_ingest":
            verified_for_rag = (
                doc.verified_by_patient
                or doc.image_review_status == "clinician_verified"
            )
            if not verified_for_rag or not doc.verified_text:
                job.status = "failed"
                job.error = "Document is not verified for RAG ingestion"
                doc.status = "rag_verification_required"
                db.commit()
                return
            indexer = MedicalVectorIndexer()
            indexed = indexer.index_verified_document(
                document_id=doc.id,
                patient_id=doc.patient_id,
                title=doc.original_filename,
                text=doc.verified_text,
                document_type=doc.document_type,
                source_created_at=extract_document_clinical_datetime(doc).isoformat(),
                clinical_context=build_document_timeline_context(db, doc).as_payload(),
            )
            doc.ingested_to_rag = indexed > 0
            doc.status = "rag_ingested" if indexed > 0 else "ingestion_failed"
            job.status = "completed" if indexed > 0 else "failed"
            if indexed <= 0:
                job.error = "No chunks were indexed into RAG"
            db.commit()
            if doc.document_type == "lab_report" and indexed > 0:
                _refresh_related_lab_report_timelines(db=db, changed_doc=doc, indexer=indexer)
            return

        content = ObjectStorageService().get_bytes(bucket=doc.storage_bucket, key=doc.storage_key)
        malware_status = MalwareScanner().scan_bytes(content)
        doc.malware_status = malware_status
        if malware_status != "clean":
            doc.status = "blocked"
            job.status = "failed"
            job.error = f"Malware scan status: {malware_status}"
            db.commit()
            return

        ocr_result = OcrService().extract(
            content,
            mime_type=doc.mime_type,
            document_type=doc.document_type,
            filename=doc.original_filename,
        )
        doc.ocr_text = ocr_result.text
        doc.ocr_engine = ocr_result.engine
        doc.ocr_confidence = f"{ocr_result.confidence:.3f}"
        doc.ocr_review_status = ocr_result.review_status
        doc.ocr_handwriting_detected = ocr_result.handwriting_detected
        doc.ocr_warning = ocr_result.warning
        image_service = MedicalImageService()
        if image_service.requires_clinician_review(
            mime_type=doc.mime_type,
            document_type=doc.document_type,
        ):
            doc.image_modality = image_service.classify_modality(
                filename=doc.original_filename,
                document_type=doc.document_type,
                mime_type=doc.mime_type,
            )
            doc.image_ai_observations = image_service.analyze_image(
                image_bytes=content,
                mime_type=doc.mime_type,
                modality=doc.image_modality,
                filename=doc.original_filename,
            )
            embedding = BioMedClipImageIndexer().index_image(
                document_id=doc.id,
                patient_id=doc.patient_id,
                image_bytes=content,
                mime_type=doc.mime_type,
                filename=doc.original_filename,
                modality=doc.image_modality,
            )
            doc.image_embedding_status = embedding.status
            doc.image_embedding_model = embedding.model
            doc.image_vector_id = embedding.vector_id
            doc.image_review_status = "clinician_review_required"
            doc.status = "image_ready_for_clinician_review"
        else:
            if ocr_result.review_status == "handwriting_human_transcription_required":
                doc.status = "handwriting_review_required"
            elif ocr_result.review_status == "ocr_dependency_missing":
                doc.status = "ocr_dependency_missing"
            elif ocr_result.review_status in {
                "low_confidence_human_verification_required",
                "ocr_failed",
            }:
                doc.status = "ocr_human_verification_required"
            else:
                doc.status = "ocr_ready_for_verification"
                doc.verified_text = ocr_result.text
                doc.verified_by_patient = True
        job.status = "completed"
        db.commit()
        if doc.verified_by_patient and doc.verified_text and not doc.ingested_to_rag:
            ingest_job = IngestionJob(
                id=f"rag-{doc.id}",
                document_id=doc.id,
                patient_id=doc.patient_id,
                job_type="document_rag_ingest",
                status="queued",
            )
            db.merge(ingest_job)
            db.commit()
            process_document_pipeline(ingest_job.id)
    except Exception as exc:
        if "job" in locals() and job is not None:
            job.status = "failed"
            job.error = str(exc)
            try:
                doc = db.get(MedicalDocument, job.document_id)
                if doc is not None:
                    if job.job_type == "document_rag_ingest":
                        doc.status = "ingestion_failed"
                        doc.ingested_to_rag = False
                    else:
                        doc.status = "ocr_failed"
                    doc.ocr_warning = f"Ingestion error: {str(exc)}"
            except Exception:
                pass
            db.commit()
        raise
    finally:
        db.close()


def _refresh_related_lab_report_timelines(
    *,
    db,
    changed_doc: MedicalDocument,
    indexer: MedicalVectorIndexer,
) -> None:
    changed_groups = _lab_groups(changed_doc)
    if not changed_groups:
        return
    related_docs = (
        db.query(MedicalDocument)
        .filter(
            MedicalDocument.patient_id == changed_doc.patient_id,
            MedicalDocument.document_type == "lab_report",
            MedicalDocument.id != changed_doc.id,
            MedicalDocument.status != "deleted_by_patient",
            MedicalDocument.verified_text != "",
        )
        .all()
    )
    for related in related_docs:
        if not (changed_groups & _lab_groups(related)):
            continue
        indexed = indexer.index_verified_document(
            document_id=related.id,
            patient_id=related.patient_id,
            title=related.original_filename,
            text=related.verified_text,
            document_type=related.document_type,
            source_created_at=extract_document_clinical_datetime(related).isoformat(),
            clinical_context=build_document_timeline_context(db, related).as_payload(),
        )
        related.ingested_to_rag = indexed > 0
        related.status = "rag_ingested" if indexed > 0 else "ingestion_failed"
    db.commit()


def _lab_groups(doc: MedicalDocument) -> set[str]:
    groups = infer_lab_group(f"{doc.original_filename}\n{doc.verified_text or doc.ocr_text}".lower())
    return {group for group in groups.split("+") if group}
