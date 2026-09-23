import re
from django.core.exceptions import ValidationError


class ComplexPasswordValidator:
    def validate(self, password, user=None):
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                'Password must contain at least one uppercase letter.',
                code='password_no_upper',
            )
        if not re.search(r'[^A-Za-z0-9]', password):
            raise ValidationError(
                'Password must contain at least one special character.',
                code='password_no_special',
            )

    def get_help_text(self):
        return (
            'Your password must contain at least one uppercase letter '
            'and one special character.'
        )


def validate_tanzanian_phone(value):
    if value and not re.fullmatch(r'0\d{9}', value.strip()):
        raise ValidationError(
            'Enter a valid phone number (10 digits starting with 0, e.g. 0712345678).',
            code='invalid_phone',
        )
