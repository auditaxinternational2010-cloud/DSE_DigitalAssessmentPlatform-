from django import forms
from .models import AwardCycle, Criterion, Response, VerifierResponse


class CycleForm(forms.ModelForm):
    class Meta:
        model = AwardCycle
        fields = ['year', 'name', 'excel_file']
        widgets = {
            'year': forms.NumberInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'excel_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'}),
        }


class BulkResponseForm(forms.Form):
    """Member response form matching the DSE workbook.

    Member enters Response only. Secretariat owns Remarks and evidence. Judges
    own Score/Comments. This keeps the workflow unchanged while matching the
    workbook columns.
    """
    def __init__(self, *args, category=None, questionnaire=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not category or not questionnaire:
            return
        criteria = list(category.criteria.filter(is_active=True).order_by('order', 'number'))
        existing_map = {
            r.criterion_id: r
            for r in Response.objects.filter(questionnaire=questionnaire, criterion__in=criteria)
        }
        for criterion in criteria:
            existing = existing_map.get(criterion.id)
            self.fields[f'response_{criterion.id}'] = forms.CharField(
                required=False,
                label=criterion.name,
                widget=forms.Textarea(attrs={
                    'class': 'form-control', 'rows': 4,
                    'placeholder': 'Enter your response to this measurable parameter.',
                }),
                initial=existing.response if existing else '',
            )


class VerifierScoreForm(forms.Form):
    """Secretariat notes form. Secretariat never enters a score."""
    def __init__(self, *args, category=None, questionnaire=None, verifier=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not category or not questionnaire:
            return
        criteria = list(category.criteria.filter(is_active=True).order_by('order', 'number'))
        existing_map = {
            vr.criterion_id: vr
            for vr in VerifierResponse.objects.filter(
                questionnaire=questionnaire, verifier=verifier, criterion__in=criteria
            )
        }
        for criterion in criteria:
            existing = existing_map.get(criterion.id)
            self.fields[f'notes_{criterion.id}'] = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={
                    'class': 'form-control', 'rows': 3,
                    'placeholder': 'Secretariat remarks for this measurable parameter.',
                }),
                initial=existing.notes if existing else '',
            )


class JudgeExcelForm(forms.Form):
    excel_attachment = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'input', 'accept': '.xlsx,.xls',
        }),
    )
