"""
ASGI config for eya_questionnaire project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eya_questionnaire.settings')

application = get_asgi_application()
