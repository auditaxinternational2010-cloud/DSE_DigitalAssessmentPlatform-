"""
WSGI config for eya_questionnaire project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eya_questionnaire.settings')

application = get_wsgi_application()
