from django.contrib import admin
from .models import (
    AwardCycle, QuestionnaireTemplate, AssessmentCategory, Criterion, LevelIndicator,
    Questionnaire, Response, VerifierResponse, JudgeResponse,
)


@admin.register(AwardCycle)
class AwardCycleAdmin(admin.ModelAdmin):
    list_display = ("name", "year", "is_open", "created_at")
    list_filter = ("is_open", "year")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(QuestionnaireTemplate)
class QuestionnaireTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "assessment_profile", "cycle", "is_active")
    list_filter = ("cycle", "assessment_profile", "is_active")
    search_fields = ("name", "code", "assessment_profile")


@admin.register(AssessmentCategory)
class AssessmentCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "assessment_profile", "weight", "cycle", "is_active", "order")
    list_filter = ("cycle", "assessment_profile", "is_active")
    search_fields = ("code", "name", "assessment_profile")
    list_editable = ("weight", "is_active", "order")
    ordering = ("cycle", "assessment_profile", "order", "code")


@admin.register(Criterion)
class CriterionAdmin(admin.ModelAdmin):
    list_display = (
        "category", "number", "name", "area_code", "assessment_area",
        "assessment_criterion_code", "weight", "is_active", "order",
    )
    list_filter = ("category__cycle", "category__assessment_profile", "category", "is_active")
    search_fields = (
        "number", "name", "area_code", "assessment_area",
        "assessment_criterion_code", "assessment_criterion", "regulation",
        "category__code", "category__name",
    )
    list_editable = ("weight", "is_active", "order")
    ordering = ("category__order", "order", "number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LevelIndicator)
class LevelIndicatorAdmin(admin.ModelAdmin):
    """
    Organise level indicators by the assessment questionnaire they belong to.

    A level indicator belongs to a Criterion; the Criterion belongs to an
    AssessmentCategory, which identifies the assessment profile and cycle.
    This keeps indicators grouped with the correct questionnaire without
    duplicating questionnaire/profile data on LevelIndicator.
    """
    list_display = (
        "cycle", "assessment_profile", "category", "criterion",
        "level", "indicator",
    )
    list_filter = (
        "criterion__category__cycle",
        "criterion__category__assessment_profile",
        "criterion__category",
        "level",
    )
    search_fields = (
        "criterion__number",
        "criterion__name",
        "criterion__category__code",
        "criterion__category__name",
        "criterion__category__assessment_profile",
        "indicator",
    )
    ordering = (
        "criterion__category__cycle__year",
        "criterion__category__assessment_profile",
        "criterion__category__order",
        "criterion__order",
        "level",
    )
    list_select_related = (
        "criterion",
        "criterion__category",
        "criterion__category__cycle",
    )

    @admin.display(description="Assessment cycle", ordering="criterion__category__cycle__year")
    def cycle(self, obj):
        return obj.criterion.category.cycle

    @admin.display(description="Questionnaire / profile", ordering="criterion__category__assessment_profile")
    def assessment_profile(self, obj):
        return obj.criterion.category.assessment_profile or "Unassigned"

    @admin.display(description="Assessment category", ordering="criterion__category__order")
    def category(self, obj):
        return f"{obj.criterion.category.code} — {obj.criterion.category.name}".strip(" —")


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ("organization", "cycle", "is_submitted", "judging_completed", "is_distributed")
    list_filter = ("cycle", "is_submitted", "judging_completed", "is_distributed")
    search_fields = ("organization__name", "cycle__name")


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("questionnaire", "criterion", "score", "updated_at")
    list_filter = ("questionnaire__cycle", "criterion__category")
    search_fields = ("questionnaire__organization__name", "criterion__number", "criterion__name")


@admin.register(VerifierResponse)
class VerifierResponseAdmin(admin.ModelAdmin):
    list_display = ("questionnaire", "verifier", "criterion", "updated_at")
    list_filter = ("questionnaire__cycle", "criterion__category")
    search_fields = ("questionnaire__organization__name", "verifier__username", "criterion__number")


@admin.register(JudgeResponse)
class JudgeResponseAdmin(admin.ModelAdmin):
    list_display = ("questionnaire", "judge", "criterion", "score", "updated_at")
    list_filter = ("questionnaire__cycle", "criterion__category", "judge")
    search_fields = ("questionnaire__organization__name", "judge__username", "criterion__number", "criterion__name")
