from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import ShareLink, generate_token


class ShareLinkModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sl_admin', password='pass')

    def test_token_is_generated_and_long(self):
        link = ShareLink.objects.create(label='Board', created_by=self.user)
        self.assertGreaterEqual(len(link.token), 40)

    def test_tokens_are_unique(self):
        a = ShareLink.objects.create(label='A')
        b = ShareLink.objects.create(label='B')
        self.assertNotEqual(a.token, b.token)

    def test_generate_token_returns_distinct_values(self):
        self.assertNotEqual(generate_token(), generate_token())

    def test_active_link_without_expiry_is_valid(self):
        self.assertTrue(ShareLink.objects.create(label='A').is_valid)

    def test_inactive_link_is_not_valid(self):
        link = ShareLink.objects.create(label='A', is_active=False)
        self.assertFalse(link.is_valid)

    def test_expired_link_is_not_valid(self):
        link = ShareLink.objects.create(
            label='A', expires_at=timezone.now() - timedelta(days=1))
        self.assertFalse(link.is_valid)

    def test_future_expiry_is_valid(self):
        link = ShareLink.objects.create(
            label='A', expires_at=timezone.now() + timedelta(days=1))
        self.assertTrue(link.is_valid)

    def test_defaults(self):
        link = ShareLink.objects.create(label='A')
        self.assertFalse(link.include_contacts)
        self.assertTrue(link.is_active)
        self.assertEqual(link.view_count, 0)
        self.assertIsNone(link.last_viewed_at)


from accounts.models import Organization, UserProfile, ParticipationRequest
from assessment.models import AwardCycle, Questionnaire

from .reporting import build_submission_report


