from django import forms
from django.contrib.auth.models import User
from django.db import transaction

from .models import Organization, UserProfile, VerifierAssignment, ParticipationRequest, ORG_TYPE_SUBTYPES
from .validators import validate_tanzanian_phone


def validate_org_subtype(org_type, org_subtype, org_subtype_other):
    """Returns list of (field_name, error_message) tuples."""
    errors = []
    if org_type == 'informal_sector':
        if org_subtype:
            errors.append(('org_subtype', 'Informal Sector does not have subtypes.'))
        return errors
    if not org_subtype:
        errors.append(('org_subtype', 'Please select a subtype.'))
        return errors
    valid_slugs = {slug for slug, _ in ORG_TYPE_SUBTYPES.get(org_type, [])}
    if org_subtype not in valid_slugs:
        errors.append(('org_subtype', 'Invalid subtype for the selected organization type.'))
        return errors
    if org_subtype == 'other' and not org_subtype_other.strip():
        errors.append(('org_subtype_other', 'Please describe your subtype.'))
    return errors


class ProfileForm(forms.ModelForm):
    phone_number = forms.CharField(max_length=30, required=False, validators=[validate_tanzanian_phone])

    class Meta:
        model = User
        fields = ['first_name', 'last_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                self.fields['phone_number'].initial = self.instance.userprofile.phone_number
            except UserProfile.DoesNotExist:
                pass

    def save(self, commit=True):
        user = super().save(commit=commit)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone_number = self.cleaned_data['phone_number']
        profile.save(update_fields=['phone_number'])
        return user


class UserCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(), required=False,
        help_text='Required for Member role.'
    )
    verifier_orgs = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Select organizations this Secretariat is assigned to.'
    )
    phone_number = forms.CharField(max_length=30, required=False, validators=[validate_tanzanian_phone])

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        org = cleaned.get('organization')
        if role == 'member' and not org:
            self.add_error('organization', 'Organization is required for member role.')
        if role == 'member' and org:
            existing = UserProfile.objects.filter(role='member', organization=org).first()
            if existing:
                self.add_error('organization', f'"{org.name}" already has a member: {existing.user.username}.')
        return cleaned

    def save(self):
        data = self.cleaned_data
        with transaction.atomic():
            user = User.objects.create_user(
                username=data['username'],
                password=data['password'],
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                email=data.get('email', ''),
            )
            UserProfile.objects.create(
                user=user,
                role=data['role'],
                organization=data.get('organization') if data['role'] == 'member' else None,
                phone_number=data.get('phone_number', ''),
            )
            if data['role'] == 'verifier':
                for org in data.get('verifier_orgs', []):
                    VerifierAssignment.objects.get_or_create(verifier=user, organization=org)
        return user


