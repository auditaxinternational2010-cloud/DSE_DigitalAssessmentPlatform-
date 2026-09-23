from accounts.models import VerifierAssignment


def can_access_document(user, document):
    """Whether `user` may preview or download `document`."""
    if not user.is_authenticated:
        return False
    profile = getattr(user, 'userprofile', None)
    if profile is None:
        return False
    if profile.role == 'admin':
        return True
    if profile.role == 'member':
        return profile.organization_id == document.organization_id
    if profile.role == 'verifier':
        is_assigned = VerifierAssignment.objects.filter(
            verifier=user, organization_id=document.organization_id
        ).exists()
        if not is_assigned:
            return False
        return document.evidence_links.filter(
            response__questionnaire__organization_id=document.organization_id
        ).exists()
    if profile.role == 'judge':
        # Judges may view evidence attached to questionnaires they are judging.
        return document.evidence_links.filter(
            response__questionnaire__is_submitted=True,
            response__questionnaire__organization_id=document.organization_id,
        ).exists()
    return False
