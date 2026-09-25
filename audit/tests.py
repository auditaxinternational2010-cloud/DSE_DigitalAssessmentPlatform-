from django.test import TestCase, RequestFactory, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from accounts.models import Organization, UserProfile, VerifierAssignment, ParticipationRequest
from assessment.models import (
    AwardCycle, AssessmentCategory, Criterion, LevelIndicator,
    Questionnaire, Response,
)
from .models import AuditLog, _get_ip


class AuditLogModelTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser', password='pass')
        self.org = Organization.objects.create(name='Test Org')

    def _request(self, user=None, forwarded_for=None):
        request = self.factory.get('/')
        request.user = user or self.user
        if forwarded_for:
            request.META['HTTP_X_FORWARDED_FOR'] = forwarded_for
        else:
            request.META['REMOTE_ADDR'] = '127.0.0.1'
        return request

    def test_log_creates_entry_with_correct_fields(self):
        request = self._request()
        AuditLog.log(
            request, 'user.created', 'Created user testuser',
            object_type='User', object_id=self.user.pk,
            object_repr='testuser', organization=self.org,
        )
        entry = AuditLog.objects.first()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, 'user.created')
        self.assertEqual(entry.description, 'Created user testuser')
        self.assertEqual(entry.object_type, 'User')
        self.assertEqual(entry.object_id, self.user.pk)
        self.assertEqual(entry.object_repr, 'testuser')
        self.assertEqual(entry.organization, self.org)

    def test_log_with_unauthenticated_user_stores_null(self):
        from django.contrib.auth.models import AnonymousUser
        request = self._request()
        request.user = AnonymousUser()
        AuditLog.log(request, 'user.created', 'Created user')
        self.assertIsNone(AuditLog.objects.first().user)

    def test_object_repr_persists_after_org_deleted(self):
        request = self._request()
        AuditLog.log(
            request, 'org.deleted', 'Deleted org',
            object_type='Organization', object_id=self.org.pk,
            object_repr=self.org.name, organization=self.org,
        )
        self.org.delete()
        entry = AuditLog.objects.first()
        self.assertEqual(entry.object_repr, 'Test Org')
        self.assertIsNone(entry.organization)

    def test_get_ip_reads_first_forwarded_for_address(self):
        request = self._request(forwarded_for='203.0.113.5, 10.0.0.1')
        self.assertEqual(_get_ip(request), '203.0.113.5')

    def test_get_ip_falls_back_to_remote_addr(self):
        request = self._request()
        self.assertEqual(_get_ip(request), '127.0.0.1')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuditLogIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin_integ', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.client.login(username='admin_integ', password='pass')

        self.org = Organization.objects.create(name='Integ Org')
        self.member_user = User.objects.create_user(username='mem_integ', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)

        self.verifier_user = User.objects.create_user(username='ver_integ', password='pass')
        UserProfile.objects.create(user=self.verifier_user, role='verifier')
        VerifierAssignment.objects.create(verifier=self.verifier_user, organization=self.org)

        self.pr = ParticipationRequest.objects.create(
            org_name='PR Integ Corp', org_type='private', region='Dar es Salaam',
            physical_address='1 Main St', postal_address='P.O. Box 1',
            num_employees='1_4', investment_capital='up_to_5m',
            first_name='Test', last_name='User',
            phone_number='+255700000001', email='test_integ@example.com',
        )

        self.cycle = AwardCycle.objects.create(year=2070, name='DSE 2070', is_open=True)
        self.questionnaire = Questionnaire.objects.get(cycle=self.cycle, organization=self.org)
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Integ Cat', order=1, is_active=True
        )
        self.criterion = Criterion.objects.create(
            category=self.cat, name='Integ Criterion', number=1, is_active=True
        )
        LevelIndicator.objects.create(criterion=self.criterion, level=3, indicator='Level 3 text')
        Response.objects.create(
            questionnaire=self.questionnaire, criterion=self.criterion, score=3, notes=''
        )

    # ── Accounts ──────────────────────────────────────────────────────────────

    def test_request_approve_creates_audit_log(self):
        self.client.post(reverse('request_approve', args=[self.pr.pk]))
        self.assertEqual(AuditLog.objects.filter(action='request.approved').count(), 1)
        entry = AuditLog.objects.get(action='request.approved')
        self.assertIn('PR Integ Corp', entry.description)

    def test_request_reject_creates_audit_log(self):
        self.client.post(reverse('request_reject', args=[self.pr.pk]))
        self.assertEqual(AuditLog.objects.filter(action='request.rejected').count(), 1)
        entry = AuditLog.objects.get(action='request.rejected')
        self.assertIn('PR Integ Corp', entry.description)

    def test_user_create_creates_audit_log(self):
        self.client.post(reverse('user_create'), {
            'username': 'newuser_integ',
            'password': 'Pass123!',
            'role': 'verifier',
        })
        self.assertEqual(AuditLog.objects.filter(action='user.created').count(), 1)

    def test_user_delete_creates_audit_log(self):
        target = User.objects.create_user(username='delete_target_integ', password='pass')
        UserProfile.objects.create(user=target, role='verifier')
        self.client.post(reverse('user_delete', args=[target.pk]))
        self.assertEqual(AuditLog.objects.filter(action='user.deleted').count(), 1)
        entry = AuditLog.objects.get(action='user.deleted')
        self.assertIn('delete_target_integ', entry.description)

    def test_org_create_creates_audit_log(self):
        self.client.post(reverse('org_create'), {
            'name': 'New Org Integ',
            'org_type': 'financial_services',
            'org_subtype': 'banking',
            'org_subtype_other': '',
            'is_active': True,
        })
        self.assertEqual(AuditLog.objects.filter(action='org.created').count(), 1)

    def test_org_delete_creates_audit_log(self):
        org_to_delete = Organization.objects.create(name='Delete Org Integ')
        self.client.post(reverse('org_delete', args=[org_to_delete.pk]))
        self.assertEqual(AuditLog.objects.filter(action='org.deleted').count(), 1)
        entry = AuditLog.objects.get(action='org.deleted')
        self.assertIn('Delete Org Integ', entry.description)

    # ── Assessment ────────────────────────────────────────────────────────────

    def test_cycle_open_creates_audit_log(self):
        closed_cycle = AwardCycle.objects.create(year=2071, name='DSE 2071', is_open=False)
        self.client.post(reverse('cycle_toggle_open', args=[closed_cycle.pk]))
        self.assertEqual(AuditLog.objects.filter(action='cycle.opened').count(), 1)
        entry = AuditLog.objects.get(action='cycle.opened')
        self.assertIn('DSE 2071', entry.description)

    def test_cycle_close_creates_audit_log(self):
        self.client.post(reverse('cycle_toggle_open', args=[self.cycle.pk]))
        self.assertEqual(AuditLog.objects.filter(action='cycle.closed').count(), 1)
        entry = AuditLog.objects.get(action='cycle.closed')
        self.assertIn('DSE 2070', entry.description)

    def test_questionnaire_submit_creates_audit_log(self):
        self.client.login(username='mem_integ', password='pass')
        self.client.post(reverse('questionnaire_submit', args=[self.questionnaire.pk]))
        self.assertEqual(AuditLog.objects.filter(action='questionnaire.submitted').count(), 1)
        entry = AuditLog.objects.get(action='questionnaire.submitted')
        self.assertEqual(entry.organization, self.org)
        self.assertIn('Integ Org', entry.description)

    def test_verifier_scores_saved_creates_audit_log(self):
        from django.utils import timezone as tz
        self.questionnaire.is_submitted = True
        self.questionnaire.submitted_at = tz.now()
        self.questionnaire.save()
        self.client.login(username='ver_integ', password='pass')
        self.client.post(
            reverse('verify_questionnaire', args=[self.questionnaire.pk]),
            {
                'category_id': self.cat.pk,
                f'criterion_{self.criterion.pk}': '3',
                f'notes_{self.criterion.pk}': 'test note',
            }
        )
        self.assertEqual(AuditLog.objects.filter(action='verifier.scores_saved').count(), 1)
        entry = AuditLog.objects.get(action='verifier.scores_saved')
        self.assertEqual(entry.organization, self.org)
        self.assertIn('Integ Org', entry.description)


class AuditLogViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin_view', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.member = User.objects.create_user(username='mem_view', password='pass')
        self.org = Organization.objects.create(name='View Test Org')
        UserProfile.objects.create(user=self.member, role='member', organization=self.org)

        AuditLog.objects.create(
            user=self.admin, action='org.created',
            description='Created View Test Org',
            object_type='Organization', object_repr='View Test Org',
            organization=self.org,
        )
        AuditLog.objects.create(
            user=self.member, action='questionnaire.submitted',
            description='Submitted questionnaire for DSE 2026 — View Test Org',
            object_type='Questionnaire', object_repr='DSE 2026 — View Test Org',
            organization=self.org,
        )

    def test_view_accessible_by_admin(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('page_obj', response.context)

    def test_view_denied_for_member(self):
        self.client.login(username='mem_view', password='pass')
        response = self.client.get(reverse('audit_log'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_unfiltered_returns_all_entries(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.context['page_obj'].paginator.count, 2)

    def test_filter_by_user(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'), {'user': self.admin.pk})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(list(response.context['page_obj'])[0].action, 'org.created')

    def test_filter_by_action(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'), {'action': 'questionnaire.submitted'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_filter_by_organization(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'), {'organization': self.org.pk})
        self.assertEqual(response.context['page_obj'].paginator.count, 2)

    def test_combined_filters_narrow_results(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'), {
            'user': self.admin.pk, 'action': 'org.created',
        })
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_date_from_filter_includes_today(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'), {'date_from': '2020-01-01'})
        self.assertEqual(response.context['page_obj'].paginator.count, 2)

    def test_date_to_filter_excludes_all_when_past(self):
        self.client.login(username='admin_view', password='pass')
        response = self.client.get(reverse('audit_log'), {'date_to': '2020-01-01'})
        self.assertEqual(response.context['page_obj'].paginator.count, 0)
