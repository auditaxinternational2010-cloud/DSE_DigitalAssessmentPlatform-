import os


def backfill_library(LibraryDocument, DocumentVersion, EvidenceLink, EvidenceUpload):
    """Convert every EvidenceUpload into a library document version + link.

    Reuses the existing storage key (no file copy). Dedups identical
    filename+size+path within an organization to a single version.
    Idempotent: pre-populates seen from existing DocumentVersion rows.
    """
    seen = {}
    # Pre-populate seen from any versions already created (idempotency on double-run).
    for version in DocumentVersion.objects.select_related(
            'document__organization').all():
        org_id = version.document.organization_id
        k = (org_id, version.original_filename, version.file_size, version.file.name)
        seen.setdefault(k, version)

    for upload in EvidenceUpload.objects.select_related(
            'response__questionnaire__organization').iterator(chunk_size=500):
        org = upload.response.questionnaire.organization
        filename = os.path.basename(upload.file.name)
        key = (org.id, filename, upload.file_size, upload.file.name)
        version = seen.get(key)
        if version is None:
            doc = LibraryDocument.objects.create(organization=org, title=filename)
            version = DocumentVersion(
                document=doc, version_number=1,
                file_size=upload.file_size, original_filename=filename)
            version.file.name = upload.file.name   # reuse exact S3 key, no copy
            version.save()
            seen[key] = version
        EvidenceLink.objects.get_or_create(
            response=upload.response, document_version=version)
