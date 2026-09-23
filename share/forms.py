from django import forms

from .models import ShareLink


class ShareLinkForm(forms.ModelForm):
    class Meta:
        model = ShareLink
        fields = ['label', 'include_contacts', 'expires_at']
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'e.g. Board of Directors',
            }),
            'expires_at': forms.DateTimeInput(attrs={
                'class': 'input',
                'type': 'datetime-local',
            }),
        }
        labels = {
            'label': 'Who is this link for?',
            'include_contacts': 'Include member contact details (name, position, phone, email)',
            'expires_at': 'Expires at (optional)',
        }