class BuildSubmissionReportTest(TestCase):
    def setUp(self):
        # Organizations must exist BEFORE the cycle is opened — AwardCycle.save()
        # auto-creates Questionnaires only for orgs that exist at open time.
        self.org_a = Organization.objects.create(
            name='Alpha Ltd', org_type='financial_services', region='Dar es Salaam')
        self.org_b = Organization.objects.create(
            name='Beta Ltd', org_type='manufacturing', region='Mwanza')
        self.org_nomember = Organization.objects.create(
            name='Gamma Ltd', org_type='ict', region='Arusha')
        self.org_inactive = Organization.objects.create(
            name='Zeta Ltd', org_type='ict', region='Dodoma', is_active=False)

        user_a = User.objects.create_user(
            username='a@alpha.co.tz', email='a@alpha.co.tz',
            password='pass', first_name='Anna', last_name='Alpha')
        UserProfile.objects.create(
            user=user_a, role='member', organization=self.org_a, phone_number='0711000001')
        user_b = User.objects.create_user(
            username='b@beta.co.tz', email='b@beta.co.tz',
            password='pass', first_name='Ben', last_name='Beta')
        UserProfile.objects.create(
            user=user_b, role='member', organization=self.org_b, phone_number='0711000002')

        ParticipationRequest.objects.create(
            org_name='Alpha Ltd', org_type='financial_services', region='Dar es Salaam',
            physical_address='1 Rd', postal_address='P.O. Box 1',
            num_employees='5_49', investment_capital='up_to_5m',
            first_name='Anna', last_name='Alpha', position='HR Manager',
            phone_number='0711000001', email='A@Alpha.co.tz')

        self.cycle = AwardCycle.objects.create(year=2031, name='EYA 2031', is_open=True)
        Questionnaire.objects.filter(
            cycle=self.cycle, organization=self.org_a
        ).update(is_submitted=True)

    def test_kpis(self):
        report = build_submission_report(include_contacts=True)
        kpis = report['kpis']
        self.assertEqual(kpis['total_orgs'], 3)          # inactive org excluded
        self.assertEqual(kpis['submitted_count'], 1)
        self.assertEqual(kpis['member_count'], 2)
        self.assertEqual(kpis['orgs_without_member'], 1)
        self.assertEqual(kpis['submission_rate'], round(1 / 3 * 100, 1))

    def test_inactive_org_excluded_from_rows(self):
        report = build_submission_report(include_contacts=True)
        self.assertNotIn('Zeta Ltd', [r['org'] for r in report['rows']])

    def test_rows_sorted_by_org_name(self):
        report = build_submission_report(include_contacts=True)
        self.assertEqual([r['org'] for r in report['rows']],
                         ['Alpha Ltd', 'Beta Ltd', 'Gamma Ltd'])

    def test_submitted_flag_and_timestamp(self):
        report = build_submission_report(include_contacts=True)
        rows = {r['org']: r for r in report['rows']}
        self.assertTrue(rows['Alpha Ltd']['submitted'])
        self.assertFalse(rows['Beta Ltd']['submitted'])

    def test_contacts_included_when_flag_true(self):
        report = build_submission_report(include_contacts=True)
        row = next(r for r in report['rows'] if r['org'] == 'Alpha Ltd')
        self.assertEqual(row['name'], 'Anna Alpha')
        self.assertEqual(row['phone'], '0711000001')
        self.assertEqual(row['email'], 'a@alpha.co.tz')

    def test_position_resolved_from_request_case_insensitively(self):
        report = build_submission_report(include_contacts=True)
        row = next(r for r in report['rows'] if r['org'] == 'Alpha Ltd')
        self.assertEqual(row['position'], 'HR Manager')

    def test_contacts_omitted_when_flag_false(self):
        report = build_submission_report(include_contacts=False)
        for row in report['rows']:
            for key in ('name', 'position', 'phone', 'email'):
                self.assertNotIn(key, row)

    def test_org_without_member_has_blank_contacts(self):
        report = build_submission_report(include_contacts=True)
        row = next(r for r in report['rows'] if r['org'] == 'Gamma Ltd')
        self.assertEqual(row['name'], '')
        self.assertEqual(row['email'], '')

    def test_by_position_always_present_and_bucketed(self):
        report = build_submission_report(include_contacts=False)
        buckets = {b['position']: b['count'] for b in report['by_position']}
        self.assertEqual(buckets.get('HR / People'), 1)
        self.assertEqual(buckets.get('Unspecified'), 2)

    def test_cycle_metadata(self):
        report = build_submission_report(include_contacts=False)
        self.assertEqual(report['cycle']['name'], 'EYA 2031')
        self.assertEqual(report['cycle']['year'], 2031)

    def test_no_open_cycle(self):
        AwardCycle.objects.filter(pk=self.cycle.pk).update(is_open=False)
        report = build_submission_report(include_contacts=False)
        self.assertIsNone(report['cycle'])
        self.assertEqual(report['kpis']['submitted_count'], 0)
        self.assertEqual(report['kpis']['submission_rate'], 0)
        self.assertEqual(len(report['rows']), 3)

    def test_result_is_json_serialisable(self):
        import json
        json.dumps(build_submission_report(include_contacts=True))

    def test_query_count_is_flat(self):
        with self.assertNumQueries(6):
            build_submission_report(include_contacts=True)


import json

from django.urls import reverse


class PublicDashboardViewTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='Alpha Ltd', org_type='ict', region='Dar es Salaam')
        user = User.objects.create_user(
            username='a@alpha.co.tz', email='a@alpha.co.tz',
            password='pass', first_name='Anna', last_name='Alpha')
        UserProfile.objects.create(
            user=user, role='member', organization=self.org, phone_number='0711000001')
        self.cycle = AwardCycle.objects.create(year=2032, name='EYA 2032', is_open=True)
        self.link = ShareLink.objects.create(label='Board', include_contacts=True)
        self.private = ShareLink.objects.create(label='Public', include_contacts=False)

    def test_valid_token_returns_200(self):
        response = self.client.get(reverse('public_dashboard', args=[self.link.token]))
        self.assertEqual(response.status_code, 200)

    def test_security_headers(self):
        response = self.client.get(reverse('public_dashboard', args=[self.link.token]))
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_unknown_token_404s(self):
        response = self.client.get(reverse('public_dashboard', args=['not-a-real-token']))
        self.assertEqual(response.status_code, 404)

    def test_revoked_token_404s(self):
        self.link.is_active = False
        self.link.save()
        response = self.client.get(reverse('public_dashboard', args=[self.link.token]))
        self.assertEqual(response.status_code, 404)

    def test_expired_token_404s(self):
        self.link.expires_at = timezone.now() - timedelta(hours=1)
        self.link.save()
        response = self.client.get(reverse('public_dashboard', args=[self.link.token]))
        self.assertEqual(response.status_code, 404)

    def test_no_login_required(self):
        response = self.client.get(reverse('public_dashboard', args=[self.link.token]))
        self.assertNotIn('/login/', response.get('Location', ''))
        self.assertEqual(response.status_code, 200)

    def test_contacts_hidden_link_leaks_no_pii(self):
        response = self.client.get(reverse('public_dashboard', args=[self.private.token]))
        body = response.content.decode()
        self.assertNotIn('0711000001', body)
        self.assertNotIn('a@alpha.co.tz', body)
        self.assertIn('Alpha Ltd', body)

    def test_json_endpoint_returns_report(self):
        response = self.client.get(reverse('public_dashboard_data', args=[self.link.token]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('kpis', data)
        self.assertIn('rows', data)
        self.assertTrue(data['include_contacts'])

    def test_json_endpoint_respects_contacts_flag(self):
        response = self.client.get(reverse('public_dashboard_data', args=[self.private.token]))
        data = json.loads(response.content)
        self.assertFalse(data['include_contacts'])
        for row in data['rows']:
            self.assertNotIn('phone', row)

    def test_json_endpoint_404s_for_revoked_token(self):
        self.private.is_active = False
        self.private.save()
        response = self.client.get(reverse('public_dashboard_data', args=[self.private.token]))
        self.assertEqual(response.status_code, 404)

    def test_html_load_increments_view_count(self):
        self.client.get(reverse('public_dashboard', args=[self.link.token]))
        self.link.refresh_from_db()
        self.assertEqual(self.link.view_count, 1)
        self.assertIsNotNone(self.link.last_viewed_at)

    def test_json_poll_does_not_increment_view_count(self):
        self.client.get(reverse('public_dashboard_data', args=[self.link.token]))
        self.link.refresh_from_db()
        self.assertEqual(self.link.view_count, 0)


from audit.models import AuditLog


class ShareLinkAdminViewTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='sl_admin2', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.member = User.objects.create_user(username='sl_member', password='pass')
        UserProfile.objects.create(user=self.member, role='member')
        self.link = ShareLink.objects.create(label='Existing', created_by=self.admin)

    def test_list_requires_admin(self):
        self.client.login(username='sl_member', password='pass')
        response = self.client.get(reverse('sharelink_list'))
        self.assertEqual(response.status_code, 302)

    def test_list_requires_login(self):
        response = self.client.get(reverse('sharelink_list'))
        self.assertEqual(response.status_code, 302)

    def test_admin_sees_list(self):
        self.client.login(username='sl_admin2', password='pass')
        response = self.client.get(reverse('sharelink_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Existing')

    def test_create_makes_link_and_logs(self):
        self.client.login(username='sl_admin2', password='pass')
        response = self.client.post(reverse('sharelink_create'), {
            'label': 'Board of Directors',
            'include_contacts': 'on',
        })
        self.assertRedirects(response, reverse('sharelink_list'))
        link = ShareLink.objects.get(label='Board of Directors')
        self.assertTrue(link.include_contacts)
        self.assertEqual(link.created_by, self.admin)
        self.assertTrue(AuditLog.objects.filter(action='sharelink.created').exists())

    def test_create_requires_admin(self):
        self.client.login(username='sl_member', password='pass')
        response = self.client.post(reverse('sharelink_create'), {'label': 'Nope'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ShareLink.objects.filter(label='Nope').exists())

    def test_revoke_deactivates_and_logs(self):
        self.client.login(username='sl_admin2', password='pass')
        response = self.client.post(reverse('sharelink_revoke', args=[self.link.pk]))
        self.assertRedirects(response, reverse('sharelink_list'))
        self.link.refresh_from_db()
        self.assertFalse(self.link.is_active)
        self.assertTrue(AuditLog.objects.filter(action='sharelink.revoked').exists())

    def test_revoked_link_url_404s(self):
        self.client.login(username='sl_admin2', password='pass')
        self.client.post(reverse('sharelink_revoke', args=[self.link.pk]))
        self.client.logout()
        response = self.client.get(reverse('public_dashboard', args=[self.link.token]))
        self.assertEqual(response.status_code, 404)

    def test_revoke_rejects_get(self):
        self.client.login(username='sl_admin2', password='pass')
        response = self.client.get(reverse('sharelink_revoke', args=[self.link.pk]))
        self.assertEqual(response.status_code, 405)
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_active)