class UserEditForm(forms.ModelForm):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    organization = forms.ModelChoiceField(queryset=Organization.objects.all(), required=False)
    verifier_orgs = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    phone_number = forms.CharField(max_length=30, required=False, validators=[validate_tanzanian_phone])

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                profile = self.instance.userprofile
                self.fields['role'].initial = profile.role
                self.fields['organization'].initial = profile.organization
                self.fields['phone_number'].initial = profile.phone_number
                self.fields['verifier_orgs'].initial = Organization.objects.filter(
                    verifier_assignments__verifier=self.instance
                )
            except UserProfile.DoesNotExist:
                pass

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        org = cleaned.get('organization')
        if role == 'member' and org:
            existing = UserProfile.objects.filter(
                role='member', organization=org
            ).exclude(user=self.instance).first()
            if existing:
                self.add_error('organization', f'"{org.name}" already has a member: {existing.user.username}.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=commit)
        data = self.cleaned_data
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = data['role']
        profile.organization = data.get('organization') if data['role'] == 'member' else None
        profile.phone_number = data.get('phone_number', '')
        profile.save()
        if data['role'] == 'verifier':
            VerifierAssignment.objects.filter(verifier=user).delete()
            for org in data.get('verifier_orgs', []):
                VerifierAssignment.objects.create(verifier=user, organization=org)
        else:
            # Clear any stale verifier assignments if role changed away from verifier
            VerifierAssignment.objects.filter(verifier=user).delete()
        return user


class OrgForm(forms.ModelForm):
    member = forms.ModelChoiceField(
        queryset=User.objects.filter(userprofile__role='member').select_related('userprofile'),
        required=False,
        help_text='Assign a member user to this organization.',
    )
    verifiers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(userprofile__role='verifier').select_related('userprofile'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Secretariat',
        help_text='Assign Secretariat user(s) to this organization.',
    )
    org_subtype = forms.CharField(required=False, widget=forms.HiddenInput())
    org_subtype_other = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Organization
        fields = [
            'name', 'org_type', 'assessment_profile', 'org_subtype', 'org_subtype_other', 'region',
            'physical_address', 'postal_address',
            'num_employees', 'investment_capital',
            'description', 'is_active', 'requires_judging',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'org_type': forms.Select(attrs={'class': 'form-control'}),
            'assessment_profile': forms.Select(attrs={'class': 'form-control'}),
            'region': forms.TextInput(attrs={'class': 'form-control'}),
            'physical_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'postal_address': forms.TextInput(attrs={'class': 'form-control'}),
            'num_employees': forms.Select(attrs={'class': 'form-control'}),
            'investment_capital': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            current_member = UserProfile.objects.filter(
                role='member', organization=self.instance
            ).select_related('user').first()
            if current_member:
                self.fields['member'].initial = current_member.user
            self.fields['verifiers'].initial = User.objects.filter(
                verifier_assignments__organization=self.instance
            )

    def clean(self):
        cleaned = super().clean()
        member = cleaned.get('member')
        verifiers = cleaned.get('verifiers') or []
        # Member cannot also be a verifier for the same org
        if member and member in verifiers:
            self.add_error('verifiers', f'{member.username} is set as the member and cannot also be a verifier.')
        # Member must not already belong to a different org
        if member:
            try:
                profile = member.userprofile
                if profile.organization and profile.organization != self.instance:
                    self.add_error('member', f'{member.username} is already a member of "{profile.organization.name}".')
            except UserProfile.DoesNotExist:
                pass
        for field, msg in validate_org_subtype(
            cleaned.get('org_type', ''),
            cleaned.get('org_subtype', ''),
            cleaned.get('org_subtype_other', ''),
        ):
            self.add_error(field, msg)
        return cleaned

    def save(self, commit=True):
        org = super().save(commit=commit)
        data = self.cleaned_data

        # Update member assignment
        # Clear previous member for this org
        UserProfile.objects.filter(role='member', organization=org).update(organization=None)
        new_member = data.get('member')
        if new_member:
            try:
                profile = new_member.userprofile
                profile.organization = org
                profile.save()
            except UserProfile.DoesNotExist:
                UserProfile.objects.create(user=new_member, role='member', organization=org)

        # Update verifier assignments
        VerifierAssignment.objects.filter(organization=org).delete()
        for verifier in data.get('verifiers') or []:
            VerifierAssignment.objects.get_or_create(verifier=verifier, organization=org)

        return org


class ParticipationRequestForm(forms.ModelForm):
    # Honeypot: hidden from humans via CSS, left blank by them. Bots that fill
    # every field will populate it — the view treats a non-empty value as spam.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'tabindex': '-1'}),
        label='Website',
    )
    phone_number = forms.CharField(
        max_length=30, required=False,
        validators=[validate_tanzanian_phone],
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'e.g. 0712345678'}),
    )
    org_subtype = forms.CharField(required=False, widget=forms.HiddenInput())
    org_subtype_other = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ParticipationRequest
        fields = [
            'org_name', 'org_type', 'org_subtype', 'org_subtype_other', 'region',
            'physical_address', 'postal_address',
            'num_employees', 'investment_capital',
            'first_name', 'last_name', 'position', 'phone_number', 'email',
        ]
        widgets = {
            'org_name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Full registered name'}),
            'org_type': forms.Select(attrs={'class': 'input'}),
            'region': forms.TextInput(attrs={'class': 'input', 'placeholder': 'e.g. Dar es Salaam'}),
            'physical_address': forms.Textarea(attrs={'class': 'input', 'rows': 2}),
            'postal_address': forms.TextInput(attrs={'class': 'input', 'placeholder': 'e.g. P.O. Box 100'}),
            'num_employees': forms.Select(attrs={'class': 'input'}),
            'investment_capital': forms.Select(attrs={'class': 'input'}),
            'first_name': forms.TextInput(attrs={'class': 'input'}),
            'last_name': forms.TextInput(attrs={'class': 'input'}),
            'position': forms.TextInput(attrs={'class': 'input', 'placeholder': 'e.g. HR Manager'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'respondent@organization.com'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            if ParticipationRequest.objects.filter(
                email=email, status__in=['pending', 'approved']
            ).exists():
                raise forms.ValidationError(
                    'A participation request with this email address is already under review. '
                    'If your previous request was rejected, you may resubmit.'
                )
            if User.objects.filter(username=email).exists():
                raise forms.ValidationError(
                    'An account with this email address already exists. '
                    'Please sign in or contact the administrator.'
                )
        return email

    def clean(self):
        cleaned = super().clean()
        for field, msg in validate_org_subtype(
            cleaned.get('org_type', ''),
            cleaned.get('org_subtype', ''),
            cleaned.get('org_subtype_other', ''),
        ):
            self.add_error(field, msg)
        return cleaned
