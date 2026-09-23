from django.contrib import admin
from .models import (
    AwardCycle, AssessmentCategory, Criterion, LevelIndicator,
    Questionnaire, Response, VerifierResponse, JudgeResponse,
)

admin.site.register(AwardCycle)
admin.site.register(AssessmentCategory)
admin.site.register(Criterion)
admin.site.register(LevelIndicator)
admin.site.register(Questionnaire)
admin.site.register(Response)
admin.site.register(VerifierResponse)
admin.site.register(JudgeResponse)
