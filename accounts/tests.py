from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail.backends.base import BaseEmailBackend
from .models import Organization, UserProfile, VerifierAssignment, ParticipationRequest
from accounts.validators import ComplexPasswordValidator, validate_tanzanian_phone
from accounts.forms import validate_org_subtype


class BrokenEmailBackend(BaseEmailBackend):
    """Simulates SMTP being down — used to test email-failure resilience."""
    def send_messages(self, email_messages):
        raise Exception('Simulated SMTP failure')


class OrganizationModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org')
        self.member_user = User.objects.create_user(username='member1', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)
        self.verifier_user = User.objects.create_user(username='verifier1', password='pass')
        UserProfile.objects.create(user=self.verifier_user, role='verifier')
        VerifierAssignment.objects.create(verifier=self.verifier_user, organization=self.org)

    def test_org_member_property(self):
        self.assertEqual(self.org.member, self.member_user)

    def test_org_verifiers_property(self):
        self.assertIn(self.verifier_user, self.org.verifiers)

    def test_verifier_assignment_unique(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            VerifierAssignment.objects.create(verifier=self.verifier_user, organization=self.org)

    def test_verifiers_property_returns_list_of_users(self):
        verifiers = list(self.org.verifiers)
        self.assertIn(self.verifier_user, verifiers)
        self.assertNotIn(self.member_user, verifiers)

    def test_verifiers_uses_prefetch_cache(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        org = Organization.objects.prefetch_related(
            'verifier_assignments__verifier'
        ).get(pk=self.org.pk)
        with CaptureQueriesContext(connection) as ctx:
            _ = list(org.verifiers)
        self.assertEqual(len(ctx.captured_queries), 0,
            f'Expected 0 queries (prefetch hit), got {len(ctx.captured_queries)}')


from django.test import Client
from django.urls import reverse


class RoleDecoratorTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='Test Org Decorator')
        self.member_user = User.objects.create_user(username='mem', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)
        self.verifier_user = User.objects.create_user(username='ver', password='pass')
        UserProfile.objects.create(user=self.verifier_user, role='verifier')

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse('user_list'))
        self.assertRedirects(response, reverse('login'))

    def test_member_cannot_access_admin_view(self):
        self.client.login(username='mem', password='pass')
        response = self.client.get(reverse('user_list'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_verifier_cannot_access_admin_view(self):
        self.client.login(username='ver', password='pass')
        response = self.client.get(reverse('user_list'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_logout_get_does_not_log_out(self):
        self.client.login(username='mem', password='pass')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)
        # Still authenticated
        dashboard = self.client.get(reverse('member_dashboard'))
        self.assertEqual(dashboard.status_code, 200)

    def test_logout_post_logs_out_and_redirects(self):
        self.client.login(username='mem', password='pass')
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
        dashboard = self.client.get(reverse('member_dashboard'))
        self.assertRedirects(dashboard, reverse('login'), fetch_redirect_response=False)


class OrganizationExtendedFieldsTest(TestCase):
    def test_organization_has_new_fields(self):
        org = Organization.objects.create(
            name='Extended Org',
            org_type='private',
            region='Dar es Salaam',
            physical_address='123 Main Street',
            postal_address='P.O. Box 100',
            num_employees='5_49',
            investment_capital='up_to_5m',
        )
        org.refresh_from_db()
        self.assertEqual(org.org_type, 'private')
        self.assertEqual(org.region, 'Dar es Salaam')
        self.assertEqual(org.physical_address, '123 Main Street')
        self.assertEqual(org.postal_address, 'P.O. Box 100')
        self.assertEqual(org.num_employees, '5_49')
        self.assertEqual(org.investment_capital, 'up_to_5m')

    def test_existing_org_without_new_fields_is_valid(self):
        # All new fields are blank=True so existing records stay valid
        org = Organization.objects.create(name='Plain Org')
        org.refresh_from_db()
        self.assertEqual(org.org_type, '')
        self.assertEqual(org.region, '')


class ParticipationRequestModelTest(TestCase):
    def test_create_participation_request(self):
        pr = ParticipationRequest.objects.create(
            org_name='New Corp',
            org_type='private',
            region='Arusha',
            physical_address='456 Uhuru Ave',
            postal_address='P.O. Box 200',
            num_employees='50_99',
            investment_capital='5m_to_200m',
            first_name='Jane',
            last_name='Doe',
            phone_number='0712345678',
            email='jane@newcorp.com',
        )
        self.assertEqual(pr.status, 'pending')
        self.assertIsNotNone(pr.submitted_at)
        self.assertIsNone(pr.reviewed_at)
        self.assertIsNone(pr.reviewed_by)

    def test_str_representation(self):
        pr = ParticipationRequest.objects.create(
            org_name='Test Co',
            org_type='ngo',
            region='Mwanza',
            physical_address='1 Lake Rd',
            postal_address='P.O. Box 1',
            num_employees='1_4',
            investment_capital='up_to_5m',
            first_name='John',
            last_name='Smith',
            phone_number='0700000000',
            email='john@testco.com',
        )
        self.assertIn('Test Co', str(pr))


from .forms import ParticipationRequestForm


class ParticipationRequestViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(username='admin_pr', password='pass')
        UserProfile.objects.create(user=self.admin_user, role='admin')

    def _valid_post_data(self):
        return {
            'org_name': 'Request Corp',
            'org_type': 'financial_services',
            'org_subtype': 'banking',
            'org_subtype_other': '',
            'region': 'Mbeya',
            'physical_address': '7 Mbeya Rd',
            'postal_address': 'P.O. Box 7',
            'num_employees': '1_4',
            'investment_capital': 'up_to_5m',
            'first_name': 'Bob',
            'last_name': 'Banda',
            'position': 'CEO',
            'phone_number': '0733000000',
            'email': 'bob@requestcorp.com',
            'website': '',
        }

    def test_root_url_shows_form_for_unauthenticated(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/participation_request.html')

    def test_root_url_redirects_authenticated_to_dashboard(self):
        self.client.login(username='admin_pr', password='pass')
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_valid_post_creates_request_and_redirects(self):
        from .models import ParticipationRequest
        response = self.client.post(reverse('home'), data=self._valid_post_data())
        self.assertRedirects(response, reverse('request_submitted'))
        self.assertEqual(ParticipationRequest.objects.count(), 1)
        pr = ParticipationRequest.objects.first()
        self.assertEqual(pr.org_name, 'Request Corp')
        self.assertEqual(pr.status, 'pending')

    def test_invalid_post_re_renders_form(self):
        data = self._valid_post_data()
        del data['email']
        response = self.client.post(reverse('home'), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/participation_request.html')

    def test_request_submitted_page_returns_200(self):
        response = self.client.get(reverse('request_submitted'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/request_submitted.html')


class ParticipationRequestFormTest(TestCase):
    def _valid_data(self):
        return {
            'org_name': 'Valid Corp',
            'org_type': 'financial_services',
            'org_subtype': 'banking',
            'org_subtype_other': '',
            'region': 'Dodoma',
            'physical_address': '1 Capital Rd',
            'postal_address': 'P.O. Box 10',
            'num_employees': '5_49',
            'investment_capital': 'up_to_5m',
            'first_name': 'Alice',
            'last_name': 'Mwangi',
            'position': 'CEO',
            'phone_number': '0722000000',
            'email': 'alice@validcorp.com',
            'website': '',
        }

    def test_valid_form_is_valid(self):
        form = ParticipationRequestForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_email_is_invalid(self):
        data = self._valid_data()
        del data['email']
        form = ParticipationRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_save_creates_participation_request(self):
        from .models import ParticipationRequest
        form = ParticipationRequestForm(data=self._valid_data())
        self.assertTrue(form.is_valid())
        pr = form.save()
        self.assertEqual(ParticipationRequest.objects.count(), 1)
        self.assertEqual(pr.org_name, 'Valid Corp')
        self.assertEqual(pr.status, 'pending')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RequestAdminViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(username='admin_req', password='pass')
        UserProfile.objects.create(user=self.admin_user, role='admin')
        self.member_user = User.objects.create_user(username='mem_req', password='pass')
        org = Organization.objects.create(name='Existing Org')
        UserProfile.objects.create(user=self.member_user, role='member', organization=org)

        self.pr = ParticipationRequest.objects.create(
            org_name='Approval Corp',
            org_type='ngo',
            region='Iringa',
            physical_address='1 Iringa Rd',
            postal_address='P.O. Box 50',
            num_employees='50_99',
            investment_capital='200m_to_800m',
            first_name='Mary',
            last_name='Njoki',
            phone_number='0744000000',
            email='mary@approvalcorp.com',
        )

    def test_request_list_accessible_by_admin(self):
        self.client.login(username='admin_req', password='pass')
        response = self.client.get(reverse('request_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/request_list.html')

    def test_request_list_denied_for_member(self):
        self.client.login(username='mem_req', password='pass')
        response = self.client.get(reverse('request_list'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_request_detail_accessible_by_admin(self):
        self.client.login(username='admin_req', password='pass')
        response = self.client.get(reverse('request_detail', args=[self.pr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/request_detail.html')

    def test_approve_redirects_to_credentials_page(self):
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_approve', args=[self.pr.pk]))
        self.assertRedirects(
            response, reverse('request_approval_success'),
            fetch_redirect_response=False
        )

    def test_approval_success_page_shows_credentials(self):
        self.client.login(username='admin_req', password='pass')
        self.client.post(reverse('request_approve', args=[self.pr.pk]))
        response = self.client.get(reverse('request_approval_success'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('credentials', response.context)
        creds = response.context['credentials']
        self.assertEqual(creds['username'], 'mary@approvalcorp.com')
        self.assertIn('password', creds)
        self.assertEqual(creds['org_name'], 'Approval Corp')

    def test_approval_success_page_clears_after_view(self):
        self.client.login(username='admin_req', password='pass')
        self.client.post(reverse('request_approve', args=[self.pr.pk]))
        self.client.get(reverse('request_approval_success'))  # first visit consumes
        response = self.client.get(reverse('request_approval_success'))
        self.assertRedirects(
            response, reverse('request_list'), fetch_redirect_response=False
        )

    def test_approve_creates_org_and_user(self):
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_approve', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_approval_success'), fetch_redirect_response=False)
        # Org created
        self.assertTrue(Organization.objects.filter(name='Approval Corp').exists())
        org = Organization.objects.get(name='Approval Corp')
        self.assertEqual(org.org_type, 'ngo')
        self.assertEqual(org.region, 'Iringa')
        # User created with email as username
        self.assertTrue(User.objects.filter(username='mary@approvalcorp.com').exists())
        user = User.objects.get(username='mary@approvalcorp.com')
        self.assertEqual(user.first_name, 'Mary')
        # UserProfile with member role
        profile = user.userprofile
        self.assertEqual(profile.role, 'member')
        self.assertEqual(profile.organization, org)
        # Request marked approved
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'approved')
        self.assertEqual(self.pr.reviewed_by, self.admin_user)

    def test_approve_blocked_if_org_name_exists(self):
        Organization.objects.create(name='Approval Corp')
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_approve', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_detail', args=[self.pr.pk]), fetch_redirect_response=False)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'pending')

    def test_approve_blocked_if_email_exists(self):
        User.objects.create_user(username='mary@approvalcorp.com', password='pass')
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_approve', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_detail', args=[self.pr.pk]), fetch_redirect_response=False)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'pending')

    def test_approve_already_reviewed_request_is_blocked(self):
        self.pr.status = 'approved'
        self.pr.save()
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_approve', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_detail', args=[self.pr.pk]), fetch_redirect_response=False)

    def test_reject_marks_request_rejected(self):
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_reject', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_list'), fetch_redirect_response=False)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'rejected')
        self.assertEqual(self.pr.reviewed_by, self.admin_user)
        self.assertFalse(Organization.objects.filter(name='Approval Corp').exists())

    def test_reject_already_reviewed_request_is_blocked(self):
        self.pr.status = 'approved'
        self.pr.save()
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_reject', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_detail', args=[self.pr.pk]), fetch_redirect_response=False)

    def test_reject_sets_reviewed_at_and_reviewed_by(self):
        self.client.login(username='admin_req', password='pass')
        self.client.post(reverse('request_reject', args=[self.pr.pk]))
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'rejected')
        self.assertIsNotNone(self.pr.reviewed_at)
        self.assertEqual(self.pr.reviewed_by, self.admin_user)

    def test_reject_already_approved_request_does_not_change_status(self):
        self.pr.status = 'approved'
        self.pr.save()
        self.client.login(username='admin_req', password='pass')
        response = self.client.post(reverse('request_reject', args=[self.pr.pk]))
        self.assertRedirects(
            response, reverse('request_detail', args=[self.pr.pk]),
            fetch_redirect_response=False
        )
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'approved')


class PaginationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin_page', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.client.login(username='admin_page', password='pass')

    def test_user_list_returns_page_obj(self):
        response = self.client.get(reverse('user_list'))
        self.assertIn('page_obj', response.context)

    def test_org_list_returns_page_obj(self):
        response = self.client.get(reverse('org_list'))
        self.assertIn('page_obj', response.context)

    def test_request_list_returns_page_obj(self):
        response = self.client.get(reverse('request_list'))
        self.assertIn('page_obj', response.context)


from django.contrib.messages import get_messages as _get_messages

class MessageTagTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin_tag', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.client.login(username='admin_tag', password='pass')

    def test_error_message_has_danger_tag(self):
        # Trigger messages.error: trying to delete own account hits the guard
        response = self.client.post(
            reverse('user_delete', args=[self.admin.pk]), follow=True
        )
        msgs = list(_get_messages(response.wsgi_request))
        self.assertTrue(
            any(m.tags == 'danger' for m in msgs),
            f"Expected tag 'danger', got: {[m.tags for m in msgs]}"
        )


class MustChangePasswordFieldTest(TestCase):
    def test_default_is_false(self):
        user = User.objects.create_user(username='flagtest@x.com', password='pass')
        profile = UserProfile.objects.create(user=user, role='member')
        self.assertFalse(profile.must_change_password)

    def test_can_be_set_true(self):
        user = User.objects.create_user(username='flagtest2@x.com', password='pass')
        profile = UserProfile.objects.create(user=user, role='member', must_change_password=True)
        profile.refresh_from_db()
        self.assertTrue(profile.must_change_password)


class MustChangePasswordMiddlewareTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='member@mw.com', password='OldPass1!', email='member@mw.com',
        )
        self.profile = UserProfile.objects.create(
            user=self.user, role='member', must_change_password=False,
        )

    def _login(self):
        self.client.login(username='member@mw.com', password='OldPass1!')

    def test_unauthenticated_not_redirected_to_change_password(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_flag_false_not_redirected(self):
        self._login()
        # Dashboard redirects to role-specific dashboard, not change_password
        response = self.client.get(reverse('dashboard'))
        self.assertNotEqual(response.get('Location', ''), reverse('change_password'))

    def test_flag_true_redirects_to_change_password(self):
        self.profile.must_change_password = True
        self.profile.save()
        self._login()
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('change_password'), fetch_redirect_response=False)

    def test_change_password_url_not_redirected(self):
        self.profile.must_change_password = True
        self.profile.save()
        self._login()
        response = self.client.get(reverse('change_password'))
        # Should serve the page, not loop back to itself
        self.assertEqual(response.status_code, 200)

    def test_logout_url_not_redirected(self):
        self.profile.must_change_password = True
        self.profile.save()
        self._login()
        response = self.client.post(reverse('logout'))
        self.assertNotEqual(response.get('Location', ''), reverse('change_password'))

    def test_password_reset_url_not_redirected(self):
        self.profile.must_change_password = True
        self.profile.save()
        self._login()
        response = self.client.get(reverse('password_reset'))
        self.assertNotEqual(response.get('Location', ''), reverse('change_password'))


class FirstLoginPasswordChangeViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='member@pw.com', password='OldPassword1!', email='member@pw.com',
        )
        self.profile = UserProfile.objects.create(
            user=self.user, role='member', must_change_password=True,
        )
        self.client.login(username='member@pw.com', password='OldPassword1!')

    def test_change_password_page_loads(self):
        response = self.client.get(reverse('change_password'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Change Your Password')

    def test_valid_change_clears_flag_and_redirects(self):
        response = self.client.post(reverse('change_password'), {
            'old_password': 'OldPassword1!',
            'new_password1': 'NewSecurePass99!',
            'new_password2': 'NewSecurePass99!',
        })
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.must_change_password)

    def test_wrong_old_password_keeps_flag(self):
        self.client.post(reverse('change_password'), {
            'old_password': 'wrongpass',
            'new_password1': 'NewSecurePass99!',
            'new_password2': 'NewSecurePass99!',
        })
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.must_change_password)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class WelcomeEmailTest(TestCase):
    def test_send_welcome_email_goes_to_correct_address(self):
        from accounts.emails import send_welcome_email
        user = User.objects.create_user(
            username='newmember@example.com',
            email='newmember@example.com',
            first_name='Jane',
        )
        send_welcome_email(user, 'TempPass123')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('newmember@example.com', mail.outbox[0].to)

    def test_send_welcome_email_contains_credentials(self):
        from accounts.emails import send_welcome_email
        user = User.objects.create_user(
            username='cred@example.com',
            email='cred@example.com',
            first_name='John',
        )
        send_welcome_email(user, 'SecretPass99')
        self.assertIn('cred@example.com', mail.outbox[0].body)
        self.assertIn('SecretPass99', mail.outbox[0].body)
        self.assertIn('John', mail.outbox[0].body)

    def test_send_welcome_email_subject(self):
        from accounts.emails import send_welcome_email
        user = User.objects.create_user(
            username='subj@example.com',
            email='subj@example.com',
            first_name='Alice',
        )
        send_welcome_email(user, 'Pass456')
        self.assertIn('Welcome', mail.outbox[0].subject)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RequestApproveEmailIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin_email', password='adminpass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.client.login(username='admin_email', password='adminpass')
        self.pr = ParticipationRequest.objects.create(
            org_name='Email Corp',
            org_type='private',
            region='Dar es Salaam',
            physical_address='123 Main St',
            postal_address='P.O. Box 1',
            num_employees='5_49',
            investment_capital='up_to_5m',
            first_name='Jane',
            last_name='Doe',
            phone_number='0700000001',
            email='jane@emailcorp.com',
        )

    def test_approval_sends_welcome_email(self):
        from accounts.models import EmailLog
        self.client.post(reverse('request_approve', kwargs={'pk': self.pr.pk}))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('jane@emailcorp.com', mail.outbox[0].to)
        # The approving admin must be recorded — this flow is unambiguously
        # admin-initiated, so the EmailLog row must not show an unknown sender.
        log = EmailLog.objects.get(kind='welcome', recipient='jane@emailcorp.com')
        self.assertEqual(log.triggered_by, self.admin)

    def test_approval_sets_must_change_password(self):
        self.client.post(reverse('request_approve', kwargs={'pk': self.pr.pk}))
        user = User.objects.get(email='jane@emailcorp.com')
        self.assertTrue(user.userprofile.must_change_password)

    @override_settings(EMAIL_BACKEND='accounts.tests.BrokenEmailBackend')
    def test_approval_succeeds_even_if_email_fails(self):
        response = self.client.post(reverse('request_approve', kwargs={'pk': self.pr.pk}))
        # User and org still created
        self.assertTrue(User.objects.filter(email='jane@emailcorp.com').exists())
        self.assertTrue(Organization.objects.filter(name='Email Corp').exists())
        # Admin still redirected to approval success page
        self.assertRedirects(response, reverse('request_approval_success'), fetch_redirect_response=False)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='reset@example.com',
            email='reset@example.com',
            password='OldPassword1!',
        )
        UserProfile.objects.create(user=self.user, role='member')

    def test_password_reset_page_loads(self):
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_sends_email(self):
        self.client.post(reverse('password_reset'), {'email': 'reset@example.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset@example.com', mail.outbox[0].to)

    def test_password_reset_redirects_to_done(self):
        response = self.client.post(reverse('password_reset'), {'email': 'reset@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'), fetch_redirect_response=False)

    def test_password_reset_done_page_loads(self):
        response = self.client.get(reverse('password_reset_done'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_complete_page_loads(self):
        response = self.client.get(reverse('password_reset_complete'))
        self.assertEqual(response.status_code, 200)

    def test_unknown_email_silently_redirects_to_done(self):
        response = self.client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)


class ComplexPasswordValidatorTest(TestCase):
    def setUp(self):
        self.validator = ComplexPasswordValidator()

    def test_accepts_valid_password(self):
        # Should not raise for a password that meets all requirements
        try:
            self.validator.validate('ValidPass1!')
        except ValidationError:
            self.fail('validate() raised ValidationError for a valid password')

    def test_rejects_no_uppercase(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate('validpass1!')
        self.assertEqual(ctx.exception.code, 'password_no_upper')

    def test_rejects_no_special_char(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate('ValidPass1A')
        self.assertEqual(ctx.exception.code, 'password_no_special')

    def test_rejects_only_letters_and_digits(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate('ValidPass1')
        self.assertEqual(ctx.exception.code, 'password_no_special')

    def test_help_text_mentions_uppercase_and_special(self):
        help_text = self.validator.get_help_text()
        self.assertIn('uppercase', help_text)
        self.assertIn('special character', help_text)


class UserProfilePhoneNumberTests(TestCase):
    def test_phone_number_field_exists_and_defaults_blank(self):
        user = User.objects.create_user(username='testphone', password='x')
        profile = UserProfile.objects.create(user=user, role='admin')
        self.assertEqual(profile.phone_number, '')

    def test_phone_number_saves_and_retrieves(self):
        user = User.objects.create_user(username='testphone2', password='x')
        profile = UserProfile.objects.create(
            user=user, role='admin', phone_number='0700123456'
        )
        profile.refresh_from_db()
        self.assertEqual(profile.phone_number, '0700123456')


class AuditLogUserEditedActionTests(TestCase):
    def test_user_edited_action_is_valid_choice(self):
        from audit.models import AuditLog
        valid_codes = [code for code, _ in AuditLog.ACTION_CHOICES]
        self.assertIn('user.edited', valid_codes)


class ProfileFormTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org')
        self.user = User.objects.create_user(
            username='formtest@test.com',
            email='formtest@test.com',
            password='TestPass123!',
            first_name='Original',
            last_name='Name',
        )
        UserProfile.objects.create(
            user=self.user, role='member',
            organization=self.org, phone_number='0700000001'
        )

    def test_form_initial_loads_phone_from_profile(self):
        from accounts.forms import ProfileForm
        form = ProfileForm(instance=self.user)
        self.assertEqual(form.fields['phone_number'].initial, '0700000001')

    def test_form_saves_first_last_and_phone(self):
        from accounts.forms import ProfileForm
        form = ProfileForm(
            data={'first_name': 'New', 'last_name': 'Person', 'phone_number': '0755999999'},
            instance=self.user
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.last_name, 'Person')
        self.assertEqual(self.user.userprofile.phone_number, '0755999999')

    def test_form_does_not_include_email_or_role(self):
        from accounts.forms import ProfileForm
        form = ProfileForm(instance=self.user)
        self.assertNotIn('email', form.fields)
        self.assertNotIn('role', form.fields)


class AdminFormsPhoneNumberTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Phone Test Org')

    def test_user_create_form_saves_phone_number(self):
        from accounts.forms import UserCreateForm
        form = UserCreateForm(data={
            'username': 'newuser@test.com',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser@test.com',
            'password': 'TestPass123!',
            'role': 'admin',
            'phone_number': '0711222333',
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.userprofile.phone_number, '0711222333')

    def test_user_edit_form_saves_phone_number(self):
        from accounts.forms import UserEditForm
        user = User.objects.create_user(username='editme@test.com', password='x')
        UserProfile.objects.create(user=user, role='admin', phone_number='0700000000')
        form = UserEditForm(
            data={
                'first_name': 'Edit',
                'last_name': 'Me',
                'email': 'editme@test.com',
                'role': 'admin',
                'phone_number': '0788999000',
            },
            instance=user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.userprofile.refresh_from_db()
        self.assertEqual(user.userprofile.phone_number, '0788999000')

    def test_user_edit_form_initial_loads_phone(self):
        from accounts.forms import UserEditForm
        user = User.objects.create_user(username='initcheck@test.com', password='x')
        UserProfile.objects.create(user=user, role='admin', phone_number='0700111222')
        form = UserEditForm(instance=user)
        self.assertEqual(form.fields['phone_number'].initial, '0700111222')


class ProfileViewTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Profile Test Org')

        self.member = User.objects.create_user(
            username='member@test.com', email='member@test.com',
            password='TestPass123!', first_name='Mem', last_name='Ber'
        )
        UserProfile.objects.create(
            user=self.member, role='member',
            organization=self.org, phone_number='0700000001'
        )

        self.verifier = User.objects.create_user(
            username='verifier@test.com', password='TestPass123!'
        )
        UserProfile.objects.create(user=self.verifier, role='verifier')

        self.admin = User.objects.create_user(
            username='admin@test.com', password='TestPass123!'
        )
        UserProfile.objects.create(user=self.admin, role='admin')

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse('profile'))
        self.assertRedirects(response, '/login/?next=/accounts/profile/')

    def test_member_get_returns_200_with_org_block(self):
        self.client.login(username='member@test.com', password='TestPass123!')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_org'])
        self.assertEqual(response.context['org'], self.org)

    def test_verifier_get_returns_200_without_org_block(self):
        self.client.login(username='verifier@test.com', password='TestPass123!')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_org'])

    def test_admin_get_returns_200_without_org_block(self):
        self.client.login(username='admin@test.com', password='TestPass123!')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_org'])

    def test_post_updates_name_and_phone(self):
        self.client.login(username='member@test.com', password='TestPass123!')
        response = self.client.post(reverse('profile'), {
            'first_name': 'Updated',
            'last_name': 'Name',
            'phone_number': '0755999888',
        })
        self.assertRedirects(response, reverse('profile'))
        self.member.refresh_from_db()
        self.member.userprofile.refresh_from_db()
        self.assertEqual(self.member.first_name, 'Updated')
        self.assertEqual(self.member.last_name, 'Name')
        self.assertEqual(self.member.userprofile.phone_number, '0755999888')

    def test_post_cannot_change_email(self):
        self.client.login(username='member@test.com', password='TestPass123!')
        self.client.post(reverse('profile'), {
            'first_name': 'X',
            'last_name': 'Y',
            'phone_number': '',
            'email': 'hacker@evil.com',
        })
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, 'member@test.com')


class ChangePasswordMessagingTests(TestCase):
    def _make_user(self, must_change):
        user = User.objects.create_user(
            username=f'pwtest_{must_change}@test.com', password='OldPass123!'
        )
        UserProfile.objects.create(user=user, role='member', must_change_password=must_change)
        return user

    def test_forced_context_true_when_must_change(self):
        user = self._make_user(must_change=True)
        self.client.force_login(user)
        response = self.client.get('/change-password/')
        self.assertTrue(response.context['forced'])

    def test_forced_context_false_when_voluntary(self):
        user = self._make_user(must_change=False)
        self.client.force_login(user)
        response = self.client.get('/change-password/')
        self.assertFalse(response.context['forced'])


class UserEditAuditTests(TestCase):
    def setUp(self):
        from audit.models import AuditLog
        self.AuditLog = AuditLog
        self.admin = User.objects.create_user(username='audit_admin@test.com', password='AdminPass123!')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.target = User.objects.create_user(
            username='audit_target@test.com',
            email='audit_target@test.com',
            password='TargetPass123!'
        )
        UserProfile.objects.create(user=self.target, role='verifier')

    def test_user_edit_creates_audit_log_entry(self):
        self.client.login(username='audit_admin@test.com', password='AdminPass123!')
        self.client.post(f'/accounts/users/{self.target.pk}/edit/', {
            'first_name': 'Edited',
            'last_name': 'User',
            'email': 'audit_target@test.com',
            'role': 'verifier',
            'phone_number': '',
        })
        log = self.AuditLog.objects.filter(action='user.edited').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.object_id, self.target.pk)


class ParticipationRequestPhoneTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_phone@test.com', password='AdminPass123!')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.pr = ParticipationRequest.objects.create(
            org_name='Phone Number Org',
            org_type='private',
            region='Dar es Salaam',
            physical_address='123 Main St',
            postal_address='P.O. Box 1',
            num_employees='1_4',
            investment_capital='up_to_5m',
            first_name='Jane',
            last_name='Doe',
            phone_number='0784123456',
            email='jane@phonenumberorg.com',
        )

    def test_approval_copies_phone_to_userprofile(self):
        self.client.login(username='admin_phone@test.com', password='AdminPass123!')
        self.client.post(f'/accounts/requests/{self.pr.pk}/approve/')
        user = User.objects.get(username='jane@phonenumberorg.com')
        self.assertEqual(user.userprofile.phone_number, '0784123456')


class UserListSearchTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_search', password='Pass123!')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.user_a = User.objects.create_user(username='alice', password='x')
        UserProfile.objects.create(user=self.user_a, role='member')
        self.user_b = User.objects.create_user(username='bob', password='x')
        UserProfile.objects.create(user=self.user_b, role='member')
        self.client.login(username='admin_search', password='Pass123!')

    def test_search_filters_by_username(self):
        response = self.client.get(reverse('user_list') + '?q=alice')
        self.assertContains(response, 'alice')
        self.assertNotContains(response, 'bob')

    def test_search_empty_returns_all(self):
        response = self.client.get(reverse('user_list'))
        self.assertContains(response, 'alice')
        self.assertContains(response, 'bob')


class OrgListSearchTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_orgsearch', password='Pass123!')
        UserProfile.objects.create(user=self.admin, role='admin')
        Organization.objects.create(name='Acme Corp')
        Organization.objects.create(name='Zeta Ltd')
        self.client.login(username='admin_orgsearch', password='Pass123!')

    def test_search_filters_by_name(self):
        response = self.client.get(reverse('org_list') + '?q=acme')
        self.assertContains(response, 'Acme Corp')
        self.assertNotContains(response, 'Zeta Ltd')

    def test_search_empty_returns_all(self):
        response = self.client.get(reverse('org_list'))
        self.assertContains(response, 'Acme Corp')
        self.assertContains(response, 'Zeta Ltd')


class NavContextProcessorTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_ctx', password='Pass123!')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.member_org = Organization.objects.create(name='Nav Org')
        self.member = User.objects.create_user(username='member_ctx', password='Pass123!')
        UserProfile.objects.create(user=self.member, role='member', organization=self.member_org)

    def test_pending_count_in_admin_context(self):
        ParticipationRequest.objects.create(
            org_name='Req Org', org_type='private', region='Dar', email='r@r.com',
            first_name='A', last_name='B', phone_number='0700000000', status='pending'
        )
        self.client.login(username='admin_ctx', password='Pass123!')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.context['pending_request_count'], 1)

    def test_pending_count_zero_for_non_admin(self):
        ParticipationRequest.objects.create(
            org_name='Req Org', org_type='private', region='Dar', email='r@r.com',
            first_name='A', last_name='B', phone_number='0700000000', status='pending'
        )
        self.client.login(username='member_ctx', password='Pass123!')
        response = self.client.get(reverse('member_dashboard'))
        self.assertEqual(response.context.get('pending_request_count', 0), 0)

    def test_anonymous_user_no_context(self):
        response = self.client.get(reverse('home'))
        self.assertNotIn('pending_request_count', response.context or {})


class ParticipationHoneypotTest(TestCase):
    def _payload(self, **extra):
        data = {
            'org_name': 'Honeypot Org', 'org_type': 'financial_services',
            'org_subtype': 'banking', 'org_subtype_other': '',
            'region': 'Dar',
            'physical_address': 'Street 1', 'postal_address': 'P.O. Box 1',
            'num_employees': '5_49', 'investment_capital': 'up_to_5m',
            'first_name': 'Jane', 'last_name': 'Doe',
            'phone_number': '0700000000', 'email': 'jane@example.com',
        }
        data.update(extra)
        return data

    def test_clean_submission_creates_request(self):
        resp = self.client.post(reverse('home'), self._payload())
        self.assertRedirects(resp, reverse('request_submitted'))
        self.assertEqual(ParticipationRequest.objects.count(), 1)

    def test_filled_honeypot_is_silently_dropped(self):
        resp = self.client.post(reverse('home'), self._payload(website='http://spam.example'))
        # Bot sees a normal success page...
        self.assertRedirects(resp, reverse('request_submitted'))
        # ...but nothing is persisted.
        self.assertEqual(ParticipationRequest.objects.count(), 0)


class RateLimitHelperTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_hit_increments_count_and_reset(self):
        from accounts import ratelimit
        self.assertEqual(ratelimit.count('k'), 0)
        self.assertEqual(ratelimit.hit('k', 60), 1)
        self.assertEqual(ratelimit.hit('k', 60), 2)
        self.assertEqual(ratelimit.count('k'), 2)
        ratelimit.reset('k')
        self.assertEqual(ratelimit.count('k'), 0)


@override_settings(TESTING=False)
class LoginThrottleTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(username='throttle_u', password='Right1!')
        UserProfile.objects.create(user=self.user, role='admin')

    def test_blocks_after_too_many_failures(self):
        from django.conf import settings
        for _ in range(settings.LOGIN_RATELIMIT_ATTEMPTS):
            self.client.post(reverse('login'), {'username': 'throttle_u', 'password': 'wrong'})
        # Even with the correct password, the next attempt is throttled.
        resp = self.client.post(reverse('login'), {'username': 'throttle_u', 'password': 'Right1!'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Too many failed sign-in attempts')
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_successful_login_resets_counter(self):
        self.client.post(reverse('login'), {'username': 'throttle_u', 'password': 'wrong'})
        resp = self.client.post(reverse('login'), {'username': 'throttle_u', 'password': 'Right1!'})
        self.assertRedirects(resp, reverse('dashboard'), fetch_redirect_response=False)


class EmailDuplicateCheckTest(TestCase):
    """clean_email() on ParticipationRequestForm blocks duplicate pending/approved requests."""

    def _valid_data(self, email='fresh@example.com'):
        return {
            'org_name': 'Unique Corp',
            'org_type': 'financial_services',
            'org_subtype': 'banking',
            'org_subtype_other': '',
            'region': 'Dar es Salaam',
            'physical_address': '1 New St',
            'postal_address': 'P.O. Box 99',
            'num_employees': '1_4',
            'investment_capital': 'up_to_5m',
            'first_name': 'Test',
            'last_name': 'User',
            'position': 'Manager',
            'phone_number': '0700000099',
            'email': email,
            'website': '',
        }

    def _pr(self, email, status):
        return ParticipationRequest.objects.create(
            org_name=f'Org {email}', org_type='ngo', region='Arusha',
            physical_address='x', postal_address='x',
            num_employees='1_4', investment_capital='up_to_5m',
            first_name='A', last_name='B', phone_number='0700',
            email=email, status=status,
        )

    def test_pending_request_blocks_resubmission(self):
        self._pr('taken@example.com', 'pending')
        response = self.client.post(reverse('home'), self._valid_data('taken@example.com'))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('email', form.errors)
        self.assertIn('already under review', form.errors['email'][0])

    def test_approved_request_blocks_resubmission(self):
        self._pr('approved@example.com', 'approved')
        response = self.client.post(reverse('home'), self._valid_data('approved@example.com'))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('email', form.errors)
        self.assertIn('already under review', form.errors['email'][0])

    def test_rejected_request_allows_resubmission(self):
        self._pr('rejected@example.com', 'rejected')
        response = self.client.post(reverse('home'), self._valid_data('rejected@example.com'))
        self.assertRedirects(response, reverse('request_submitted'))
        self.assertEqual(ParticipationRequest.objects.filter(email='rejected@example.com').count(), 2)

    def test_existing_user_blocks_submission(self):
        User.objects.create_user(username='existing@example.com', password='pass')
        response = self.client.post(reverse('home'), self._valid_data('existing@example.com'))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('email', form.errors)
        self.assertIn('already exists', form.errors['email'][0])

    def test_fresh_email_allows_submission(self):
        response = self.client.post(reverse('home'), self._valid_data('brand@new.com'))
        self.assertRedirects(response, reverse('request_submitted'))
        self.assertTrue(ParticipationRequest.objects.filter(email='brand@new.com').exists())


from django.utils import timezone
from audit.models import AuditLog


class ReopenRequestTest(TestCase):
    """request_reopen_view sets rejected → pending and logs the action."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin_reopen', password='AdminPass1!')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.reviewer = User.objects.create_user(username='reviewer_reopen', password='pass')
        UserProfile.objects.create(user=self.reviewer, role='admin')
        self.client.login(username='admin_reopen', password='AdminPass1!')
        self.pr = ParticipationRequest.objects.create(
            org_name='Reopen Corp', org_type='private', region='DSM',
            physical_address='1 Rd', postal_address='P.O. Box 1',
            num_employees='5_49', investment_capital='up_to_5m',
            first_name='Jane', last_name='Doe',
            phone_number='0712345678', email='jane@reopencorp.com',
            status='rejected',
            reviewed_by=self.reviewer,
            reviewed_at=timezone.now(),
        )

    def test_reopen_sets_status_to_pending(self):
        self.client.post(reverse('request_reopen', args=[self.pr.pk]))
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'pending')

    def test_reopen_clears_reviewer_fields(self):
        self.client.post(reverse('request_reopen', args=[self.pr.pk]))
        self.pr.refresh_from_db()
        self.assertIsNone(self.pr.reviewed_by)
        self.assertIsNone(self.pr.reviewed_at)

    def test_reopen_logs_audit_entry(self):
        self.client.post(reverse('request_reopen', args=[self.pr.pk]))
        self.assertTrue(
            AuditLog.objects.filter(action='request.reopened', object_repr='Reopen Corp').exists()
        )

    def test_reopen_redirects_to_detail(self):
        response = self.client.post(reverse('request_reopen', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_detail', args=[self.pr.pk]))

    def test_cannot_reopen_pending_request(self):
        self.pr.status = 'pending'
        self.pr.reviewed_by = None
        self.pr.reviewed_at = None
        self.pr.save()
        self.client.post(reverse('request_reopen', args=[self.pr.pk]))
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'pending')

    def test_cannot_reopen_approved_request(self):
        self.pr.status = 'approved'
        self.pr.save()
        self.client.post(reverse('request_reopen', args=[self.pr.pk]))
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'approved')

    def test_get_request_redirects_to_detail(self):
        response = self.client.get(reverse('request_reopen', args=[self.pr.pk]))
        self.assertRedirects(response, reverse('request_detail', args=[self.pr.pk]))
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'rejected')

    def test_non_admin_cannot_reopen(self):
        member = User.objects.create_user(username='member_ro', password='pass')
        UserProfile.objects.create(user=member, role='member')
        self.client.login(username='member_ro', password='pass')
        self.client.post(reverse('request_reopen', args=[self.pr.pk]))
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, 'rejected')


class PhoneValidationTest(TestCase):
    def test_valid_07xx_number_accepted(self):
        # Should not raise
        validate_tanzanian_phone('0712345678')
        validate_tanzanian_phone('0612345678')
        validate_tanzanian_phone('0612345670')

    def test_missing_leading_zero_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_tanzanian_phone('712345678')

    def test_11_digits_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_tanzanian_phone('07123456789')

    def test_9_digits_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_tanzanian_phone('071234567')

    def test_plus_format_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_tanzanian_phone('+255712345678')

    def test_alpha_chars_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_tanzanian_phone('0712abc678')

    def test_empty_string_passes(self):
        # Field is optional — empty value must not raise
        validate_tanzanian_phone('')

    def test_participation_form_validates_phone(self):
        data = {
            'org_name': 'Test Org', 'org_type': 'financial_services',
            'org_subtype': 'banking', 'org_subtype_other': '',
            'region': 'Dar es Salaam',
            'physical_address': '1 Road', 'postal_address': 'P.O. Box 1',
            'num_employees': '1_4', 'investment_capital': 'up_to_5m',
            'first_name': 'Alice', 'last_name': 'Smith', 'position': 'HR',
            'phone_number': '712345678',  # missing leading 0 — should fail
            'email': 'alice@example.com',
            'website': '',
        }
        from accounts.forms import ParticipationRequestForm
        form = ParticipationRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('phone_number', form.errors)


class OrgTypeSubtypeModelTest(TestCase):
    def test_org_fields_default_blank(self):
        org = Organization.objects.create(name='SubtypeOrg', org_type='financial_services')
        self.assertEqual(org.org_subtype, '')
        self.assertEqual(org.org_subtype_other, '')

    def test_get_org_subtype_display_returns_label(self):
        org = Organization(org_type='financial_services', org_subtype='banking')
        self.assertEqual(org.get_org_subtype_display(), 'Banking')

    def test_get_org_subtype_display_other_returns_description(self):
        org = Organization(
            org_type='financial_services',
            org_subtype='other',
            org_subtype_other='Investment club',
        )
        self.assertEqual(org.get_org_subtype_display(), 'Investment club')

    def test_get_org_subtype_display_other_no_description_returns_other(self):
        org = Organization(org_type='financial_services', org_subtype='other', org_subtype_other='')
        self.assertEqual(org.get_org_subtype_display(), 'Other')

    def test_get_org_subtype_display_blank_returns_empty(self):
        org = Organization(org_type='financial_services', org_subtype='')
        self.assertEqual(org.get_org_subtype_display(), '')

    def test_pr_fields_default_blank(self):
        pr = ParticipationRequest.objects.create(
            org_name='PR Org', org_type='financial_services',
            region='Dar es Salaam', physical_address='1 Road',
            postal_address='P.O. Box 1', num_employees='1_4',
            investment_capital='up_to_5m', first_name='A', last_name='B',
            phone_number='0700000000', email='a@b.com',
        )
        self.assertEqual(pr.org_subtype, '')
        self.assertEqual(pr.org_subtype_other, '')

    def test_pr_get_org_subtype_display(self):
        pr = ParticipationRequest(org_type='ngos', org_subtype='local_ngos')
        self.assertEqual(pr.get_org_subtype_display(), 'Local NGOs')


class ValidateOrgSubtypeHelperTest(TestCase):
    def test_valid_type_and_subtype(self):
        self.assertEqual(validate_org_subtype('financial_services', 'banking', ''), [])

    def test_other_subtype_with_description(self):
        self.assertEqual(validate_org_subtype('financial_services', 'other', 'Investment club'), [])

    def test_other_subtype_without_description(self):
        errors = validate_org_subtype('financial_services', 'other', '')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], 'org_subtype_other')

    def test_other_subtype_with_whitespace_description_rejected(self):
        errors = validate_org_subtype('financial_services', 'other', '   ')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], 'org_subtype_other')

    def test_missing_subtype(self):
        errors = validate_org_subtype('financial_services', '', '')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], 'org_subtype')

    def test_wrong_subtype_for_type(self):
        errors = validate_org_subtype('financial_services', 'schools', '')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], 'org_subtype')

    def test_informal_sector_no_subtype_ok(self):
        self.assertEqual(validate_org_subtype('informal_sector', '', ''), [])

    def test_informal_sector_with_subtype_rejected(self):
        errors = validate_org_subtype('informal_sector', 'banking', '')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], 'org_subtype')


class ParticipationRequestFormSubtypeTest(TestCase):
    def _base_data(self):
        return {
            'org_name': 'Test Corp',
            'org_type': 'financial_services',
            'org_subtype': 'banking',
            'org_subtype_other': '',
            'region': 'Dar es Salaam',
            'physical_address': '123 Test Street',
            'postal_address': 'P.O. Box 1',
            'num_employees': '5_49',
            'investment_capital': '5m_to_200m',
            'first_name': 'Jane',
            'last_name': 'Doe',
            'position': 'CEO',
            'phone_number': '0712345678',
            'email': 'jane@testcorp.com',
            'website': '',
        }

    def test_valid_type_and_subtype_accepted(self):
        from accounts.forms import ParticipationRequestForm
        form = ParticipationRequestForm(data=self._base_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_subtype_with_description_accepted(self):
        from accounts.forms import ParticipationRequestForm
        data = self._base_data()
        data['org_subtype'] = 'other'
        data['org_subtype_other'] = 'Investment club'
        form = ParticipationRequestForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_subtype_without_description_rejected(self):
        from accounts.forms import ParticipationRequestForm
        data = self._base_data()
        data['org_subtype'] = 'other'
        data['org_subtype_other'] = ''
        form = ParticipationRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('org_subtype_other', form.errors)

    def test_invalid_subtype_for_type_rejected(self):
        from accounts.forms import ParticipationRequestForm
        data = self._base_data()
        data['org_subtype'] = 'schools'  # valid for education_vocational, not financial_services
        form = ParticipationRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('org_subtype', form.errors)

    def test_informal_sector_no_subtype_accepted(self):
        from accounts.forms import ParticipationRequestForm
        data = self._base_data()
        data['org_type'] = 'informal_sector'
        data['org_subtype'] = ''
        form = ParticipationRequestForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_informal_sector_with_subtype_rejected(self):
        from accounts.forms import ParticipationRequestForm
        data = self._base_data()
        data['org_type'] = 'informal_sector'
        data['org_subtype'] = 'banking'
        form = ParticipationRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('org_subtype', form.errors)


class OrgFormSubtypeTest(TestCase):
    def _base_data(self):
        return {
            'name': 'Test Corp',
            'org_type': 'financial_services',
            'org_subtype': 'banking',
            'org_subtype_other': '',
            'region': 'Dar es Salaam',
            'physical_address': '123 Test Street',
            'postal_address': 'P.O. Box 1',
            'num_employees': '5_49',
            'investment_capital': '5m_to_200m',
            'description': '',
            'is_active': True,
        }

    def test_valid_type_and_subtype_accepted(self):
        from accounts.forms import OrgForm
        form = OrgForm(data=self._base_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_subtype_with_description_accepted(self):
        from accounts.forms import OrgForm
        data = self._base_data()
        data['org_subtype'] = 'other'
        data['org_subtype_other'] = 'Investment club'
        form = OrgForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_subtype_without_description_rejected(self):
        from accounts.forms import OrgForm
        data = self._base_data()
        data['org_subtype'] = 'other'
        data['org_subtype_other'] = ''
        form = OrgForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('org_subtype_other', form.errors)

    def test_invalid_subtype_for_type_rejected(self):
        from accounts.forms import OrgForm
        data = self._base_data()
        data['org_subtype'] = 'schools'
        form = OrgForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('org_subtype', form.errors)

    def test_informal_sector_no_subtype_accepted(self):
        from accounts.forms import OrgForm
        data = self._base_data()
        data['org_type'] = 'informal_sector'
        data['org_subtype'] = ''
        form = OrgForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_informal_sector_with_subtype_rejected(self):
        from accounts.forms import OrgForm
        data = self._base_data()
        data['org_type'] = 'informal_sector'
        data['org_subtype'] = 'banking'
        form = OrgForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('org_subtype', form.errors)


class RequestApproveSubtypeTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin_sub', password='Admin@Test1!')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.client.login(username='admin_sub', password='Admin@Test1!')
        self.pr = ParticipationRequest.objects.create(
            org_name='Subtype Corp',
            org_type='financial_services',
            org_subtype='banking',
            org_subtype_other='',
            region='Dar es Salaam',
            physical_address='123 Test St',
            postal_address='P.O. Box 1',
            num_employees='5_49',
            investment_capital='5m_to_200m',
            first_name='Jane',
            last_name='Doe',
            position='CEO',
            phone_number='0712345678',
            email='jane@subtypecorp.com',
        )

    @patch('accounts.views.send_welcome_email')
    def test_approve_copies_subtype_to_org(self, _mock_email):
        self.client.post(reverse('request_approve', args=[self.pr.pk]))
        org = Organization.objects.get(name='Subtype Corp')
        self.assertEqual(org.org_subtype, 'banking')
        self.assertEqual(org.org_subtype_other, '')

    @patch('accounts.views.send_welcome_email')
    def test_approve_copies_other_subtype_to_org(self, _mock_email):
        self.pr.org_subtype = 'other'
        self.pr.org_subtype_other = 'Investment holding'
        self.pr.save()
        self.client.post(reverse('request_approve', args=[self.pr.pk]))
        org = Organization.objects.get(name='Subtype Corp')
        self.assertEqual(org.org_subtype, 'other')
        self.assertEqual(org.org_subtype_other, 'Investment holding')


class AdminRequestNotificationTest(TestCase):
    def setUp(self):
        self.client = Client()
        admin = User.objects.create_user(
            username='notify_admin', password='pass', email='admin1@auditax.co.tz')
        UserProfile.objects.create(user=admin, role='admin')
        noemail = User.objects.create_user(username='notify_admin2', password='pass', email='')
        UserProfile.objects.create(user=noemail, role='admin')
        member = User.objects.create_user(
            username='notify_member', password='pass', email='member@example.com')
        UserProfile.objects.create(user=member, role='member')
        mail.outbox = []

    def _valid_post_data(self):
        return {
            'org_name': 'Notify Corp',
            'org_type': 'financial_services',
            'org_subtype': 'banking',
            'org_subtype_other': '',
            'region': 'Mbeya',
            'physical_address': '7 Mbeya Rd',
            'postal_address': 'P.O. Box 7',
            'num_employees': '1_4',
            'investment_capital': 'up_to_5m',
            'first_name': 'Bob',
            'last_name': 'Banda',
            'position': 'CEO',
            'phone_number': '0733000000',
            'email': 'bob@notifycorp.com',
            'website': '',
        }

    def test_email_sent_to_admin_role_users(self):
        self.client.post(reverse('home'), self._valid_post_data())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin1@auditax.co.tz'])

    def test_subject_and_body_contain_org_and_link(self):
        self.client.post(reverse('home'), self._valid_post_data())
        msg = mail.outbox[0]
        self.assertIn('Notify Corp', msg.subject)
        self.assertIn('Notify Corp', msg.body)
        self.assertIn('Bob Banda', msg.body)
        self.assertIn('bob@notifycorp.com', msg.body)
        pr = ParticipationRequest.objects.get(org_name='Notify Corp')
        self.assertIn(f'/accounts/requests/{pr.pk}/', msg.body)

    @override_settings(ADMIN_NOTIFY_EMAILS=['override@auditax.co.tz'])
    def test_override_replaces_admin_role_recipients(self):
        self.client.post(reverse('home'), self._valid_post_data())
        self.assertEqual(mail.outbox[0].to, ['override@auditax.co.tz'])

    def test_honeypot_submission_sends_no_email(self):
        data = self._valid_post_data()
        data['website'] = 'http://spam.example.com'
        self.client.post(reverse('home'), data)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(ParticipationRequest.objects.filter(org_name='Notify Corp').exists())

    def test_submission_succeeds_when_mail_backend_raises(self):
        with patch('accounts.views.send_new_request_notification',
                   side_effect=Exception('smtp down')):
            response = self.client.post(reverse('home'), self._valid_post_data())
        self.assertRedirects(response, reverse('request_submitted'))
        self.assertTrue(ParticipationRequest.objects.filter(org_name='Notify Corp').exists())

    @override_settings(ADMIN_NOTIFY_EMAILS=[])
    def test_no_recipients_sends_nothing(self):
        User.objects.filter(userprofile__role='admin').update(email='')
        self.client.post(reverse('home'), self._valid_post_data())
        self.assertEqual(len(mail.outbox), 0)


class EmailLogModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Log Org')
        self.user = User.objects.create_user(username='logmember@example.com',
                                             email='logmember@example.com', password='pass')
        self.admin = User.objects.create_user(username='logadmin', password='pass')

    def test_create_sent_log(self):
        from accounts.models import EmailLog
        log = EmailLog.objects.create(
            kind='welcome', recipient='logmember@example.com', subject='Welcome',
            status='sent', user=self.user, organization=self.org, triggered_by=self.admin,
        )
        self.assertEqual(log.status, 'sent')
        self.assertEqual(log.error, '')
        self.assertIsNotNone(log.created_at)
        self.assertEqual(self.user.email_logs.count(), 1)
        self.assertEqual(self.org.email_logs.count(), 1)
        self.assertEqual(self.admin.emails_triggered.count(), 1)

    def test_create_failed_log_keeps_error(self):
        from accounts.models import EmailLog
        log = EmailLog.objects.create(
            kind='welcome', recipient='logmember@example.com', subject='Welcome',
            status='failed', error='Exception("Simulated SMTP failure")', user=self.user,
        )
        self.assertEqual(log.status, 'failed')
        self.assertIn('Simulated SMTP failure', log.error)

    def test_ordering_is_newest_first(self):
        from accounts.models import EmailLog
        old = EmailLog.objects.create(kind='welcome', recipient='a@x.com',
                                      subject='A', status='sent')
        new = EmailLog.objects.create(kind='welcome', recipient='b@x.com',
                                      subject='B', status='sent')
        self.assertEqual(list(EmailLog.objects.all())[0], new)
        self.assertEqual(list(EmailLog.objects.all())[1], old)

    def test_fks_survive_user_deletion(self):
        from accounts.models import EmailLog
        EmailLog.objects.create(kind='welcome', recipient='logmember@example.com',
                                subject='Welcome', status='sent', user=self.user)
        self.user.delete()
        log = EmailLog.objects.get()
        self.assertIsNone(log.user)
        self.assertEqual(log.recipient, 'logmember@example.com')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SendAndLogTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Funnel Org')
        self.user = User.objects.create_user(username='funnel@example.com',
                                             email='funnel@example.com',
                                             password='pass', first_name='Fay')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.admin = User.objects.create_user(username='funneladmin', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        mail.outbox = []

    def test_successful_welcome_send_writes_one_sent_row(self):
        from accounts.emails import send_welcome_email
        from accounts.models import EmailLog
        send_welcome_email(self.user, 'TempPass1!', triggered_by=self.admin)
        self.assertEqual(len(mail.outbox), 1)
        log = EmailLog.objects.get()
        self.assertEqual(log.kind, 'welcome')
        self.assertEqual(log.status, 'sent')
        self.assertEqual(log.recipient, 'funnel@example.com')
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.organization, self.org)
        self.assertEqual(log.triggered_by, self.admin)
        self.assertEqual(log.error, '')

    def test_welcome_log_never_stores_the_password(self):
        from accounts.emails import send_welcome_email
        from accounts.models import EmailLog
        send_welcome_email(self.user, 'SuperSecret9!')
        log = EmailLog.objects.get()
        self.assertNotIn('SuperSecret9!', log.subject)
        self.assertNotIn('SuperSecret9!', log.error)

    @override_settings(EMAIL_BACKEND='accounts.tests.BrokenEmailBackend')
    def test_failed_send_writes_failed_row_and_reraises(self):
        from accounts.emails import send_welcome_email
        from accounts.models import EmailLog
        with self.assertRaisesMessage(Exception, 'Simulated SMTP failure'):
            send_welcome_email(self.user, 'TempPass1!')
        log = EmailLog.objects.get()
        self.assertEqual(log.status, 'failed')
        self.assertIn('Simulated SMTP failure', log.error)
        self.assertEqual(log.user, self.user)

    @override_settings(ADMIN_NOTIFY_EMAILS=['a@x.com', 'b@x.com'])
    def test_notification_to_many_admins_writes_one_row(self):
        from accounts.emails import send_new_request_notification
        from accounts.models import EmailLog
        pr = ParticipationRequest.objects.create(
            org_name='Notify Co', org_type='manufacturing', region='Dar',
            physical_address='addr', postal_address='PO 1',
            num_employees='1_4', investment_capital='up_to_5m',
            first_name='Ann', last_name='Bee', phone_number='0712345678',
            email='ann@notify.co',
        )
        send_new_request_notification(pr)
        self.assertEqual(EmailLog.objects.count(), 1)
        log = EmailLog.objects.get()
        self.assertEqual(log.kind, 'new_request')
        self.assertEqual(log.status, 'sent')
        self.assertIn('a@x.com', log.recipient)
        self.assertIn('b@x.com', log.recipient)
        self.assertIsNone(log.user)

    def test_logging_failure_does_not_break_send(self):
        from accounts.emails import send_welcome_email
        with patch('accounts.emails.EmailLog.objects.create',
                   side_effect=Exception('db is on fire')):
            send_welcome_email(self.user, 'TempPass1!')
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='accounts.tests.BrokenEmailBackend')
    def test_send_failure_survives_a_simultaneous_log_failure(self):
        """A DB failure while logging a failed send must not mask the SMTP error."""
        from accounts.emails import send_welcome_email
        with patch('accounts.emails.EmailLog.objects.create',
                   side_effect=Exception('db is on fire')):
            with self.assertRaisesMessage(Exception, 'Simulated SMTP failure'):
                send_welcome_email(self.user, 'TempPass1!')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ResendWelcomeEmailTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Resend Org')
        self.member = User.objects.create_user(username='resend@example.com',
                                               email='resend@example.com',
                                               password='OldPass1!', first_name='Ray')
        self.member_profile = UserProfile.objects.create(
            user=self.member, role='member', organization=self.org,
            must_change_password=False)
        self.admin = User.objects.create_user(username='resendadmin', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.url = f'/accounts/users/{self.member.pk}/resend-welcome/'
        mail.outbox = []

    def test_resend_issues_a_new_password_and_invalidates_the_old(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.check_password('OldPass1!'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('resend@example.com', mail.outbox[0].to)

    def test_resend_rearms_must_change_password(self):
        self.client.force_login(self.admin)
        self.client.post(self.url)
        self.member_profile.refresh_from_db()
        self.assertTrue(self.member_profile.must_change_password)

    def test_emailed_password_actually_works(self):
        self.client.force_login(self.admin)
        self.client.post(self.url)
        body = mail.outbox[0].body
        # welcome.txt renders "  Password: <value>" on its own line
        password = [ln.split('Password:', 1)[1].strip()
                    for ln in body.splitlines() if 'Password:' in ln][0]
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(password))

    def test_resend_writes_email_log_and_audit_log(self):
        from accounts.models import EmailLog
        from audit.models import AuditLog
        self.client.force_login(self.admin)
        self.client.post(self.url)
        log = EmailLog.objects.get()
        self.assertEqual(log.kind, 'welcome')
        self.assertEqual(log.status, 'sent')
        self.assertEqual(log.triggered_by, self.admin)
        self.assertEqual(AuditLog.objects.filter(action='email.welcome_resent').count(), 1)

    def test_resend_rejects_get(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_rejects_non_admin(self):
        self.client.force_login(self.member)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password('OldPass1!'))

    def test_resend_rejects_non_member_target(self):
        """Any non-member role is refused — not just verifiers."""
        verifier = User.objects.create_user(username='v1', email='v1@example.com',
                                            password='VPass1!')
        UserProfile.objects.create(user=verifier, role='verifier')
        other_admin = User.objects.create_user(username='a2', email='a2@example.com',
                                               password='VPass1!')
        UserProfile.objects.create(user=other_admin, role='admin')
        self.client.force_login(self.admin)
        for target in (verifier, other_admin):
            with self.subTest(role=target.userprofile.role):
                resp = self.client.post(f'/accounts/users/{target.pk}/resend-welcome/')
                self.assertEqual(resp.status_code, 302)
                self.assertEqual(resp.url, '/accounts/users/')
                self.assertEqual(len(mail.outbox), 0)
                target.refresh_from_db()
                self.assertTrue(target.check_password('VPass1!'))

    @override_settings(EMAIL_BACKEND='accounts.tests.BrokenEmailBackend')
    def test_failed_resend_stores_credentials_in_session(self):
        from accounts.models import EmailLog
        self.client.force_login(self.admin)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('approval_credentials', self.client.session)
        self.assertEqual(self.client.session['approval_credentials']['username'],
                         'resend@example.com')
        self.assertEqual(EmailLog.objects.get().status, 'failed')
        # password was still rotated, so the admin can hand it over manually
        self.member.refresh_from_db()
        self.assertFalse(self.member.check_password('OldPass1!'))
        # and the stashed password is the live one — that is the whole point of
        # stashing it, so the admin hands over credentials that actually work
        self.assertTrue(self.member.check_password(
            self.client.session['approval_credentials']['password']))

    def test_welcome_template_warns_prior_password_is_void(self):
        self.client.force_login(self.admin)
        self.client.post(self.url)
        self.assertIn('no longer valid', mail.outbox[0].body)

    def test_successful_resend_ignores_stale_approval_credentials(self):
        """A leftover approval_credentials key must not divert a successful resend.

        request_approve_view stashes approval_credentials and only
        request_approval_success_view pops it, so an admin who abandons the
        approval-success page carries the key into later requests. A successful
        resend must still land on user_list rather than showing another
        organisation's stale credentials next to a success message.
        """
        self.client.force_login(self.admin)
        session = self.client.session
        session['approval_credentials'] = {
            'org_name': 'Some Other Org', 'username': 'someone@example.com',
            'password': 'StalePass1!', 'email': 'someone@example.com',
        }
        session.save()

        resp = self.client.post(self.url)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/accounts/users/')
        self.assertEqual(len(mail.outbox), 1)
        # the stale entry is left untouched, not consumed or overwritten
        self.assertEqual(self.client.session['approval_credentials']['username'],
                         'someone@example.com')


class UserListEmailStatusTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Status Org')
        self.admin = User.objects.create_user(username='statusadmin', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.sent_user = User.objects.create_user(username='sent@example.com',
                                                  email='sent@example.com', password='p')
        UserProfile.objects.create(user=self.sent_user, role='member', organization=self.org)
        self.failed_user = User.objects.create_user(username='failed@example.com',
                                                    email='failed@example.com', password='p')
        UserProfile.objects.create(user=self.failed_user, role='member', organization=self.org)
        self.never_user = User.objects.create_user(username='never@example.com',
                                                   email='never@example.com', password='p')
        UserProfile.objects.create(user=self.never_user, role='member', organization=self.org)
        self.client.force_login(self.admin)

    def test_shows_sent_failed_and_never_states(self):
        from accounts.models import EmailLog
        EmailLog.objects.create(kind='welcome', recipient=self.sent_user.email,
                                subject='W', status='sent', user=self.sent_user)
        EmailLog.objects.create(kind='welcome', recipient=self.failed_user.email,
                                subject='W', status='failed',
                                error='Connection timed out', user=self.failed_user)
        resp = self.client.get('/accounts/users/')
        self.assertEqual(resp.status_code, 200)
        by_user = {u.pk: u.welcome_email_log for u in resp.context['page_obj']}
        self.assertEqual(by_user[self.sent_user.pk].status, 'sent')
        self.assertEqual(by_user[self.failed_user.pk].status, 'failed')
        self.assertIsNone(by_user[self.never_user.pk])
        self.assertContains(resp, 'Never sent')

    def test_uses_latest_log_per_user(self):
        from accounts.models import EmailLog
        EmailLog.objects.create(kind='welcome', recipient=self.sent_user.email,
                                subject='W', status='failed', error='old failure',
                                user=self.sent_user)
        EmailLog.objects.create(kind='welcome', recipient=self.sent_user.email,
                                subject='W', status='sent', user=self.sent_user)
        resp = self.client.get('/accounts/users/')
        by_user = {u.pk: u.welcome_email_log for u in resp.context['page_obj']}
        self.assertEqual(by_user[self.sent_user.pk].status, 'sent')

    def test_ignores_non_welcome_kinds(self):
        from accounts.models import EmailLog
        EmailLog.objects.create(kind='password_reset', recipient=self.never_user.email,
                                subject='R', status='sent', user=self.never_user)
        resp = self.client.get('/accounts/users/')
        by_user = {u.pk: u.welcome_email_log for u in resp.context['page_obj']}
        self.assertIsNone(by_user[self.never_user.pk])

    def test_status_lookup_costs_one_extra_query_regardless_of_row_count(self):
        from accounts.models import EmailLog
        for u in (self.sent_user, self.failed_user, self.never_user):
            EmailLog.objects.create(kind='welcome', recipient=u.email, subject='W',
                                    status='sent', user=u)
        with self.assertNumQueries(7):
            self.client.get('/accounts/users/')


class EmailLogViewTest(TestCase):
    def setUp(self):
        from accounts.models import EmailLog
        self.admin = User.objects.create_user(username='emailadmin', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.member = User.objects.create_user(username='m@example.com',
                                               email='m@example.com', password='p')
        UserProfile.objects.create(user=self.member, role='member')
        EmailLog.objects.create(kind='welcome', recipient='m@example.com',
                                subject='Welcome', status='sent', user=self.member)
        EmailLog.objects.create(kind='new_request', recipient='admin@x.com',
                                subject='New request', status='failed',
                                error='Connection refused')

    def test_requires_admin(self):
        self.client.force_login(self.member)
        resp = self.client.get('/emails/')
        self.assertEqual(resp.status_code, 302)

    def test_requires_login(self):
        resp = self.client.get('/emails/')
        self.assertEqual(resp.status_code, 302)

    def test_lists_all_rows_for_admin(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/emails/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['page_obj'].object_list), 2)

    def test_kind_filter(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/emails/?kind=welcome')
        rows = resp.context['page_obj'].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, 'welcome')

    def test_status_filter(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/emails/?status=failed')
        rows = resp.context['page_obj'].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, 'failed')
        self.assertContains(resp, 'Connection refused')

    def test_date_filters(self):
        from django.utils import timezone
        self.client.force_login(self.admin)
        today = timezone.localdate().isoformat()
        resp = self.client.get(f'/emails/?date_from={today}&date_to={today}')
        self.assertEqual(len(resp.context['page_obj'].object_list), 2)
        resp = self.client.get('/emails/?date_from=2000-01-01&date_to=2000-01-02')
        self.assertEqual(len(resp.context['page_obj'].object_list), 0)

    def test_empty_state(self):
        from accounts.models import EmailLog
        EmailLog.objects.all().delete()
        self.client.force_login(self.admin)
        resp = self.client.get('/emails/')
        self.assertContains(resp, 'No email records found')

    def test_malformed_date_does_not_crash(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/emails/?date_from=not-a-date')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['page_obj'].object_list), 2)

        resp = self.client.get('/emails/?date_to=not-a-date')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['page_obj'].object_list), 2)
