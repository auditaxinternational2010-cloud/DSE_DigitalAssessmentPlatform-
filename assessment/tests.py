import json
import re

from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import Organization, UserProfile
from .models import (
    AwardCycle, AssessmentCategory, Criterion, Questionnaire, VerifierResponse, Response,
    EvidenceDocument, EvidenceLink, LevelIndicator,
)


class EvidenceDocumentModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Ev Doc Org')
        self.user = User.objects.create_user(username='evdoc_user', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)

    def test_evidence_upload_path_uses_uuid_prefix(self):
        from assessment.models import evidence_upload_path
        doc = EvidenceDocument(organization=self.org)
        path = evidence_upload_path(doc, 'my report.pdf')
        parts = path.split('/')
        self.assertEqual(parts[0], 'evidence')
        self.assertEqual(parts[1], str(self.org.id))
        # Third part: <uuid>_my_report.pdf
        self.assertIn('_my_report.pdf', parts[2])
        self.assertEqual(len(parts[2].split('_')[0]), 32)  # uuid4 hex = 32 chars

    def test_evidence_upload_path_sanitizes_spaces_and_special_chars(self):
        from assessment.models import evidence_upload_path
        doc = EvidenceDocument(organization=self.org)
        path = evidence_upload_path(doc, 'my file (2024).pdf')
        filename_part = path.split('/')[-1]
        self.assertNotIn(' ', filename_part)
        self.assertNotIn('(', filename_part)
        self.assertNotIn(')', filename_part)

    def test_evidence_upload_path_strips_directory_traversal(self):
        from assessment.models import evidence_upload_path
        doc = EvidenceDocument(organization=self.org)
        path = evidence_upload_path(doc, '../../etc/passwd')
        self.assertNotIn('..', path)
        self.assertNotIn('/', path.split('/')[-1])  # no slash in filename part

    def test_evidencelink_unique_per_response_document(self):
        from django.db import IntegrityError
        cycle = AwardCycle.objects.create(year=2099, name='DSE 2099', is_open=True)
        q = Questionnaire.objects.get_or_create(cycle=cycle, organization=self.org)[0]
        cat = AssessmentCategory.objects.create(cycle=cycle, name='Cat', order=1)
        crit = Criterion.objects.create(category=cat, number=1, name='C1', order=1)
        resp = Response.objects.create(questionnaire=q, criterion=crit)
        doc = EvidenceDocument.objects.create(
            organization=self.org, title='Test', original_filename='test.pdf', file_size=100
        )
        EvidenceLink.objects.create(response=resp, document=doc)
        with self.assertRaises(IntegrityError):
            EvidenceLink.objects.create(response=resp, document=doc)


class AwardCycleTest(TestCase):
    def test_only_one_open_cycle_at_a_time(self):
        cycle1 = AwardCycle.objects.create(year=2024, name='DSE 2024', is_open=True)
        cycle2 = AwardCycle.objects.create(year=2025, name='DSE 2025', is_open=True)
        cycle1.refresh_from_db()
        self.assertFalse(cycle1.is_open)
        self.assertTrue(cycle2.is_open)

    def test_questionnaires_are_not_created_when_cycle_opens(self):
        org = Organization.objects.create(name='Org A')
        cycle = AwardCycle.objects.create(year=2025, name='DSE 2025')
        self.assertFalse(Questionnaire.objects.filter(cycle=cycle).exists())
        cycle.is_open = True
        cycle.save()
        self.assertFalse(
            Questionnaire.objects.filter(cycle=cycle, organization=org).exists()
        )

    def test_questionnaire_unique_per_cycle_org(self):
        from django.db import IntegrityError
        org = Organization.objects.create(name='Org B')
        cycle = AwardCycle.objects.create(year=2026, name='DSE 2026')
        Questionnaire.objects.create(cycle=cycle, organization=org)
        with self.assertRaises(IntegrityError):
            Questionnaire.objects.create(cycle=cycle, organization=org)

    def test_opening_cycle_does_not_assign_all_active_orgs(self):
        org1 = Organization.objects.create(name='Atomic Org 1', is_active=True)
        org2 = Organization.objects.create(name='Atomic Org 2', is_active=True)
        Organization.objects.create(name='Inactive Org', is_active=False)
        cycle = AwardCycle.objects.create(year=2050, name='DSE 2050')
        cycle.is_open = True
        cycle.save()
        self.assertFalse(
            Questionnaire.objects.filter(
                cycle=cycle, organization__in=[org1, org2]
            ).exists()
        )


import io
import openpyxl
from .models import LevelIndicator


class ExcelParserTest(TestCase):
    """Tests for the current DSE workbook layout (13 columns)."""

    def _make_excel(self, *, include_second_parameter=True, sheet_name='Bond Issuer'):
        import io
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name
        ws.append([
            'Code', 'Assessment Category', 'S/N', 'Assessment Areas',
            'S/N', 'Assessment Criteria', 'S/N', 'Measurable Parameters',
            'Relevant Act / Guideline / Regulation', 'Weight (%)',
            'Response', 'Remarks', 'Score',
        ])
        ws.append([
            '1', 'Leadership', '1', 'Governance', '1',
            'Board oversight', '1.1', 'Board charter is documented',
            'Companies Act', 0.25, None, None, None,
        ])
        if include_second_parameter:
            ws.append([
                None, None, None, None, None, None, '1.2',
                'Board meetings are recorded', 'DSE Rules', 0.15,
                None, None, None,
            ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def setUp(self):
        self.cycle = AwardCycle.objects.create(year=2025, name='DSE 2025')

    def test_parser_creates_template_and_category(self):
        from .excel_parser import parse_excel_questionnaire
        parse_excel_questionnaire(self._make_excel(), self.cycle)
        from .models import QuestionnaireTemplate
        template = QuestionnaireTemplate.objects.get(cycle=self.cycle, code='bond_issuer')
        self.assertTrue(
            AssessmentCategory.objects.filter(
                cycle=self.cycle, template=template, code='1', name='Leadership'
            ).exists()
        )

    def test_parser_creates_measurable_parameters(self):
        from .excel_parser import parse_excel_questionnaire
        parse_excel_questionnaire(self._make_excel(), self.cycle)
        self.assertEqual(
            Criterion.objects.filter(category__cycle=self.cycle).count(), 2
        )

    def test_parser_maps_hierarchy_regulation_and_weight(self):
        from .excel_parser import parse_excel_questionnaire
        parse_excel_questionnaire(self._make_excel(), self.cycle)
        criterion = Criterion.objects.get(
            category__cycle=self.cycle, number='1.1'
        )
        self.assertEqual(criterion.name, 'Board charter is documented')
        self.assertEqual(criterion.assessment_area, 'Governance')
        self.assertEqual(criterion.assessment_criterion, 'Board oversight')
        self.assertEqual(criterion.regulation, 'Companies Act')
        self.assertEqual(str(criterion.weight), '0.25000000')

    def test_parser_reupload_updates_existing_parameters_without_duplicates(self):
        from .excel_parser import parse_excel_questionnaire
        parse_excel_questionnaire(self._make_excel(), self.cycle)
        parse_excel_questionnaire(self._make_excel(), self.cycle)
        self.assertEqual(
            Criterion.objects.filter(category__cycle=self.cycle).count(), 2
        )

    def test_parser_skips_unrecognised_sheet(self):
        from .excel_parser import parse_excel_questionnaire
        warnings = parse_excel_questionnaire(
            self._make_excel(sheet_name='Unrecognised Sheet'), self.cycle
        )
        self.assertTrue(any('skipped' in warning for warning in warnings))
        self.assertFalse(AssessmentCategory.objects.filter(cycle=self.cycle).exists())

    def test_parser_returns_warning_for_corrupt_file(self):
        import io
        from .excel_parser import parse_excel_questionnaire
        corrupt = io.BytesIO(b'not an Excel workbook')
        warnings = parse_excel_questionnaire(corrupt, self.cycle)
        self.assertEqual(len(warnings), 1)
        self.assertIn('Could not read Excel file', warnings[0])

    def test_parser_returns_warning_for_empty_bytes(self):
        import io
        from .excel_parser import parse_excel_questionnaire
        warnings = parse_excel_questionnaire(io.BytesIO(b''), self.cycle)
        self.assertEqual(len(warnings), 1)
        self.assertIn('Could not read Excel file', warnings[0])

class NumericCriterionModelTest(TestCase):
    def setUp(self):
        from accounts.models import Organization
        self.org = Organization.objects.create(name='TestOrg', org_type='Private Sector')
        self.cycle = AwardCycle.objects.create(year=2030, name='DSE 2030', is_open=False)
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='Cat', order=0)
        self.numeric_crit = Criterion.objects.create(
            category=self.cat, number=1, name='Employment Data',
            is_numeric=True,
            numeric_fields=[
                {'name': 'Employees 2024', 'type': 'integer'},
                {'name': 'Turnover rate 2024 (%)', 'type': 'decimal'},
            ],
        )
        self.score_crit = Criterion.objects.create(
            category=self.cat, number=2, name='Normal Criterion',
            is_numeric=False,
        )
        self.questionnaire = Questionnaire.objects.create(cycle=self.cycle, organization=self.org)

    def test_criterion_is_numeric_defaults_false(self):
        c = Criterion.objects.create(category=self.cat, number=3, name='Another')
        self.assertFalse(c.is_numeric)

    def test_criterion_numeric_fields_defaults_empty_list(self):
        c = Criterion.objects.create(category=self.cat, number=4, name='Another2')
        self.assertEqual(c.numeric_fields, [])

    def test_response_numeric_data_defaults_none(self):
        resp = Response.objects.create(questionnaire=self.questionnaire, criterion=self.score_crit)
        self.assertIsNone(resp.numeric_data)

    def test_completion_percentage_counts_numeric_response(self):
        Response.objects.create(
            questionnaire=self.questionnaire, criterion=self.numeric_crit,
            numeric_data={'Employees 2024': 100, 'Turnover rate 2024 (%)': 12.5},
        )
        # score_crit unanswered → 1 of 2 answered = 50%
        self.assertEqual(self.questionnaire.completion_percentage, 50.0)

    def test_completion_percentage_excludes_empty_numeric_data(self):
        # numeric_data=None → not counted
        Response.objects.create(
            questionnaire=self.questionnaire, criterion=self.numeric_crit,
            numeric_data=None,
        )
        self.assertEqual(self.questionnaire.completion_percentage, 0)

    def test_completion_percentage_does_not_double_count_mixed_response(self):
        Response.objects.create(
            questionnaire=self.questionnaire,
            criterion=self.numeric_crit,
            score=3,
            numeric_data={'Employees 2024': 100},
        )
        # 1 of 2 criteria answered = 50%
        self.assertEqual(self.questionnaire.completion_percentage, 50.0)


class NumericCriterionFillViewTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from accounts.models import Organization, UserProfile
        self.user = User.objects.create_user('member1', password='Pass@1234')
        self.org = Organization.objects.create(name='OrgA', org_type='Private Sector')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        # Create cycle with is_open=False first to add criteria before opening
        self.cycle = AwardCycle.objects.create(year=2031, name='DSE 2031', is_open=False)
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='Talent', order=0)
        self.numeric_crit = Criterion.objects.create(
            category=self.cat, number=1, name='Employment Data',
            is_numeric=True,
            numeric_fields=[
                {'name': 'Employees 2024', 'type': 'integer'},
                {'name': 'Turnover rate 2024 (%)', 'type': 'decimal'},
            ],
        )
        # Open the cycle so the view accepts it; auto-creates questionnaire for self.org
        self.cycle.is_open = True
        self.cycle.save()
        self.questionnaire = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.client.login(username='member1', password='Pass@1234')

    def test_numeric_values_in_criteria_data_context(self):
        url = reverse('questionnaire_fill', args=[self.questionnaire.pk])
        resp = self.client.get(url, {'category': self.cat.id},
                               HTTP_X_FORWARDED_PROTO='https')
        item = resp.context['criteria_data'][0]
        self.assertIn('numeric_values', item)
        self.assertEqual(len(item['numeric_values']), 2)
        # Values should be empty strings when no response exists
        self.assertEqual(item['numeric_values'][0][1], '')

    def test_post_saves_numeric_data(self):
        url = reverse('save_category', args=[self.questionnaire.pk])
        self.client.post(url, {
            'category_id': self.cat.id,
            f'numeric_{self.numeric_crit.id}_0': '150',
            f'numeric_{self.numeric_crit.id}_1': '12.5',
        }, HTTP_X_FORWARDED_PROTO='https')
        resp = Response.objects.get(questionnaire=self.questionnaire, criterion=self.numeric_crit)
        self.assertEqual(resp.numeric_data['Employees 2024'], 150)
        self.assertAlmostEqual(resp.numeric_data['Turnover rate 2024 (%)'], 12.5)

    def test_numeric_criterion_counted_in_answered_count(self):
        Response.objects.create(
            questionnaire=self.questionnaire, criterion=self.numeric_crit,
            numeric_data={'Employees 2024': 50},
        )
        url = reverse('questionnaire_fill', args=[self.questionnaire.pk])
        resp = self.client.get(url, {'category': self.cat.id},
                               HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(resp.context['answered_count'], 1)


class NumericCriterionVerifierViewTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from accounts.models import Organization, UserProfile, VerifierAssignment
        self.verifier = User.objects.create_user('verifier1', password='Pass@1234')
        self.org = Organization.objects.create(name='OrgB', org_type='Private Sector')
        profile, created = UserProfile.objects.get_or_create(user=self.verifier, defaults={'role': 'verifier'})
        if not created:
            profile.role = 'verifier'
            profile.save()
        VerifierAssignment.objects.create(verifier=self.verifier, organization=self.org)
        self.cycle = AwardCycle.objects.create(year=2032, name='DSE 2032', is_open=True)
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='Talent', order=0)
        self.numeric_crit = Criterion.objects.create(
            category=self.cat, number=1, name='Employment Data',
            is_numeric=True,
            numeric_fields=[{'name': 'Employees 2024', 'type': 'integer'}],
        )
        self.questionnaire = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.questionnaire.is_submitted = True
        self.questionnaire.save()
        Response.objects.create(
            questionnaire=self.questionnaire, criterion=self.numeric_crit,
            numeric_data={'Employees 2024': 120},
        )
        self.client.login(username='verifier1', password='Pass@1234')

    def test_verifier_post_saves_notes_for_numeric_criterion(self):
        url = reverse('verify_questionnaire', args=[self.questionnaire.pk])
        self.client.post(url, {
            'category_id': self.cat.id,
            f'notes_{self.numeric_crit.id}': 'Verified headcount via HR records.',
        }, HTTP_X_FORWARDED_PROTO='https')
        vr = VerifierResponse.objects.get(
            questionnaire=self.questionnaire,
            verifier=self.verifier,
            criterion=self.numeric_crit,
        )
        self.assertIsNone(vr.score)
        self.assertEqual(vr.notes, 'Verified headcount via HR records.')


from django.test import Client
from django.urls import reverse
from accounts.models import Organization as Org2, UserProfile as UP2, VerifierAssignment as VA2


class WorkflowTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User as U
        self.client = Client()
        self.org = Org2.objects.create(name='Org A Workflow')
        self.member_user = U.objects.create_user(username='mem_wf', password='pass')
        UP2.objects.create(user=self.member_user, role='member', organization=self.org)
        self.verifier_user = U.objects.create_user(username='ver_wf', password='pass')
        UP2.objects.create(user=self.verifier_user, role='verifier')
        VA2.objects.create(verifier=self.verifier_user, organization=self.org)
        self.cycle = AwardCycle.objects.create(year=2030, name='DSE 2030', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]

    def test_member_cannot_access_verifier_view_before_submit(self):
        self.client.login(username='mem_wf', password='pass')
        response = self.client.get(reverse('verify_questionnaire', args=[self.q.pk]))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_verifier_cannot_access_unsubmitted_questionnaire(self):
        self.client.login(username='ver_wf', password='pass')
        response = self.client.get(reverse('verify_questionnaire', args=[self.q.pk]))
        self.assertEqual(response.status_code, 404)

    def test_verifier_can_access_after_member_submits(self):
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        self.client.login(username='ver_wf', password='pass')
        response = self.client.get(reverse('verify_questionnaire', args=[self.q.pk]))
        self.assertEqual(response.status_code, 200)


class AdminDashboardContextTest(TestCase):
    def setUp(self):
        self.client = Client()
        admin_user = User.objects.create_user(username='admin_ctx', password='pass')
        UserProfile.objects.create(user=admin_user, role='admin')
        self.client.login(username='admin_ctx', password='pass')
        self.org = Organization.objects.create(name='Org Admin Ctx')
        self.cycle = AwardCycle.objects.create(year=2033, name='DSE 2033', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]

    def test_context_includes_org_data(self):
        response = self.client.get(reverse('admin_dashboard'))
        self.assertIn('org_data', response.context)
        self.assertEqual(len(response.context['org_data']), 1)
        entry = response.context['org_data'][0]
        self.assertEqual(entry['org'], self.org)
        self.assertIn('answered_count', entry)
        self.assertIn('verified_count', entry)

    def test_context_includes_submission_rate(self):
        response = self.client.get(reverse('admin_dashboard'))
        self.assertIn('submission_rate', response.context)
        self.assertEqual(response.context['submission_rate'], 0)

    def test_submission_rate_100_when_all_submitted(self):
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.context['submission_rate'], 100)


class QuestionnaireFillContextTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='Fill Ctx Org')
        self.user = User.objects.create_user(username='fill_ctx', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='fill_ctx', password='pass')
        self.cycle = AwardCycle.objects.create(year=2034, name='DSE 2034', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Fill Cat', order=1, is_active=True
        )
        self.criterion = Criterion.objects.create(
            category=self.cat, name='Fill Criterion', number=1, is_active=True
        )

    def test_context_has_current_category_index(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        self.assertIn('current_category_index', response.context)
        self.assertEqual(response.context['current_category_index'], 1)

    def test_context_has_answered_count(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        self.assertIn('answered_count', response.context)
        self.assertEqual(response.context['answered_count'], 0)

    def test_context_has_total_criteria(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        self.assertIn('total_criteria', response.context)
        self.assertEqual(response.context['total_criteria'], 1)

    def test_categories_annotated_with_is_complete_false(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        cats = list(response.context['categories'])
        self.assertTrue(hasattr(cats[0], 'is_complete'))
        self.assertIs(cats[0].is_complete, False)

    def test_categories_annotated_with_is_complete_true_after_answer(self):
        Response.objects.create(questionnaire=self.q, criterion=self.criterion, score=3, notes='')
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        cats = list(response.context['categories'])
        self.assertTrue(cats[0].is_complete)


class ScoreValidationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='Score Val Org')
        self.user = User.objects.create_user(username='score_val', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='score_val', password='pass')
        self.cycle = AwardCycle.objects.create(year=2040, name='DSE 2040', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Score Cat', order=1, is_active=True
        )
        self.criterion = Criterion.objects.create(
            category=self.cat, name='Score Criterion', number=1, is_active=True
        )
        # LevelIndicator required so BulkResponseForm ChoiceField accepts level values
        LevelIndicator.objects.create(criterion=self.criterion, level=3, indicator='Level 3 text')

    def test_non_integer_score_does_not_crash(self):
        response = self.client.post(
            reverse('save_category', args=[self.q.pk]),
            {'category_id': self.cat.pk,
             f'criterion_{self.criterion.pk}': 'not-a-number',
             f'notes_{self.criterion.pk}': ''},
        )
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(Response.objects.filter(questionnaire=self.q).count(), 0)

    def test_out_of_range_score_does_not_save(self):
        response = self.client.post(
            reverse('save_category', args=[self.q.pk]),
            {'category_id': self.cat.pk,
             f'criterion_{self.criterion.pk}': '99',
             f'notes_{self.criterion.pk}': ''},
        )
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(Response.objects.filter(questionnaire=self.q).count(), 0)

    def test_valid_score_saves_correctly(self):
        self.client.post(
            reverse('save_category', args=[self.q.pk]),
            {'category_id': self.cat.pk,
             f'criterion_{self.criterion.pk}': '3',
             f'notes_{self.criterion.pk}': 'test note'},
        )
        self.assertEqual(Response.objects.filter(questionnaire=self.q, score=3).count(), 1)

    def test_post_with_valid_score_saves_and_redirects(self):
        response = self.client.post(
            reverse('save_category', args=[self.q.pk]),
            {'category_id': self.cat.pk,
             f'criterion_{self.criterion.pk}': '3',
             f'notes_{self.criterion.pk}': 'some note'},
        )
        # AJAX endpoint returns 200 JSON, not a redirect
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(Response.objects.filter(questionnaire=self.q, score=3).count(), 1)

    @override_settings(
        EVIDENCE_MAX_FILE_BYTES=10 * 1024 * 1024,
        EVIDENCE_MAX_FILES_PER_RESP=5,
        EVIDENCE_MAX_QUOTA_BYTES=100 * 1024 * 1024,
        MEDIA_ROOT='/tmp/eya_test_media/',
    )
    def test_upload_creates_evidence_doc_and_link(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(
            reverse('evidence_upload_ajax'),
            {'file': f,
             'questionnaire_id': self.q.pk,
             'criterion_id': self.criterion.pk},
        )
        self.assertEqual(EvidenceDocument.objects.filter(
            organization=self.org).count(), 1)
        self.assertTrue(EvidenceLink.objects.filter(
            response__questionnaire=self.q).exists())


class QuestionnaireSubmittedGuardTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='Guard Test Org')
        self.user = User.objects.create_user(username='guard_user', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='guard_user', password='pass')
        self.cycle = AwardCycle.objects.create(year=2041, name='DSE 2041', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]

    def test_submitted_view_redirects_when_not_submitted(self):
        self.assertFalse(self.q.is_submitted)
        response = self.client.get(reverse('questionnaire_submitted', args=[self.q.pk]))
        self.assertRedirects(
            response, reverse('questionnaire_fill', args=[self.q.pk]),
            fetch_redirect_response=False
        )

    def test_submitted_view_renders_when_submitted(self):
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        response = self.client.get(reverse('questionnaire_submitted', args=[self.q.pk]))
        self.assertEqual(response.status_code, 200)


from django.test import Client
from django.urls import reverse


class CycleAddOrgValidationTest(TestCase):
    def setUp(self):
        self.client = Client()
        admin_user = User.objects.create_user(username='admin_add', password='pass')
        UserProfile.objects.create(user=admin_user, role='admin')
        self.client.login(username='admin_add', password='pass')
        self.cycle = AwardCycle.objects.create(year=2042, name='DSE 2042', is_open=True)

    def test_missing_org_id_does_not_crash(self):
        response = self.client.post(reverse('cycle_add_org', args=[self.cycle.pk]), {})
        self.assertNotEqual(response.status_code, 500)
        self.assertRedirects(
            response, reverse('cycle_detail', args=[self.cycle.pk]),
            fetch_redirect_response=False
        )

    def test_non_integer_org_id_does_not_crash(self):
        response = self.client.post(
            reverse('cycle_add_org', args=[self.cycle.pk]), {'org_id': 'abc'}
        )
        self.assertNotEqual(response.status_code, 500)
        self.assertRedirects(
            response, reverse('cycle_detail', args=[self.cycle.pk]),
            fetch_redirect_response=False
        )


class CycleResultsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        admin_user = User.objects.create_user(username='admin_results', password='pass')
        UserProfile.objects.create(user=admin_user, role='admin')
        self.client.login(username='admin_results', password='pass')

        self.org = Organization.objects.create(name='Results Org')
        self.cycle = AwardCycle.objects.create(year=2043, name='DSE 2043', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()

        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Results Cat', order=1, is_active=True
        )
        self.criterion = Criterion.objects.create(
            category=self.cat, name='Results Criterion', number=1, is_active=True
        )
        Response.objects.create(questionnaire=self.q, criterion=self.criterion, score=4, notes='good')

        verifier_user = User.objects.create_user(username='ver_results', password='pass')
        UserProfile.objects.create(user=verifier_user, role='verifier')
        from accounts.models import VerifierAssignment
        VerifierAssignment.objects.create(verifier=verifier_user, organization=self.org)
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=verifier_user,
            criterion=self.criterion, score=3, notes='verifier note'
        )

    def test_results_view_renders_with_scores(self):
        response = self.client.get(reverse('cycle_results', args=[self.cycle.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.context)
        results = response.context['results']
        self.assertEqual(len(results), 1)
        cat_data = results[0]['categories']
        self.assertEqual(len(cat_data), 1)
        row = cat_data[0]['rows'][0]
        self.assertEqual(row['member_score'], 4)
        self.assertEqual(len(row['verifier_scores']), 1)
        self.assertEqual(row['verifier_scores'][0]['score'], 3)


class FileUploadValidationTest(TestCase):
    def setUp(self):
        self.client = Client()
        admin_user = User.objects.create_user(username='admin_upload', password='pass')
        UserProfile.objects.create(user=admin_user, role='admin')
        self.client.login(username='admin_upload', password='pass')
        self.cycle = AwardCycle.objects.create(year=2044, name='DSE 2044')

    def _make_fake_file(self, name, content=b'fake content', content_type='text/plain'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, content, content_type=content_type)

    def test_excel_upload_rejects_non_xlsx(self):
        fake_txt = self._make_fake_file('data.txt', b'not excel', 'text/plain')
        response = self.client.post(
            reverse('cycle_detail', args=[self.cycle.pk]),
            {'excel_file': fake_txt},
            format='multipart',
        )
        self.assertRedirects(
            response, reverse('cycle_detail', args=[self.cycle.pk]),
            fetch_redirect_response=False
        )
        self.assertEqual(AssessmentCategory.objects.filter(cycle=self.cycle).count(), 0)

    def test_reupload_blocked_when_cycle_is_open(self):
        self.cycle.is_open = True
        self.cycle.save()
        fake_xlsx = self._make_fake_file(
            'data.xlsx', b'fake',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response = self.client.post(
            reverse('cycle_detail', args=[self.cycle.pk]),
            {'excel_file': fake_xlsx},
            format='multipart',
        )
        self.assertRedirects(
            response, reverse('cycle_detail', args=[self.cycle.pk]),
            fetch_redirect_response=False
        )
        self.assertEqual(AssessmentCategory.objects.filter(cycle=self.cycle).count(), 0)


class AccessDeniedReturns403Test(TestCase):
    def setUp(self):
        self.client = Client()
        # org1 — the logged-in member belongs here
        self.org1 = Organization.objects.create(name='Org403A')
        self.member = User.objects.create_user(username='mem_403', password='pass')
        UserProfile.objects.create(user=self.member, role='member', organization=self.org1)
        # org2 — a different org whose questionnaire the member must not access
        self.org2 = Organization.objects.create(name='Org403B')
        self.cycle = AwardCycle.objects.create(year=2099, name='DSE 2099', is_open=True)
        # Opening the cycle auto-creates questionnaires for all active orgs
        self.q_org2 = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org2)[0]
        self.client.login(username='mem_403', password='pass')

    def test_member_fill_other_org_questionnaire_returns_403(self):
        response = self.client.get(
            reverse('questionnaire_fill', args=[self.q_org2.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_member_submit_other_org_questionnaire_returns_403(self):
        response = self.client.post(
            reverse('questionnaire_submit', args=[self.q_org2.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_unassigned_verifier_accessing_questionnaire_returns_403(self):
        from django.utils import timezone
        self.q_org2.is_submitted = True
        self.q_org2.submitted_at = timezone.now()
        self.q_org2.save()
        verifier = User.objects.create_user(username='ver_403', password='pass')
        UserProfile.objects.create(user=verifier, role='verifier')
        # verifier is NOT assigned to org2
        self.client.login(username='ver_403', password='pass')
        response = self.client.get(
            reverse('verify_questionnaire', args=[self.q_org2.pk])
        )
        self.assertEqual(response.status_code, 403)


class ErrorPageTemplateTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='ErrPageOrg')
        self.member = User.objects.create_user(username='mem_err', password='pass')
        UserProfile.objects.create(user=self.member, role='member', organization=self.org)
        self.org2 = Organization.objects.create(name='ErrPageOrg2')
        self.cycle = AwardCycle.objects.create(year=2098, name='DSE 2098', is_open=True)
        self.q_org2 = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org2)[0]

    @override_settings(DEBUG=False)
    def test_403_uses_custom_template(self):
        client = Client(raise_request_exception=False)
        client.login(username='mem_err', password='pass')
        response = client.get(reverse('questionnaire_fill', args=[self.q_org2.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')

    @override_settings(DEBUG=False)
    def test_404_uses_custom_template(self):
        client = Client(raise_request_exception=False)
        response = client.get('/this-url-absolutely-does-not-exist-eya/')
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, '404.html')




class EvidenceQuotaContextTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='QuotaCtxOrg')
        self.user = User.objects.create_user(username='quota_ctx', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='quota_ctx', password='pass')
        self.cycle = AwardCycle.objects.create(year=2047, name='DSE 2047', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Quota Cat', order=1, is_active=True
        )
        self.criterion = Criterion.objects.create(
            category=self.cat, name='Quota Criterion', number=1, is_active=True
        )

    def test_context_includes_quota_used_zero(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        self.assertIn('quota_used', response.context)
        self.assertEqual(response.context['quota_used'], 0)

    def test_context_includes_quota_pct_zero(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        self.assertIn('quota_pct', response.context)
        self.assertEqual(response.context['quota_pct'], 0)

    def test_quota_used_reflects_existing_uploads(self):
        EvidenceDocument.objects.create(
            organization=self.org, title='x.pdf',
            original_filename='x.pdf', file_size=1024 * 1024,
            uploaded_by=self.user)
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        self.assertEqual(response.context['quota_used'], 1024 * 1024)
        self.assertEqual(response.context['quota_pct'], 1)

    def test_criteria_data_includes_links(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        item = response.context['criteria_data'][0]
        self.assertIn('links', item)
        self.assertEqual(item['links'], [])


class PreambleDisplayTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='PreambleOrg')
        self.user = User.objects.create_user(username='preamble_mem', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='preamble_mem', password='pass')
        self.cycle = AwardCycle.objects.create(year=2051, name='DSE 2051', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Preamble Cat', order=1, is_active=True,
            description='This is the preamble text for testing.'
        )
        Criterion.objects.create(
            category=self.cat, name='Preamble Criterion', number=1, is_active=True
        )
        self.admin_user = User.objects.create_user(username='preamble_admin', password='pass')
        UserProfile.objects.create(user=self.admin_user, role='admin')

    def test_preamble_shown_in_questionnaire_fill(self):
        response = self.client.get(reverse('questionnaire_fill', args=[self.q.pk]))
        self.assertContains(response, 'This is the preamble text for testing.')

    def test_preamble_shown_in_cycle_detail(self):
        self.client.login(username='preamble_admin', password='pass')
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertContains(response, 'This is the preamble text for testing.')

    def test_upload_form_hidden_when_cycle_open(self):
        self.client.login(username='preamble_admin', password='pass')
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertNotContains(response, 'name="excel_file"')
        self.assertContains(response, 'locked')

    def test_upload_form_shown_when_cycle_closed(self):
        self.cycle.is_open = False
        self.cycle.save()
        self.client.login(username='preamble_admin', password='pass')
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertContains(response, 'name="excel_file"')


class FillAccordionTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='AccordionOrg')
        self.user = User.objects.create_user(username='acc_mem', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='acc_mem', password='pass')
        self.cycle = AwardCycle.objects.create(year=2060, name='DSE 2060', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Acc Cat', order=1, is_active=True
        )
        self.criterion = Criterion.objects.create(
            category=self.cat, name='Acc Criterion', number=1, is_active=True
        )

    def test_indicator_body_has_collapsed_class(self):
        response = self.client.get(
            reverse('questionnaire_fill', args=[self.q.pk]) + f'?category={self.cat.id}'
        )
        self.assertContains(response, 'indicator-body collapsed')

    def test_indicator_has_data_answered_false_when_unanswered(self):
        response = self.client.get(
            reverse('questionnaire_fill', args=[self.q.pk]) + f'?category={self.cat.id}'
        )
        self.assertContains(response, 'data-answered="false"')

    def test_indicator_has_data_answered_true_when_answered(self):
        Response.objects.create(questionnaire=self.q, criterion=self.criterion, score=3, notes='')
        response = self.client.get(
            reverse('questionnaire_fill', args=[self.q.pk]) + f'?category={self.cat.id}'
        )
        self.assertContains(response, 'data-answered="true"')

    def test_indicator_chevron_present(self):
        response = self.client.get(
            reverse('questionnaire_fill', args=[self.q.pk]) + f'?category={self.cat.id}'
        )
        self.assertContains(response, 'indicator-chevron')


class CategoryAccordionTest(TestCase):
    def setUp(self):
        self.client = Client()
        admin_user = User.objects.create_user(username='cat_acc_admin', password='pass')
        UserProfile.objects.create(user=admin_user, role='admin')
        self.client.login(username='cat_acc_admin', password='pass')
        self.cycle = AwardCycle.objects.create(year=2061, name='DSE 2061')
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Accordion Category', order=1, is_active=True,
            description='This is the preamble.'
        )
        Criterion.objects.create(
            category=self.cat, name='First Criterion', number=1, is_active=True
        )

    def test_category_row_has_cat_row_class(self):
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertContains(response, 'cat-row')

    def test_category_detail_row_present(self):
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertContains(response, 'cat-detail')

    def test_criteria_names_in_detail_row(self):
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertContains(response, 'First Criterion')

    def test_description_in_detail_row(self):
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertContains(response, 'This is the preamble.')

    def test_category_without_description_shows_no_preamble_block(self):
        self.cat.description = ''
        self.cat.save()
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertNotContains(response, 'cat-preamble')

    def test_inactive_criterion_not_shown_in_detail_row(self):
        Criterion.objects.create(
            category=self.cat, name='Hidden Criterion', number=2, is_active=False
        )
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertNotContains(response, 'Hidden Criterion')

    def test_cat_chevron_present(self):
        response = self.client.get(reverse('cycle_detail', args=[self.cycle.pk]))
        self.assertContains(response, 'cat-chevron')


class VerifierDashboardNoOpenCycleTests(TestCase):
    def setUp(self):
        from accounts.models import Organization, UserProfile, VerifierAssignment
        self.org = Organization.objects.create(name='Verifier Dash Org')
        self.verifier = User.objects.create_user(
            username='vdash@test.com', password='VPass123!'
        )
        UserProfile.objects.create(user=self.verifier, role='verifier')
        VerifierAssignment.objects.create(verifier=self.verifier, organization=self.org)

    def test_assigned_orgs_in_context_when_no_cycle(self):
        self.client.login(username='vdash@test.com', password='VPass123!')
        response = self.client.get('/verifier/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('assigned_orgs', response.context)
        orgs = [a.organization for a in response.context['assigned_orgs']]
        self.assertIn(self.org, orgs)

    def test_assigned_orgs_count_correct_when_no_cycle(self):
        self.client.login(username='vdash@test.com', password='VPass123!')
        response = self.client.get('/verifier/dashboard/')
        self.assertEqual(len(response.context['assigned_orgs']), 1)

    def test_no_assignments_shows_empty_state(self):
        from accounts.models import VerifierAssignment
        VerifierAssignment.objects.filter(verifier=self.verifier).delete()
        self.client.login(username='vdash@test.com', password='VPass123!')
        response = self.client.get('/verifier/dashboard/')
        self.assertEqual(len(response.context['assigned_orgs']), 0)


class VerifierDashboardStatsTests(TestCase):
    def setUp(self):
        from accounts.models import Organization, UserProfile, VerifierAssignment
        self.org1 = Organization.objects.create(name='Org One')
        self.org2 = Organization.objects.create(name='Org Two')
        self.verifier = User.objects.create_user(username='ver1', password='Pass123!')
        UserProfile.objects.create(user=self.verifier, role='verifier')
        VerifierAssignment.objects.create(verifier=self.verifier, organization=self.org1)
        VerifierAssignment.objects.create(verifier=self.verifier, organization=self.org2)
        self.cycle = AwardCycle.objects.create(year=2026, name='DSE 2026', is_open=True)
        # cycle.save() auto-creates questionnaires for active orgs; mark org1 submitted
        self.q1, _ = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org1)
        self.q1.is_submitted = True
        self.q1.save()
        self.q2, _ = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org2)
        self.client.login(username='ver1', password='Pass123!')

    def test_submitted_and_pending_counts_in_context(self):
        response = self.client.get(reverse('verifier_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['submitted_count'], 1)
        self.assertEqual(response.context['pending_count'], 1)

    def test_stats_are_zero_when_no_cycle_open(self):
        AwardCycle.objects.all().update(is_open=False)
        response = self.client.get(reverse('verifier_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['submitted_count'], 0)
        self.assertEqual(response.context['pending_count'], 0)

    def test_no_stat_dash_placeholders_in_html(self):
        response = self.client.get(reverse('verifier_dashboard'))
        self.assertNotContains(response, 'id="stat-submitted"')
        self.assertNotContains(response, 'id="stat-pending"')


class ComputeOrgAnalyticsTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.org = Organization.objects.create(name='Analytics Org')
        self.cycle = AwardCycle.objects.create(year=2060, name='DSE 2060', is_open=True)
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Cat A', order=1, is_active=True
        )
        self.c1 = Criterion.objects.create(
            category=self.cat, number=1, name='C1', is_active=True
        )
        self.c2 = Criterion.objects.create(
            category=self.cat, number=2, name='C2', is_active=True
        )
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        self.verifier = User.objects.create_user(username='ver_analytics', password='pass')
        Response.objects.create(questionnaire=self.q, criterion=self.c1, score=4, notes='note1')
        Response.objects.create(questionnaire=self.q, criterion=self.c2, score=2, notes='note2')
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.verifier, criterion=self.c1, score=3
        )
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.verifier, criterion=self.c2, score=5
        )

    def test_overall_member_score(self):
        from .analytics import compute_org_analytics
        result = compute_org_analytics(self.q)
        self.assertEqual(result['overall_member_score'], 3.0)  # avg(4, 2)

    def test_overall_verifier_score(self):
        from .analytics import compute_org_analytics
        result = compute_org_analytics(self.q)
        self.assertEqual(result['overall_verifier_score'], 4.0)  # avg(3, 5)

    def test_overall_gap(self):
        from .analytics import compute_org_analytics
        result = compute_org_analytics(self.q)
        self.assertEqual(result['overall_gap'], 1.0)

    def test_no_verifier_scores_returns_none(self):
        from .analytics import compute_org_analytics
        VerifierResponse.objects.filter(questionnaire=self.q).delete()
        result = compute_org_analytics(self.q)
        self.assertIsNone(result['overall_verifier_score'])
        self.assertIsNone(result['overall_gap'])

    def test_category_entry_has_correct_avgs(self):
        from .analytics import compute_org_analytics
        result = compute_org_analytics(self.q)
        self.assertEqual(len(result['categories']), 1)
        cat_entry = result['categories'][0]
        self.assertEqual(cat_entry['member_avg'], 3.0)
        self.assertEqual(cat_entry['verifier_avg'], 4.0)
        self.assertEqual(cat_entry['gap'], 1.0)

    def test_criteria_included_in_category(self):
        from .analytics import compute_org_analytics
        result = compute_org_analytics(self.q)
        crit_entries = result['categories'][0]['criteria']
        self.assertEqual(len(crit_entries), 2)
        self.assertEqual(crit_entries[0]['member_score'], 4)
        self.assertEqual(crit_entries[0]['verifier_score'], 3.0)
        self.assertEqual(crit_entries[0]['member_notes'], 'note1')

    def test_strengths_weaknesses_ordering(self):
        from .analytics import compute_org_analytics
        cat_b = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Cat B', order=2, is_active=True
        )
        cat_c = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Cat C', order=3, is_active=True
        )
        cb1 = Criterion.objects.create(
            category=cat_b, number=1, name='CB1', is_active=True
        )
        cc1 = Criterion.objects.create(
            category=cat_c, number=1, name='CC1', is_active=True
        )
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.verifier, criterion=cb1, score=1
        )
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.verifier, criterion=cc1, score=5
        )
        result = compute_org_analytics(self.q)
        strength_names = [e['category'].name for e in result['strengths']]
        weakness_names = [e['category'].name for e in result['weaknesses']]
        self.assertEqual(strength_names[0], 'Cat C')
        self.assertEqual(weakness_names[0], 'Cat B')


class ComputeCycleAnalyticsTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.utils import timezone
        self.org_a = Organization.objects.create(name='Org Alpha')
        self.org_b = Organization.objects.create(name='Org Beta')
        self.cycle = AwardCycle.objects.create(year=2061, name='DSE 2061', is_open=True)
        self.cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Cat X', order=1, is_active=True
        )
        self.c1 = Criterion.objects.create(
            category=self.cat, number=1, name='CX1', is_active=True
        )
        self.q_a = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org_a)[0]
        self.q_b = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org_b)[0]
        now = timezone.now()
        self.q_a.is_submitted = True; self.q_a.submitted_at = now; self.q_a.save()
        self.q_b.is_submitted = True; self.q_b.submitted_at = now; self.q_b.save()
        self.verifier = User.objects.create_user(username='ver_cycle', password='pass')
        VerifierResponse.objects.create(
            questionnaire=self.q_a, verifier=self.verifier, criterion=self.c1, score=4
        )
        VerifierResponse.objects.create(
            questionnaire=self.q_b, verifier=self.verifier, criterion=self.c1, score=2
        )

    def test_ranked_orgs_sorted_descending(self):
        from .analytics import compute_cycle_analytics
        result = compute_cycle_analytics(self.cycle)
        orgs = [e['org'] for e in result['ranked_orgs']]
        self.assertEqual(orgs[0], self.org_a)
        self.assertEqual(orgs[1], self.org_b)

    def test_ranks_assigned_correctly(self):
        from .analytics import compute_cycle_analytics
        result = compute_cycle_analytics(self.cycle)
        self.assertEqual(result['ranked_orgs'][0]['rank'], 1)
        self.assertEqual(result['ranked_orgs'][1]['rank'], 2)

    def test_cycle_high_and_low(self):
        from .analytics import compute_cycle_analytics
        result = compute_cycle_analytics(self.cycle)
        self.assertEqual(result['cycle_high'], 4.0)
        self.assertEqual(result['cycle_low'], 2.0)

    def test_cycle_avg_verifier(self):
        from .analytics import compute_cycle_analytics
        result = compute_cycle_analytics(self.cycle)
        self.assertEqual(result['cycle_avg_verifier'], 3.0)

    def test_category_leader_best_and_worst(self):
        from .analytics import compute_cycle_analytics
        result = compute_cycle_analytics(self.cycle)
        leader = result['category_leaders'][0]
        self.assertEqual(leader['category'], self.cat)
        self.assertEqual(leader['best_org'], self.org_a)
        self.assertEqual(leader['worst_org'], self.org_b)

    def test_empty_cycle_returns_empty_results(self):
        from .analytics import compute_cycle_analytics
        empty_cycle = AwardCycle.objects.create(year=2099, name='DSE 2099')
        result = compute_cycle_analytics(empty_cycle)
        self.assertEqual(result['ranked_orgs'], [])
        self.assertIsNone(result['cycle_avg_verifier'])
        self.assertEqual(result['category_leaders'], [])

    def test_unsubmitted_questionnaires_excluded(self):
        from .analytics import compute_cycle_analytics
        org_c = Organization.objects.create(name='Org Gamma')
        # Questionnaire auto-created but not submitted
        result = compute_cycle_analytics(self.cycle)
        org_names = [e['org'].name for e in result['ranked_orgs']]
        self.assertNotIn('Org Gamma', org_names)


class NewUrlsTest(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.client = Client()
        admin = User.objects.create_user(username='admin_urls', password='pass')
        UserProfile.objects.create(user=admin, role='admin')
        self.client.login(username='admin_urls', password='pass')
        self.org = Organization.objects.create(name='URL Test Org')
        self.cycle = AwardCycle.objects.create(year=2063, name='DSE 2063', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()

    def test_org_report_url_resolves(self):
        response = self.client.get(
            reverse('org_report', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_export_cycle_excel_url_resolves(self):
        response = self.client.get(
            reverse('export_cycle_excel', args=[self.cycle.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_export_org_excel_url_resolves(self):
        response = self.client.get(
            reverse('export_org_excel', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_export_org_pdf_url_resolves(self):
        response = self.client.get(
            reverse('export_org_pdf', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 200)


class CycleResultsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        admin = User.objects.create_user(username='admin_cres', password='pass')
        UserProfile.objects.create(user=admin, role='admin')
        self.client.login(username='admin_cres', password='pass')
        self.cycle = AwardCycle.objects.create(year=2064, name='DSE 2064')

    def test_admin_can_access(self):
        response = self.client.get(reverse('cycle_results', args=[self.cycle.pk]))
        self.assertEqual(response.status_code, 200)

    def test_context_has_analytics_key(self):
        response = self.client.get(reverse('cycle_results', args=[self.cycle.pk]))
        self.assertIn('analytics', response.context)

    def test_analytics_has_ranked_orgs(self):
        response = self.client.get(reverse('cycle_results', args=[self.cycle.pk]))
        self.assertIn('ranked_orgs', response.context['analytics'])

    def test_non_admin_redirected(self):
        member = User.objects.create_user(username='mem_cres', password='pass')
        org = Organization.objects.create(name='CRes Org')
        UserProfile.objects.create(user=member, role='member', organization=org)
        self.client.login(username='mem_cres', password='pass')
        response = self.client.get(reverse('cycle_results', args=[self.cycle.pk]))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)


class OrgReportViewTest(TestCase):
    def setUp(self):
        from django.utils import timezone
        from accounts.models import VerifierAssignment
        self.client = Client()
        # Admin
        admin = User.objects.create_user(username='admin_orpt', password='pass')
        UserProfile.objects.create(user=admin, role='admin')
        self.admin = admin
        # Org and submitted questionnaire
        self.org = Organization.objects.create(name='OrgRpt Org')
        self.cycle = AwardCycle.objects.create(year=2065, name='DSE 2065', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        # Assigned verifier
        self.ver = User.objects.create_user(username='ver_orpt', password='pass')
        UserProfile.objects.create(user=self.ver, role='verifier')
        VerifierAssignment.objects.create(verifier=self.ver, organization=self.org)
        # Unassigned verifier
        self.ver2 = User.objects.create_user(username='ver_orpt2', password='pass')
        UserProfile.objects.create(user=self.ver2, role='verifier')

    def _url(self):
        return reverse('org_report', args=[self.cycle.pk, self.q.pk])

    def test_admin_can_access(self):
        self.client.login(username='admin_orpt', password='pass')
        self.assertEqual(self.client.get(self._url()).status_code, 200)

    def test_assigned_verifier_can_access(self):
        self.client.login(username='ver_orpt', password='pass')
        self.assertEqual(self.client.get(self._url()).status_code, 200)

    def test_unassigned_verifier_gets_403(self):
        self.client.login(username='ver_orpt2', password='pass')
        self.assertEqual(self.client.get(self._url()).status_code, 403)

    def test_context_has_analytics(self):
        self.client.login(username='admin_orpt', password='pass')
        ctx = self.client.get(self._url()).context
        self.assertIn('analytics', ctx)
        self.assertIn('overall_verifier_score', ctx['analytics'])

    def test_context_is_admin_flag(self):
        self.client.login(username='admin_orpt', password='pass')
        ctx = self.client.get(self._url()).context
        self.assertTrue(ctx['is_admin'])

    def test_context_is_admin_false_for_verifier(self):
        self.client.login(username='ver_orpt', password='pass')
        ctx = self.client.get(self._url()).context
        self.assertFalse(ctx['is_admin'])

    def test_404_for_unsubmitted_questionnaire(self):
        self.client.login(username='admin_orpt', password='pass')
        self.q.is_submitted = False
        self.q.save()
        self.assertEqual(self.client.get(self._url()).status_code, 404)


class ExcelExportTest(TestCase):
    def setUp(self):
        from django.utils import timezone
        from accounts.models import VerifierAssignment
        self.client = Client()
        admin = User.objects.create_user(username='admin_xls', password='pass')
        UserProfile.objects.create(user=admin, role='admin')
        self.admin = admin
        self.org = Organization.objects.create(name='XLS Org')
        self.cycle = AwardCycle.objects.create(year=2066, name='DSE 2066', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        self.ver = User.objects.create_user(username='ver_xls', password='pass')
        UserProfile.objects.create(user=self.ver, role='verifier')
        VerifierAssignment.objects.create(verifier=self.ver, organization=self.org)
        self.ver2 = User.objects.create_user(username='ver_xls2', password='pass')
        UserProfile.objects.create(user=self.ver2, role='verifier')

    def test_cycle_excel_content_type(self):
        self.client.login(username='admin_xls', password='pass')
        response = self.client.get(reverse('export_cycle_excel', args=[self.cycle.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'spreadsheetml',
            response.get('Content-Type', '')
        )

    def test_cycle_excel_has_attachment_header(self):
        self.client.login(username='admin_xls', password='pass')
        response = self.client.get(reverse('export_cycle_excel', args=[self.cycle.pk]))
        self.assertIn('attachment', response.get('Content-Disposition', ''))

    def test_org_excel_admin_access(self):
        self.client.login(username='admin_xls', password='pass')
        response = self.client.get(
            reverse('export_org_excel', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response.get('Content-Type', ''))

    def test_org_excel_assigned_verifier_access(self):
        self.client.login(username='ver_xls', password='pass')
        response = self.client.get(
            reverse('export_org_excel', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_org_excel_unassigned_verifier_denied(self):
        self.client.login(username='ver_xls2', password='pass')
        response = self.client.get(
            reverse('export_org_excel', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 403)


class PdfExportTest(TestCase):
    def setUp(self):
        from django.utils import timezone
        from accounts.models import VerifierAssignment
        self.client = Client()
        admin = User.objects.create_user(username='admin_pdf', password='pass')
        UserProfile.objects.create(user=admin, role='admin')
        self.org = Organization.objects.create(name='PDF Org')
        self.cycle = AwardCycle.objects.create(year=2067, name='DSE 2067', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        self.ver = User.objects.create_user(username='ver_pdf', password='pass')
        UserProfile.objects.create(user=self.ver, role='verifier')
        VerifierAssignment.objects.create(verifier=self.ver, organization=self.org)
        self.ver2 = User.objects.create_user(username='ver_pdf2', password='pass')
        UserProfile.objects.create(user=self.ver2, role='verifier')
        self.client.login(username='admin_pdf', password='pass')

    def test_pdf_content_type(self):
        response = self.client.get(
            reverse('export_org_pdf', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get('Content-Type'), 'application/pdf')

    def test_pdf_attachment_header(self):
        response = self.client.get(
            reverse('export_org_pdf', args=[self.cycle.pk, self.q.pk])
        )
        self.assertIn('attachment', response.get('Content-Disposition', ''))

    def test_pdf_assigned_verifier_access(self):
        self.client.login(username='ver_pdf', password='pass')
        response = self.client.get(
            reverse('export_org_pdf', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_pdf_unassigned_verifier_denied(self):
        self.client.login(username='ver_pdf2', password='pass')
        response = self.client.get(
            reverse('export_org_pdf', args=[self.cycle.pk, self.q.pk])
        )
        self.assertEqual(response.status_code, 403)


class VerifyCrossCycleCategoryTest(TestCase):
    """A verifier must not load/score a category that belongs to another cycle."""
    def setUp(self):
        from django.utils import timezone
        from accounts.models import VerifierAssignment
        self.client = Client()
        self.org = Organization.objects.create(name='XCycle Org')
        self.cycle = AwardCycle.objects.create(year=2071, name='DSE 2071', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        self.ver = User.objects.create_user(username='ver_xc', password='pass')
        UserProfile.objects.create(user=self.ver, role='verifier')
        VerifierAssignment.objects.create(verifier=self.ver, organization=self.org)
        # A category in a *different* cycle
        self.other_cycle = AwardCycle.objects.create(year=2072, name='DSE 2072', is_open=False)
        self.foreign_cat = AssessmentCategory.objects.create(
            cycle=self.other_cycle, name='Foreign Cat', order=0
        )
        self.client.login(username='ver_xc', password='pass')

    def test_foreign_category_on_get_returns_404(self):
        response = self.client.get(
            reverse('verify_questionnaire', args=[self.q.pk]),
            {'category': self.foreign_cat.id},
        )
        self.assertEqual(response.status_code, 404)

    def test_foreign_category_on_post_returns_404(self):
        # Reopen this questionnaire's cycle so POST is permitted, then submit a foreign category
        self.cycle.is_open = True
        self.cycle.save()
        response = self.client.post(
            reverse('verify_questionnaire', args=[self.q.pk]),
            {'category_id': self.foreign_cat.id},
        )
        self.assertEqual(response.status_code, 404)


class LibraryModelTests(TestCase):
    def setUp(self):
        from accounts.models import Organization
        self.org = Organization.objects.create(name="Org A", is_active=True)

    def test_evidence_document_str(self):
        doc = EvidenceDocument.objects.create(
            organization=self.org, title="ISO Cert",
            original_filename="iso.pdf", file_size=100)
        self.assertIn("ISO Cert", str(doc))

    def test_evidence_document_ordering(self):
        doc1 = EvidenceDocument.objects.create(
            organization=self.org, title="First",
            original_filename="a.pdf", file_size=10)
        doc2 = EvidenceDocument.objects.create(
            organization=self.org, title="Second",
            original_filename="b.pdf", file_size=20)
        docs = list(EvidenceDocument.objects.filter(organization=self.org))
        # Most recent first
        self.assertEqual(docs[0], doc2)
        self.assertEqual(docs[1], doc1)

    def test_evidence_link_unique_per_response_document(self):
        from django.db import IntegrityError
        cycle = AwardCycle.objects.create(year=99991, name="T", is_open=False)
        cat = AssessmentCategory.objects.create(cycle=cycle, name="Cat", order=1)
        crit = Criterion.objects.create(category=cat, number=1, name="Crit")
        q = Questionnaire.objects.create(cycle=cycle, organization=self.org)
        resp = Response.objects.create(questionnaire=q, criterion=crit)
        doc = EvidenceDocument.objects.create(
            organization=self.org, title="X",
            original_filename="x.pdf", file_size=1)
        EvidenceLink.objects.create(response=resp, document=doc)
        with self.assertRaises(IntegrityError):
            EvidenceLink.objects.create(response=resp, document=doc)


class AccessPredicateTests(TestCase):
    """Tests for can_access_document (new flat model)."""
    def setUp(self):
        from accounts.models import (
            Organization, UserProfile, VerifierAssignment)
        self.org = Organization.objects.create(name="Org C", is_active=True)
        self.other = Organization.objects.create(name="Org D", is_active=True)
        self.member = User.objects.create_user("memberc", password="x")
        UserProfile.objects.create(user=self.member, role='member', organization=self.org)
        self.admin = User.objects.create_user("adminc", password="x")
        UserProfile.objects.create(user=self.admin, role='admin')
        self.verifier = User.objects.create_user("verc", password="x")
        UserProfile.objects.create(user=self.verifier, role='verifier')

        self.cycle = AwardCycle.objects.create(year=90002, name="C2", is_open=False)
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name="K", order=1)
        self.crit = Criterion.objects.create(category=self.cat, number=1, name="Cr")
        self.q = Questionnaire.objects.create(cycle=self.cycle, organization=self.org)
        self.resp = Response.objects.create(questionnaire=self.q, criterion=self.crit, score=2)

        self.doc = EvidenceDocument.objects.create(
            organization=self.org, title="d",
            original_filename="d.pdf", file_size=1)
        EvidenceLink.objects.create(response=self.resp, document=self.doc)
        VerifierAssignment.objects.create(verifier=self.verifier, organization=self.org)

    def test_member_of_owning_org_allowed(self):
        from assessment.access import can_access_document
        self.assertTrue(can_access_document(self.member, self.doc))

    def test_admin_allowed_for_any(self):
        from assessment.access import can_access_document
        self.assertTrue(can_access_document(self.admin, self.doc))

    def test_verifier_allowed_when_linked(self):
        from assessment.access import can_access_document
        self.assertTrue(can_access_document(self.verifier, self.doc))

    def test_verifier_of_other_org_denied(self):
        from accounts.models import UserProfile
        from assessment.access import can_access_document
        stranger = User.objects.create_user("strange", password="x")
        UserProfile.objects.create(user=stranger, role='verifier')
        # Create unlinked doc for other org
        other_doc = EvidenceDocument.objects.create(
            organization=self.other, title="other",
            original_filename="o.pdf", file_size=1)
        self.assertFalse(can_access_document(stranger, other_doc))

    def test_member_with_no_org_denied(self):
        from accounts.models import UserProfile
        from assessment.access import can_access_document
        orphan = User.objects.create_user("orphan", password="x")
        UserProfile.objects.create(user=orphan, role='member', organization=None)
        self.assertFalse(can_access_document(orphan, self.doc))


class DocumentViewTests(TestCase):
    """Tests for document_file view (new flat EvidenceDocument model)."""
    def setUp(self):
        from accounts.models import Organization, UserProfile
        self.org = Organization.objects.create(name="Org E", is_active=True)
        self.member = User.objects.create_user("membere", password="x")
        UserProfile.objects.create(user=self.member, role='member', organization=self.org)
        self.verifier = User.objects.create_user("vere", password="x")
        UserProfile.objects.create(user=self.verifier, role='verifier')
        self.doc = EvidenceDocument.objects.create(
            organization=self.org, title="d",
            original_filename="d.pdf", file_size=1)

    def test_member_gets_redirect_or_200(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse('document_file', args=[self.doc.pk]))
        self.assertIn(r.status_code, [200, 302])

    def test_unauthorized_verifier_gets_403(self):
        self.client.force_login(self.verifier)
        r = self.client.get(reverse('document_file', args=[self.doc.pk]))
        self.assertEqual(r.status_code, 403)

    def test_unauthenticated_redirects_to_login(self):
        r = self.client.get(reverse('document_file', args=[self.doc.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])


class LibraryCrudTests(TestCase):
    """Tests for library list view with new EvidenceDocument model."""
    def setUp(self):
        from accounts.models import Organization, UserProfile
        self.org = Organization.objects.create(name="Org F", is_active=True)
        self.member = User.objects.create_user("memberf", password="x")
        UserProfile.objects.create(user=self.member, role='member', organization=self.org)

    def test_member_cannot_see_other_org_library(self):
        other = Organization.objects.create(name="Other", is_active=True)
        EvidenceDocument.objects.create(
            organization=other, title="secret",
            original_filename="secret_report.pdf", file_size=1)
        EvidenceDocument.objects.create(
            organization=self.org, title="mine",
            original_filename="mine_report.pdf", file_size=1)
        self.client.force_login(self.member)
        r = self.client.get('/library/')
        self.assertContains(r, "mine_report.pdf")
        self.assertNotContains(r, "secret_report.pdf")

    def test_library_list_returns_200(self):
        self.client.force_login(self.member)
        r = self.client.get('/library/')
        self.assertEqual(r.status_code, 200)

    def test_library_list_shows_documents(self):
        EvidenceDocument.objects.create(
            organization=self.org, title="My Evidence",
            original_filename="evidence_report.pdf", file_size=1024)
        self.client.force_login(self.member)
        r = self.client.get('/library/')
        self.assertContains(r, "evidence_report.pdf")


class EvidenceLinkTests(TestCase):
    def setUp(self):
        from accounts.models import Organization, UserProfile
        self.org = Organization.objects.create(name="Org G", is_active=True)
        self.member = User.objects.create_user("memberg", password="x")
        UserProfile.objects.create(user=self.member, role='member', organization=self.org)
        # org must exist before opening the cycle
        self.cycle = AwardCycle.objects.create(year=90004, name="C4", is_open=True)
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name="K", order=1)
        self.crit = Criterion.objects.create(category=self.cat, number=1, name="Cr")
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.resp = Response.objects.create(questionnaire=self.q, criterion=self.crit, score=2)
        self.doc = EvidenceDocument.objects.create(
            organization=self.org, title="d",
            original_filename="d.pdf", file_size=1)

    def test_link_creates_evidence_link(self):
        self.client.force_login(self.member)
        r = self.client.post('/evidence/link/', {
            'response_id': self.resp.id, 'doc_id': self.doc.id})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(EvidenceLink.objects.filter(
            response=self.resp, document=self.doc).exists())

    def test_unlink_removes_link_and_orphan_document(self):
        link = EvidenceLink.objects.create(response=self.resp, document=self.doc)
        self.client.force_login(self.member)
        r = self.client.post(f'/evidence/unlink/{link.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(EvidenceLink.objects.filter(id=link.id).exists())
        # Orphan document (no remaining links) is deleted automatically
        self.assertFalse(EvidenceDocument.objects.filter(id=self.doc.id).exists())

    def test_link_blocked_after_submit(self):
        self.q.is_submitted = True
        self.q.save()
        self.client.force_login(self.member)
        r = self.client.post('/evidence/link/', {
            'response_id': self.resp.id, 'doc_id': self.doc.id})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(EvidenceLink.objects.filter(response=self.resp).exists())

    def test_link_cap_per_criterion(self):
        from django.conf import settings
        self.client.force_login(self.member)
        for i in range(settings.EVIDENCE_MAX_FILES_PER_RESP):
            extra_doc = EvidenceDocument.objects.create(
                organization=self.org, title=f"doc{i}",
                original_filename=f"{i}.pdf", file_size=1)
            EvidenceLink.objects.create(response=self.resp, document=extra_doc)
        r = self.client.post('/evidence/link/', {
            'response_id': self.resp.id, 'doc_id': self.doc.id})
        self.assertEqual(r.status_code, 409)

    def test_link_cross_org_blocked(self):
        from accounts.models import Organization, UserProfile
        other_org = Organization.objects.create(name="Org H", is_active=True)
        other_member = User.objects.create_user("member_h", password="x")
        UserProfile.objects.create(user=other_member, role='member', organization=other_org)
        self.client.force_login(other_member)
        r = self.client.post('/evidence/link/', {
            'response_id': self.resp.id, 'doc_id': self.doc.id})
        self.assertEqual(r.status_code, 403)

    def test_link_by_criterion_creates_response_before_scoring(self):
        """Picker must work on a fresh cycle: a criterion with no Response yet
        can be linked, and the Response is auto-created (score stays null)."""
        crit2 = Criterion.objects.create(category=self.cat, number=2, name="Cr2")
        self.assertFalse(Response.objects.filter(
            questionnaire=self.q, criterion=crit2).exists())
        self.client.force_login(self.member)
        r = self.client.post('/evidence/link/', {
            'questionnaire_id': self.q.id, 'criterion_id': crit2.id,
            'doc_id': self.doc.id})
        self.assertEqual(r.status_code, 200)
        resp = Response.objects.get(questionnaire=self.q, criterion=crit2)
        self.assertIsNone(resp.score)
        self.assertTrue(EvidenceLink.objects.filter(
            response=resp, document=self.doc).exists())

    def test_link_by_criterion_rejects_other_cycle_criterion(self):
        """A criterion from a different cycle cannot be linked into this one."""
        other_cycle = AwardCycle.objects.create(year=90005, name="C5", is_open=False)
        other_cat = AssessmentCategory.objects.create(cycle=other_cycle, name="K2", order=1)
        foreign_crit = Criterion.objects.create(category=other_cat, number=1, name="Foreign")
        self.client.force_login(self.member)
        r = self.client.post('/evidence/link/', {
            'questionnaire_id': self.q.id, 'criterion_id': foreign_crit.id,
            'doc_id': self.doc.id})
        self.assertEqual(r.status_code, 404)


class CanAccessDocumentTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='AccessOrg')
        self.other_org = Organization.objects.create(name='OtherOrg')

        self.admin_user = User.objects.create_user(username='access_admin', password='pass')
        UserProfile.objects.create(user=self.admin_user, role='admin')

        self.member_user = User.objects.create_user(username='access_member', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)

        self.other_member = User.objects.create_user(username='access_other', password='pass')
        UserProfile.objects.create(user=self.other_member, role='member', organization=self.other_org)

        self.verifier_user = User.objects.create_user(username='access_verifier', password='pass')
        UserProfile.objects.create(user=self.verifier_user, role='verifier')
        from accounts.models import VerifierAssignment
        VerifierAssignment.objects.create(verifier=self.verifier_user, organization=self.org)

        self.doc = EvidenceDocument.objects.create(
            organization=self.org, title='Doc', original_filename='doc.pdf', file_size=100
        )

    def test_admin_can_access_any_document(self):
        from assessment.access import can_access_document
        self.assertTrue(can_access_document(self.admin_user, self.doc))

    def test_member_can_access_own_org_document(self):
        from assessment.access import can_access_document
        self.assertTrue(can_access_document(self.member_user, self.doc))

    def test_member_cannot_access_other_org_document(self):
        from assessment.access import can_access_document
        self.assertFalse(can_access_document(self.other_member, self.doc))

    def test_verifier_without_evidence_link_cannot_access(self):
        from assessment.access import can_access_document
        self.assertFalse(can_access_document(self.verifier_user, self.doc))

    def test_verifier_with_evidence_link_can_access(self):
        from assessment.access import can_access_document
        cycle = AwardCycle.objects.create(year=2088, name='DSE 2088', is_open=True)
        q = Questionnaire.objects.get_or_create(cycle=cycle, organization=self.org)[0]
        cat = AssessmentCategory.objects.create(cycle=cycle, name='Cat', order=1)
        crit = Criterion.objects.create(category=cat, number=1, name='C1', order=1)
        resp = Response.objects.create(questionnaire=q, criterion=crit, score=3)
        EvidenceLink.objects.create(response=resp, document=self.doc)
        self.assertTrue(can_access_document(self.verifier_user, self.doc))

    def test_unauthenticated_user_cannot_access(self):
        from assessment.access import can_access_document
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(can_access_document(AnonymousUser(), self.doc))


class DocumentFileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='FileOrg')
        self.member_user = User.objects.create_user(username='fileMember', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)
        self.other_user = User.objects.create_user(username='fileOther', password='pass')
        other_org = Organization.objects.create(name='Other File Org')
        UserProfile.objects.create(user=self.other_user, role='member', organization=other_org)
        self.doc = EvidenceDocument.objects.create(
            organization=self.org, title='Test', original_filename='test.pdf', file_size=100
        )

    def test_member_can_access_own_org_document(self):
        self.client.login(username='fileMember', password='pass')
        response = self.client.get(reverse('document_file', args=[self.doc.pk]))
        # Redirects to the file URL (MEDIA_URL or signed URL)
        self.assertIn(response.status_code, [200, 302])

    def test_other_org_member_gets_403(self):
        self.client.login(username='fileOther', password='pass')
        response = self.client.get(reverse('document_file', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse('document_file', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])


class LibraryListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='LibListOrg')
        self.member_user = User.objects.create_user(username='liblist_mem', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)

    def test_library_list_accessible_to_member(self):
        self.client.login(username='liblist_mem', password='pass')
        response = self.client.get(reverse('library_list'))
        self.assertEqual(response.status_code, 200)

    def test_library_list_has_no_upload_form(self):
        self.client.login(username='liblist_mem', password='pass')
        response = self.client.get(reverse('library_list'))
        self.assertNotContains(response, 'enctype="multipart/form-data"')

    def test_verifier_gets_403(self):
        ver = User.objects.create_user(username='liblist_ver', password='pass')
        UserProfile.objects.create(user=ver, role='verifier')
        self.client.login(username='liblist_ver', password='pass')
        response = self.client.get(reverse('library_list'))
        self.assertEqual(response.status_code, 403)


class LibrarySearchViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='SearchOrg')
        self.member_user = User.objects.create_user(username='search_mem', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)

        self.cycle = AwardCycle.objects.create(year=2077, name='DSE 2077', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='Cat', order=1)
        self.crit = Criterion.objects.create(category=self.cat, number=1, name='C1', order=1)
        self.crit2 = Criterion.objects.create(category=self.cat, number=2, name='C2', order=2)

        # doc1 is linked to crit (same criterion)
        self.doc1 = EvidenceDocument.objects.create(
            organization=self.org, title='Alpha', original_filename='alpha.pdf', file_size=100
        )
        resp1 = Response.objects.create(questionnaire=self.q, criterion=self.crit, score=3)
        EvidenceLink.objects.create(response=resp1, document=self.doc1)

        # doc2 is linked to crit2 (same category, different criterion)
        self.doc2 = EvidenceDocument.objects.create(
            organization=self.org, title='Beta', original_filename='beta.pdf', file_size=200
        )
        resp2 = Response.objects.create(questionnaire=self.q, criterion=self.crit2, score=2)
        EvidenceLink.objects.create(response=resp2, document=self.doc2)

        # doc3 has no links
        self.doc3 = EvidenceDocument.objects.create(
            organization=self.org, title='Gamma', original_filename='gamma.pdf', file_size=300
        )

    def _search(self, **params):
        self.client.login(username='search_mem', password='pass')
        return self.client.get(reverse('library_search'), params)

    def test_returns_json(self):
        r = self._search()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/json')

    def test_text_filter_by_title(self):
        r = self._search(q='alpha')
        data = json.loads(r.content)
        titles = [d['title'] for d in data['results']]
        self.assertIn('Alpha', titles)
        self.assertNotIn('Beta', titles)

    def test_same_criterion_ranked_first(self):
        r = self._search(criterion_id=self.crit.id)
        data = json.loads(r.content)
        ids = [d['id'] for d in data['results']]
        self.assertEqual(ids[0], self.doc1.id)

    def test_results_include_context_fields(self):
        r = self._search()
        data = json.loads(r.content)
        result = data['results'][0]
        self.assertIn('id', result)
        self.assertIn('title', result)
        self.assertIn('original_filename', result)
        self.assertIn('file_size', result)
        self.assertIn('uploaded_at', result)
        self.assertIn('cycle_name', result)
        self.assertIn('criterion_name', result)
        self.assertIn('is_suggested', result)

    def test_unauthenticated_gets_redirect(self):
        r = self.client.get(reverse('library_search'))
        self.assertEqual(r.status_code, 302)

    def test_verifier_gets_403(self):
        ver = User.objects.create_user(username='search_ver', password='pass')
        UserProfile.objects.create(user=ver, role='verifier')
        self.client.login(username='search_ver', password='pass')
        r = self.client.get(reverse('library_search'))
        self.assertEqual(r.status_code, 403)


class EvidenceLinkUnlinkTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='LinkOrg')
        self.member_user = User.objects.create_user(username='link_mem', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)
        self.cycle = AwardCycle.objects.create(year=2066, name='DSE 2066', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='Cat', order=1)
        self.crit = Criterion.objects.create(category=self.cat, number=1, name='C1', order=1)
        self.doc = EvidenceDocument.objects.create(
            organization=self.org, title='Doc', original_filename='doc.pdf', file_size=100
        )

    def _post_link(self, data):
        self.client.login(username='link_mem', password='pass')
        return self.client.post(reverse('evidence_link'), data)

    def test_link_via_questionnaire_and_criterion_creates_response_and_link(self):
        r = self._post_link({
            'questionnaire_id': self.q.pk,
            'criterion_id': self.crit.pk,
            'document_id': self.doc.pk,
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data['ok'])
        self.assertTrue(EvidenceLink.objects.filter(
            response__questionnaire=self.q,
            response__criterion=self.crit,
            document=self.doc,
        ).exists())

    def test_link_is_idempotent(self):
        self._post_link({
            'questionnaire_id': self.q.pk,
            'criterion_id': self.crit.pk,
            'document_id': self.doc.pk,
        })
        self._post_link({
            'questionnaire_id': self.q.pk,
            'criterion_id': self.crit.pk,
            'document_id': self.doc.pk,
        })
        self.assertEqual(EvidenceLink.objects.filter(document=self.doc).count(), 1)

    def test_link_blocked_after_submission(self):
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        r = self._post_link({
            'questionnaire_id': self.q.pk,
            'criterion_id': self.crit.pk,
            'document_id': self.doc.pk,
        })
        data = json.loads(r.content)
        self.assertFalse(data['ok'])
        self.assertEqual(r.status_code, 403)

    def test_unlink_removes_link_and_deletes_orphan_doc(self):
        resp = Response.objects.create(questionnaire=self.q, criterion=self.crit)
        link = EvidenceLink.objects.create(response=resp, document=self.doc)
        self.client.login(username='link_mem', password='pass')
        r = self.client.post(reverse('evidence_unlink', args=[link.pk]))
        data = json.loads(r.content)
        self.assertTrue(data['ok'])
        self.assertFalse(EvidenceLink.objects.filter(pk=link.pk).exists())
        # Doc deleted because it has no remaining links and questionnaire not submitted
        self.assertFalse(EvidenceDocument.objects.filter(pk=self.doc.pk).exists())

    def test_unlink_keeps_doc_when_other_links_exist(self):
        crit2 = Criterion.objects.create(category=self.cat, number=2, name='C2', order=2)
        resp1 = Response.objects.create(questionnaire=self.q, criterion=self.crit)
        resp2 = Response.objects.create(questionnaire=self.q, criterion=crit2)
        link1 = EvidenceLink.objects.create(response=resp1, document=self.doc)
        EvidenceLink.objects.create(response=resp2, document=self.doc)
        self.client.login(username='link_mem', password='pass')
        self.client.post(reverse('evidence_unlink', args=[link1.pk]))
        # Doc still exists — still linked via resp2
        self.assertTrue(EvidenceDocument.objects.filter(pk=self.doc.pk).exists())

    def test_unlink_blocked_after_submission(self):
        from django.utils import timezone
        resp = Response.objects.create(questionnaire=self.q, criterion=self.crit)
        link = EvidenceLink.objects.create(response=resp, document=self.doc)
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        self.client.login(username='link_mem', password='pass')
        r = self.client.post(reverse('evidence_unlink', args=[link.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(EvidenceLink.objects.filter(pk=link.pk).exists())


class QuestionnaireFillUploadTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='FillOrg')
        self.member_user = User.objects.create_user(username='fill_mem', password='pass')
        UserProfile.objects.create(user=self.member_user, role='member', organization=self.org)
        self.cycle = AwardCycle.objects.create(year=2055, name='DSE 2055', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='Cat', order=1)
        self.crit = Criterion.objects.create(category=self.cat, number=1, name='C1', order=1)
        LevelIndicator.objects.create(criterion=self.crit, level=3, indicator='Good')
        self.client.login(username='fill_mem', password='pass')

    @override_settings(
        EVIDENCE_MAX_FILE_BYTES=10 * 1024 * 1024,
        EVIDENCE_MAX_FILES_PER_RESP=5,
        EVIDENCE_MAX_QUOTA_BYTES=100 * 1024 * 1024,
        MEDIA_ROOT='/tmp/eya_test_media/',
    )
    def test_upload_creates_evidence_document_and_link(self):
        f = SimpleUploadedFile('evidence.pdf', b'%PDF-1.4 content', content_type='application/pdf')
        self.client.post(
            reverse('evidence_upload_ajax'),
            {
                'file': f,
                'questionnaire_id': self.q.pk,
                'criterion_id': self.crit.pk,
            },
        )
        self.assertEqual(EvidenceDocument.objects.filter(organization=self.org).count(), 1)
        doc = EvidenceDocument.objects.get(organization=self.org)
        self.assertEqual(doc.original_filename, 'evidence.pdf')
        self.assertTrue(EvidenceLink.objects.filter(document=doc).exists())

    @override_settings(
        EVIDENCE_MAX_FILE_BYTES=10 * 1024 * 1024,
        EVIDENCE_MAX_FILES_PER_RESP=5,
        EVIDENCE_MAX_QUOTA_BYTES=100 * 1024 * 1024,
    )
    def test_fill_page_get_contains_quota_info(self):
        r = self.client.get(
            reverse('questionnaire_fill', args=[self.q.pk]) + f'?category={self.cat.id}'
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('quota_used', r.context)


from accounts.models import VerifierAssignment


class ReportDistributionTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin_rep', password='pass')
        UserProfile.objects.create(user=self.admin, role='admin')
        self.org = Organization.objects.create(name='Org Reports A')
        self.member = User.objects.create_user(username='member_rep', password='pass')
        UserProfile.objects.create(user=self.member, role='member', organization=self.org)
        self.verifier = User.objects.create_user(username='verifier_rep', password='pass')
        UserProfile.objects.create(user=self.verifier, role='verifier')
        VerifierAssignment.objects.create(verifier=self.verifier, organization=self.org)
        self.org2 = Organization.objects.create(name='Org Reports B')
        self.cycle = AwardCycle.objects.create(year=2041, name='DSE 2041', is_open=False)
        self.q = Questionnaire.objects.create(
            cycle=self.cycle, organization=self.org, is_submitted=True
        )
        self.q2 = Questionnaire.objects.create(
            cycle=self.cycle, organization=self.org2, is_submitted=True
        )

    def test_admin_can_distribute_report(self):
        self.client.login(username='admin_rep', password='pass')
        response = self.client.post(reverse('report_distribute', args=[self.cycle.pk, self.q.pk]))
        self.assertRedirects(response, reverse('reports_cycle', args=[self.cycle.pk]), fetch_redirect_response=False)
        self.q.refresh_from_db()
        self.assertTrue(self.q.is_distributed)
        self.assertIsNotNone(self.q.distributed_at)
        self.assertEqual(self.q.distributed_by, self.admin)

    def test_verifier_can_distribute_assigned_org(self):
        self.client.login(username='verifier_rep', password='pass')
        response = self.client.post(reverse('report_distribute', args=[self.cycle.pk, self.q.pk]))
        self.assertRedirects(response, reverse('reports_cycle', args=[self.cycle.pk]), fetch_redirect_response=False)
        self.q.refresh_from_db()
        self.assertTrue(self.q.is_distributed)

    def test_verifier_cannot_distribute_unassigned_org(self):
        self.client.login(username='verifier_rep', password='pass')
        response = self.client.post(reverse('report_distribute', args=[self.cycle.pk, self.q2.pk]))
        self.assertEqual(response.status_code, 403)
        self.q2.refresh_from_db()
        self.assertFalse(self.q2.is_distributed)

    def test_distribute_blocked_when_cycle_open(self):
        self.cycle.is_open = True
        self.cycle.save()
        self.client.login(username='admin_rep', password='pass')
        response = self.client.post(reverse('report_distribute', args=[self.cycle.pk, self.q.pk]))
        self.assertRedirects(response, reverse('reports_cycle', args=[self.cycle.pk]), fetch_redirect_response=False)
        self.q.refresh_from_db()
        self.assertFalse(self.q.is_distributed)

    def test_admin_can_revoke_distributed_report(self):
        self.q.is_distributed = True
        self.q.distributed_by = self.admin
        self.q.save()
        self.client.login(username='admin_rep', password='pass')
        response = self.client.post(reverse('report_revoke', args=[self.cycle.pk, self.q.pk]))
        self.assertRedirects(response, reverse('reports_cycle', args=[self.cycle.pk]), fetch_redirect_response=False)
        self.q.refresh_from_db()
        self.assertFalse(self.q.is_distributed)
        self.assertIsNone(self.q.distributed_by)
        self.assertIsNone(self.q.distributed_at)

    def test_verifier_cannot_revoke(self):
        self.q.is_distributed = True
        self.q.save()
        self.client.login(username='verifier_rep', password='pass')
        response = self.client.post(reverse('report_revoke', args=[self.cycle.pk, self.q.pk]))
        self.assertEqual(response.status_code, 403)
        self.q.refresh_from_db()
        self.assertTrue(self.q.is_distributed)

    def test_distribute_logs_audit(self):
        from audit.models import AuditLog
        self.client.login(username='admin_rep', password='pass')
        self.client.post(reverse('report_distribute', args=[self.cycle.pk, self.q.pk]))
        self.assertTrue(
            AuditLog.objects.filter(action='report.distributed', organization=self.org).exists()
        )

    def test_revoke_logs_audit(self):
        from audit.models import AuditLog
        self.q.is_distributed = True
        self.q.save()
        self.client.login(username='admin_rep', password='pass')
        self.client.post(reverse('report_revoke', args=[self.cycle.pk, self.q.pk]))
        self.assertTrue(
            AuditLog.objects.filter(action='report.revoked', organization=self.org).exists()
        )

    def test_admin_distribute_all_distributes_all_submitted(self):
        self.client.login(username='admin_rep', password='pass')
        response = self.client.post(reverse('report_distribute_all', args=[self.cycle.pk]))
        self.assertRedirects(response, reverse('reports_cycle', args=[self.cycle.pk]), fetch_redirect_response=False)
        self.q.refresh_from_db()
        self.q2.refresh_from_db()
        self.assertTrue(self.q.is_distributed)
        self.assertTrue(self.q2.is_distributed)

    def test_verifier_distribute_all_only_affects_assigned_orgs(self):
        self.client.login(username='verifier_rep', password='pass')
        self.client.post(reverse('report_distribute_all', args=[self.cycle.pk]))
        self.q.refresh_from_db()
        self.q2.refresh_from_db()
        self.assertTrue(self.q.is_distributed)
        self.assertFalse(self.q2.is_distributed)

    def test_distribute_all_skips_already_distributed(self):
        from audit.models import AuditLog
        self.q.is_distributed = True
        self.q.save()
        self.client.login(username='admin_rep', password='pass')
        self.client.post(reverse('report_distribute_all', args=[self.cycle.pk]))
        logs = AuditLog.objects.filter(action='report.distributed')
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().organization, self.org2)

    def test_admin_reports_list_shows_cycle(self):
        self.client.login(username='admin_rep', password='pass')
        response = self.client.get(reverse('reports_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('cycle_data', response.context)
        cycles = [item['cycle'] for item in response.context['cycle_data']]
        self.assertIn(self.cycle, cycles)

    def test_member_reports_list_shows_their_cycle(self):
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('reports_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['cycle_data']), 1)
        item = response.context['cycle_data'][0]
        self.assertFalse(item['available'])

    def test_member_reports_list_available_when_distributed_and_closed(self):
        self.q.is_distributed = True
        self.q.save()
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('reports_list'))
        item = response.context['cycle_data'][0]
        self.assertTrue(item['available'])

    def test_verifier_reports_list_shows_only_assigned_cycles(self):
        cycle2 = AwardCycle.objects.create(year=2042, name='DSE 2042', is_open=False)
        Questionnaire.objects.create(cycle=cycle2, organization=self.org2, is_submitted=True)
        self.client.login(username='verifier_rep', password='pass')
        response = self.client.get(reverse('reports_list'))
        cycle_pks = [item['cycle'].pk for item in response.context['cycle_data']]
        self.assertIn(self.cycle.pk, cycle_pks)
        self.assertNotIn(cycle2.pk, cycle_pks)

    def test_admin_reports_cycle_shows_all_questionnaires(self):
        self.client.login(username='admin_rep', password='pass')
        response = self.client.get(reverse('reports_cycle', args=[self.cycle.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            list(response.context['questionnaires']),
            list(Questionnaire.objects.filter(cycle=self.cycle))
        )

    def test_verifier_reports_cycle_shows_only_assigned_orgs(self):
        self.client.login(username='verifier_rep', password='pass')
        response = self.client.get(reverse('reports_cycle', args=[self.cycle.pk]))
        self.assertEqual(response.status_code, 200)
        qs = list(response.context['questionnaires'])
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].organization, self.org)

    def test_member_reports_cycle_locked_when_not_distributed(self):
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('reports_cycle', args=[self.cycle.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not yet available')

    def test_member_reports_cycle_redirects_when_available(self):
        self.q.is_distributed = True
        self.q.save()
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('reports_cycle', args=[self.cycle.pk]))
        self.assertRedirects(
            response,
            reverse('org_report', args=[self.cycle.pk, self.q.pk]),
            fetch_redirect_response=False
        )

    def test_member_can_access_org_report_when_distributed_and_closed(self):
        self.q.is_distributed = True
        self.q.save()
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('org_report', args=[self.cycle.pk, self.q.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_member'])

    def test_member_cannot_access_org_report_when_not_distributed(self):
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('org_report', args=[self.cycle.pk, self.q.pk]))
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_access_org_report_when_cycle_open(self):
        self.q.is_distributed = True
        self.q.save()
        self.cycle.is_open = True
        self.cycle.save()
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('org_report', args=[self.cycle.pk, self.q.pk]))
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_access_another_orgs_report(self):
        self.q2.is_distributed = True
        self.q2.save()
        self.client.login(username='member_rep', password='pass')
        response = self.client.get(reverse('org_report', args=[self.cycle.pk, self.q2.pk]))
        self.assertEqual(response.status_code, 403)


class InformalSectorScopingTest(TestCase):
    """Tests for org-type-scoped category visibility."""

    def setUp(self):
        self.regular_org = Organization.objects.create(
            name='Regular Org', org_type='government_agency', is_active=True
        )
        self.informal_org = Organization.objects.create(
            name='Informal Org', org_type='informal_sector', is_active=True
        )

        # Create cycle closed so we control questionnaire creation
        self.cycle = AwardCycle.objects.create(year=2099, name='DSE 2099', is_open=False)

        # Two categories: one regular, one informal-only
        self.regular_cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Category A', order=1,
            is_active=True, is_informal_sector_only=False,
        )
        self.informal_cat = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Informal Sector', order=2,
            is_active=True, is_informal_sector_only=True,
        )

        # One criterion per category
        self.regular_crit = Criterion.objects.create(
            category=self.regular_cat, number=1, name='R1', order=1, is_active=True,
        )
        self.informal_crit = Criterion.objects.create(
            category=self.informal_cat, number=1, name='I1', order=1, is_active=True,
        )

        # Open cycle — auto-creates a Questionnaire for each active org
        self.cycle.is_open = True
        self.cycle.save()

        self.regular_q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.regular_org)[0]
        self.informal_q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.informal_org)[0]

        # Member users
        self.regular_user = User.objects.create_user(username='regular_member', password='Pass@123')
        UserProfile.objects.create(user=self.regular_user, role='member', organization=self.regular_org)
        self.informal_user = User.objects.create_user(username='informal_member', password='Pass@123')
        UserProfile.objects.create(user=self.informal_user, role='member', organization=self.informal_org)

    # ── Helper unit tests ──────────────────────────────────────────────────────

    def test_categories_for_org_returns_informal_only_for_informal_org(self):
        from assessment.models import categories_for_org
        qs = categories_for_org(self.cycle, self.informal_org)
        names = list(qs.values_list('name', flat=True))
        self.assertIn('Informal Sector', names)
        self.assertNotIn('Category A', names)

    def test_categories_for_org_excludes_informal_for_regular_org(self):
        from assessment.models import categories_for_org
        qs = categories_for_org(self.cycle, self.regular_org)
        names = list(qs.values_list('name', flat=True))
        self.assertNotIn('Informal Sector', names)
        self.assertIn('Category A', names)

    # ── Excel parser tests ─────────────────────────────────────────────────────

    def test_excel_parser_tags_last_informal_sheet(self):
        """Parser sets is_informal_sector_only=True on last sheet when name contains 'informal'."""
        import io
        import openpyxl
        from assessment.excel_parser import parse_excel_questionnaire

        wb = openpyxl.Workbook()
        # Sheet 1: regular category
        ws1 = wb.active
        ws1.title = 'Category A'
        ws1['A1'] = 'Preamble A'
        ws1['A4'] = 1
        ws1['B4'] = 'Criterion 1'
        ws1['C4'] = 0
        ws1['D4'] = 'Level 0 indicator'
        # Sheet 2: informal sector (last, name contains 'informal')
        ws2 = wb.create_sheet('Informal Sector')
        ws2['A1'] = 'Preamble Informal'
        ws2['A4'] = 1
        ws2['B4'] = 'Inf Criterion 1'
        ws2['C4'] = 0
        ws2['D4'] = 'Level 0 indicator'

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        # Use a fresh cycle to avoid collisions with setUp cycle
        fresh_cycle = AwardCycle.objects.create(year=2097, name='Parser Test 2097', is_open=False)
        parse_excel_questionnaire(buf, fresh_cycle)

        cat_a = AssessmentCategory.objects.get(cycle=fresh_cycle, name='Category A')
        cat_inf = AssessmentCategory.objects.get(cycle=fresh_cycle, name='Informal Sector')
        self.assertFalse(cat_a.is_informal_sector_only)
        self.assertTrue(cat_inf.is_informal_sector_only)

    def test_excel_parser_no_tag_when_last_sheet_not_informal(self):
        """If the last sheet name does not contain 'informal', no category is tagged."""
        import io
        import openpyxl
        from assessment.excel_parser import parse_excel_questionnaire

        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = 'Category A'
        ws1['A1'] = 'Preamble A'
        ws1['A4'] = 1
        ws1['B4'] = 'Criterion 1'
        ws1['C4'] = 0
        ws1['D4'] = 'Level 0 indicator'
        ws2 = wb.create_sheet('Category B')   # last sheet — no 'informal' in name
        ws2['A1'] = 'Preamble B'
        ws2['A4'] = 1
        ws2['B4'] = 'Criterion 1'
        ws2['C4'] = 0
        ws2['D4'] = 'Level 0 indicator'

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        fresh_cycle = AwardCycle.objects.create(year=2096, name='Parser Test 2096', is_open=False)
        parse_excel_questionnaire(buf, fresh_cycle)

        self.assertFalse(
            AssessmentCategory.objects.filter(cycle=fresh_cycle, is_informal_sector_only=True).exists()
        )

    # ── Completion percentage ──────────────────────────────────────────────────

    def test_completion_percentage_scoped(self):
        """completion_percentage counts only criteria from the org's applicable categories."""
        # Informal org answers its criterion → 100 %
        Response.objects.create(
            questionnaire=self.informal_q, criterion=self.informal_crit, score=3
        )
        self.assertEqual(self.informal_q.completion_percentage, 100.0)

        # That response must not affect the regular org's percentage
        self.assertEqual(self.regular_q.completion_percentage, 0.0)

        # Regular org answers its criterion → 100 %
        Response.objects.create(
            questionnaire=self.regular_q, criterion=self.regular_crit, score=4
        )
        self.assertEqual(self.regular_q.completion_percentage, 100.0)

    # ── Fill view ──────────────────────────────────────────────────────────────

    def test_informal_org_sees_only_informal_category_on_fill(self):
        """Informal org member: fill page context contains only the informal category."""
        self.client.login(username='informal_member', password='Pass@123')
        url = reverse('questionnaire_fill', kwargs={'pk': self.informal_q.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        cat_names = [c.name for c in response.context['categories']]
        self.assertIn('Informal Sector', cat_names)
        self.assertNotIn('Category A', cat_names)

    def test_regular_org_skips_informal_category_on_fill(self):
        """Regular org member: fill page context does not include the informal category."""
        self.client.login(username='regular_member', password='Pass@123')
        url = reverse('questionnaire_fill', kwargs={'pk': self.regular_q.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        cat_names = [c.name for c in response.context['categories']]
        self.assertNotIn('Informal Sector', cat_names)
        self.assertIn('Category A', cat_names)

    # ── Verifier view ──────────────────────────────────────────────────────────

    def test_verify_view_scoped_to_org_categories(self):
        """Verifier sees only the informal category for an informal org's questionnaire."""
        from accounts.models import VerifierAssignment

        # Submit the informal questionnaire
        Response.objects.create(
            questionnaire=self.informal_q, criterion=self.informal_crit, score=3
        )
        self.informal_q.is_submitted = True
        self.informal_q.save()

        # Create a verifier assigned to the informal org
        verifier = User.objects.create_user(username='verifier_inf', password='Pass@123')
        UserProfile.objects.create(user=verifier, role='verifier')
        VerifierAssignment.objects.create(verifier=verifier, organization=self.informal_org)

        self.client.login(username='verifier_inf', password='Pass@123')
        url = reverse('verify_questionnaire', kwargs={'pk': self.informal_q.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        cat_names = list(response.context['categories'].values_list('name', flat=True))
        self.assertIn('Informal Sector', cat_names)
        self.assertNotIn('Category A', cat_names)

    # ── Analytics ──────────────────────────────────────────────────────────────

    def test_compute_org_analytics_scoped(self):
        """compute_org_analytics returns only applicable categories for each org type."""
        from assessment.analytics import compute_org_analytics

        # Score the informal criterion on the informal questionnaire
        Response.objects.create(
            questionnaire=self.informal_q, criterion=self.informal_crit, score=4
        )
        self.informal_q.is_submitted = True
        self.informal_q.save()

        analytics = compute_org_analytics(self.informal_q)
        returned_cat_names = [entry['category'].name for entry in analytics['categories']]
        self.assertIn('Informal Sector', returned_cat_names)
        self.assertNotIn('Category A', returned_cat_names)


class SaveCategoryAjaxTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='SaveCat Org')
        self.user = User.objects.create_user(username='savecat_mem', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='savecat_mem', password='pass')
        self.cycle = AwardCycle.objects.create(year=2070, name='DSE 2070', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='Cat A', order=1)
        self.cat2 = AssessmentCategory.objects.create(cycle=self.cycle, name='Cat B', order=2)
        self.crit = Criterion.objects.create(category=self.cat, number=1, name='C1', order=1)
        LevelIndicator.objects.create(criterion=self.crit, level=3, indicator='Good')

    def _url(self):
        return reverse('save_category', args=[self.q.pk])

    def test_saves_score_and_notes(self):
        r = self.client.post(self._url(), {
            'category_id': self.cat.pk,
            f'criterion_{self.crit.pk}': '3',
            f'notes_{self.crit.pk}': 'test note',
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data['success'])
        resp = Response.objects.get(questionnaire=self.q, criterion=self.crit)
        self.assertEqual(resp.score, 3)
        self.assertEqual(resp.notes, 'test note')

    def test_returns_next_url_when_next_category_exists(self):
        r = self.client.post(self._url(), {
            'category_id': self.cat.pk,
            f'criterion_{self.crit.pk}': '3',
            f'notes_{self.crit.pk}': '',
        })
        data = json.loads(r.content)
        self.assertTrue(data['success'])
        self.assertIsNotNone(data['next_url'])
        self.assertIn(f'category={self.cat2.pk}', data['next_url'])

    def test_returns_null_next_url_for_last_category(self):
        r = self.client.post(self._url(), {
            'category_id': self.cat2.pk,
        })
        data = json.loads(r.content)
        self.assertTrue(data['success'])
        self.assertIsNone(data['next_url'])

    def test_returns_message_with_category_name(self):
        r = self.client.post(self._url(), {
            'category_id': self.cat.pk,
            f'criterion_{self.crit.pk}': '3',
            f'notes_{self.crit.pk}': '',
        })
        data = json.loads(r.content)
        self.assertIn('Cat A', data['message'])

    def test_submitted_questionnaire_returns_403(self):
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        r = self.client.post(self._url(), {'category_id': self.cat.pk})
        self.assertEqual(r.status_code, 403)

    def test_closed_cycle_returns_403(self):
        self.cycle.is_open = False
        self.cycle.save()
        r = self.client.post(self._url(), {'category_id': self.cat.pk})
        self.assertEqual(r.status_code, 403)
        data = json.loads(r.content)
        self.assertFalse(data['success'])

    def test_cross_cycle_category_returns_404(self):
        other_cycle = AwardCycle.objects.create(year=2071, name='DSE 2071')
        other_cat = AssessmentCategory.objects.create(cycle=other_cycle, name='Other', order=1)
        r = self.client.post(self._url(), {'category_id': other_cat.pk})
        self.assertEqual(r.status_code, 404)

    def test_non_member_redirected(self):
        self.client.logout()
        admin = User.objects.create_user(username='admin_savecat', password='pass')
        UserProfile.objects.create(user=admin, role='admin')
        self.client.login(username='admin_savecat', password='pass')
        r = self.client.post(self._url(), {'category_id': self.cat.pk})
        self.assertEqual(r.status_code, 302)

    def test_other_org_member_returns_403(self):
        other_org = Organization.objects.create(name='OtherSaveCat')
        other_user = User.objects.create_user(username='other_savecat', password='pass')
        UserProfile.objects.create(user=other_user, role='member', organization=other_org)
        self.client.login(username='other_savecat', password='pass')
        r = self.client.post(self._url(), {'category_id': self.cat.pk})
        self.assertEqual(r.status_code, 403)


class FileSignatureValidationTest(TestCase):
    def test_real_pdf_passes(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('doc.pdf', b'%PDF-1.7\n...rest', content_type='application/pdf')
        self.assertTrue(_content_matches_extension(f))

    def test_real_png_passes(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('img.png', b'\x89PNG\r\n\x1a\n....', content_type='image/png')
        self.assertTrue(_content_matches_extension(f))

    def test_real_jpeg_passes(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('img.jpg', b'\xff\xd8\xff\xe0....', content_type='image/jpeg')
        self.assertTrue(_content_matches_extension(f))

    def test_docx_zip_signature_passes(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('doc.docx', b'PK\x03\x04....', content_type='application/octet-stream')
        self.assertTrue(_content_matches_extension(f))

    def test_html_disguised_as_png_is_rejected(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('evil.png', b'<html><script>alert(1)</script>', content_type='image/png')
        self.assertFalse(_content_matches_extension(f))

    def test_stream_position_is_restored(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('doc.pdf', b'%PDF-1.7 body', content_type='application/pdf')
        _content_matches_extension(f)
        self.assertEqual(f.read(), b'%PDF-1.7 body')  # full content still readable afterwards

    def test_empty_file_is_rejected(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('empty.pdf', b'', content_type='application/pdf')
        self.assertFalse(_content_matches_extension(f))

    def test_doc_ole_signature_passes(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('doc.doc', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', content_type='application/msword')
        self.assertTrue(_content_matches_extension(f))

    def test_unknown_extension_is_rejected(self):
        from assessment.views import _content_matches_extension
        f = SimpleUploadedFile('file.txt', b'hello world', content_type='text/plain')
        self.assertFalse(_content_matches_extension(f))


class EvidenceUploadAjaxTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='EvUpload Org')
        self.user = User.objects.create_user(username='evupload_mem', password='pass')
        UserProfile.objects.create(user=self.user, role='member', organization=self.org)
        self.client.login(username='evupload_mem', password='pass')
        self.cycle = AwardCycle.objects.create(year=2072, name='DSE 2072', is_open=True)
        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.cat = AssessmentCategory.objects.create(cycle=self.cycle, name='EvCat', order=1)
        self.crit = Criterion.objects.create(category=self.cat, number=1, name='EvCrit', order=1)

    def _url(self):
        return reverse('evidence_upload_ajax')

    def _post(self, filename, content, content_type='application/pdf', extra=None):
        data = {
            'file': SimpleUploadedFile(filename, content, content_type=content_type),
            'questionnaire_id': self.q.pk,
            'criterion_id': self.crit.pk,
        }
        if extra:
            data.update(extra)
        return self.client.post(self._url(), data)

    @override_settings(
        EVIDENCE_MAX_FILE_BYTES=10 * 1024 * 1024,
        EVIDENCE_MAX_FILES_PER_RESP=5,
        EVIDENCE_MAX_QUOTA_BYTES=100 * 1024 * 1024,
        MEDIA_ROOT='/tmp/eya_test_media/',
    )
    def test_creates_evidence_doc_and_link(self):
        r = self._post('doc.pdf', b'%PDF-1.4 content')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data['success'])
        self.assertIn('document', data)
        self.assertIn('id', data['document'])
        self.assertIn('title', data['document'])
        self.assertIn('original_filename', data['document'])
        self.assertIn('file_url', data['document'])
        self.assertIn('delete_url', data['document'])
        self.assertEqual(EvidenceDocument.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(EvidenceLink.objects.filter(response__questionnaire=self.q).count(), 1)

    @override_settings(
        EVIDENCE_MAX_FILE_BYTES=100,
        EVIDENCE_MAX_FILES_PER_RESP=5,
        EVIDENCE_MAX_QUOTA_BYTES=100 * 1024 * 1024,
    )
    def test_rejects_oversized_file(self):
        r = self._post('big.pdf', b'%PDF-1.4' + b'x' * 200)
        data = json.loads(r.content)
        self.assertFalse(data['success'])
        self.assertIn('exceeds', data['error'])

    def test_rejects_disallowed_extension(self):
        r = self._post('script.exe', b'MZ executable', content_type='application/octet-stream')
        data = json.loads(r.content)
        self.assertFalse(data['success'])
        self.assertIn('unsupported', data['error'])

    def test_rejects_magic_byte_mismatch(self):
        r = self._post('fake.pdf', b'not a pdf at all')
        data = json.loads(r.content)
        self.assertFalse(data['success'])
        self.assertIn('content does not match', data['error'])

    @override_settings(
        EVIDENCE_MAX_FILE_BYTES=10 * 1024 * 1024,
        EVIDENCE_MAX_FILES_PER_RESP=2,
        EVIDENCE_MAX_QUOTA_BYTES=100 * 1024 * 1024,
        MEDIA_ROOT='/tmp/eya_test_media/',
    )
    def test_rejects_when_per_criterion_limit_reached(self):
        resp, _ = Response.objects.get_or_create(questionnaire=self.q, criterion=self.crit)
        for i in range(2):
            doc = EvidenceDocument.objects.create(
                organization=self.org, title=f'Doc{i}',
                original_filename=f'doc{i}.pdf', file_size=100,
            )
            EvidenceLink.objects.create(response=resp, document=doc)
        r = self._post('extra.pdf', b'%PDF-1.4 content')
        data = json.loads(r.content)
        self.assertFalse(data['success'])
        self.assertIn('max', data['error'].lower())

    @override_settings(
        EVIDENCE_MAX_FILE_BYTES=10 * 1024 * 1024,
        EVIDENCE_MAX_FILES_PER_RESP=5,
        EVIDENCE_MAX_QUOTA_BYTES=50,
    )
    def test_rejects_when_quota_exceeded(self):
        r = self._post('quota.pdf', b'%PDF-1.4' + b'x' * 100)
        data = json.loads(r.content)
        self.assertFalse(data['success'])
        self.assertIn('quota', data['error'].lower())

    def test_non_member_redirected(self):
        self.client.logout()
        admin = User.objects.create_user(username='admin_evup', password='pass')
        UserProfile.objects.create(user=admin, role='admin')
        self.client.login(username='admin_evup', password='pass')
        r = self._post('doc.pdf', b'%PDF-1.4 content')
        self.assertEqual(r.status_code, 302)

    def test_submitted_questionnaire_returns_403(self):
        from django.utils import timezone
        self.q.is_submitted = True
        self.q.submitted_at = timezone.now()
        self.q.save()
        r = self._post('doc.pdf', b'%PDF-1.4 content')
        self.assertEqual(r.status_code, 403)

    def test_other_org_member_returns_403(self):
        other_org = Organization.objects.create(name='OtherEvUpload')
        other_user = User.objects.create_user(username='other_evupload', password='pass')
        UserProfile.objects.create(user=other_user, role='member', organization=other_org)
        self.client.login(username='other_evupload', password='pass')
        r = self._post('doc.pdf', b'%PDF-1.4 content')
        self.assertEqual(r.status_code, 403)


class PruneOrphanEvidenceCommandTest(TestCase):
    """prune_orphan_evidence decides what to delete by diffing storage against
    the database, so its guards are the only thing standing between a
    wrong-database run and deleting real evidence. Test the guards, not just
    the happy path."""

    def setUp(self):
        import tempfile
        from django.core.files.base import ContentFile

        self.media = tempfile.mkdtemp(prefix='prune_test_')
        # Applies to setUp and the test body; undone even if the test fails.
        patcher = override_settings(MEDIA_ROOT=self.media)
        patcher.enable()
        self.addCleanup(patcher.disable)

        self.org = Organization.objects.create(name='Prune Org')
        self.doc = EvidenceDocument.objects.create(
            organization=self.org, title='kept',
            original_filename='kept.pdf', file_size=13,
        )
        self.doc.file.save('evidence/1/kept.pdf', ContentFile(b'%PDF-1.4 keep'), save=True)
        self.kept_key = self.doc.file.name

    def tearDown(self):
        import shutil
        shutil.rmtree(self.media, ignore_errors=True)

    def _write_orphan(self, rel='evidence/999/orphan.pdf'):
        """Write a file nothing in the DB references."""
        import os
        full = os.path.join(self.media, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as fh:
            fh.write(b'%PDF-1.4 content')
        return full

    def _exists(self, rel):
        import os
        return os.path.exists(os.path.join(self.media, rel))

    def _run(self, **kw):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        opts = {'stdout': out, 'min_age_hours': 0, 'noinput': True}
        opts.update(kw)
        call_command('prune_orphan_evidence', **opts)
        return out.getvalue()

    def test_dry_run_reports_orphan_but_deletes_nothing(self):
        self._write_orphan()
        out = self._run()
        self.assertIn('evidence/999/orphan.pdf', out)
        self.assertIn('DRY RUN', out)
        self.assertTrue(self._exists('evidence/999/orphan.pdf'),
                        'dry run must not delete anything')

    def test_delete_removes_orphan_and_keeps_referenced_file(self):
        self._write_orphan()
        out = self._run(delete=True, max_orphan_pct=99)
        self.assertFalse(self._exists('evidence/999/orphan.pdf'))
        self.assertTrue(self._exists(self.kept_key),
                        'a file referenced by an EvidenceDocument must survive')
        self.assertIn('Deleted 1', out)

    def test_refuses_when_no_rows_reference_a_file(self):
        """The wrong-database case: an empty table makes every object look
        orphaned. This is the guard that saved the production bucket."""
        from django.core.management.base import CommandError
        self._write_orphan()
        EvidenceDocument.objects.all().delete()
        with self.assertRaises(CommandError) as ctx:
            self._run(delete=True)
        self.assertIn('Refusing to run', str(ctx.exception))
        self.assertTrue(self._exists('evidence/999/orphan.pdf'))

    def test_orphan_ratio_guard_blocks_delete(self):
        from django.core.management.base import CommandError
        for i in range(6):
            self._write_orphan(f'evidence/99{i}/orphan{i}.pdf')
        with self.assertRaises(CommandError) as ctx:
            self._run(delete=True)          # 6 of 7 scanned = 85%, over the 25% default
        self.assertIn('Refusing to delete', str(ctx.exception))
        self.assertTrue(self._exists('evidence/990/orphan0.pdf'))
        self.assertTrue(self._exists(self.kept_key))

    def test_ratio_guard_can_be_overridden_with_force(self):
        for i in range(6):
            self._write_orphan(f'evidence/99{i}/orphan{i}.pdf')
        out = self._run(delete=True, force=True)
        self.assertIn('Deleted 6', out)
        self.assertTrue(self._exists(self.kept_key))

    def test_recent_orphans_are_skipped_by_age_guard(self):
        """Protects an upload whose file is written but whose row has not
        committed yet."""
        self._write_orphan()
        out = self._run(min_age_hours=24, delete=True, max_orphan_pct=99)
        self.assertTrue(self._exists('evidence/999/orphan.pdf'))
        self.assertIn('No orphans', out)

    def test_prefix_scopes_the_scan(self):
        import os
        os.makedirs(os.path.join(self.media, 'cycles'), exist_ok=True)
        with open(os.path.join(self.media, 'cycles', 'import.xlsx'), 'wb') as fh:
            fh.write(b'PK\x03\x04 not evidence')
        self._run(delete=True, max_orphan_pct=99)
        self.assertTrue(self._exists('cycles/import.xlsx'),
                        'files outside the evidence/ prefix must never be scanned')


class VerifierCoverageTest(TestCase):
    """Cross-verifier coverage — who has already verified what."""

    def setUp(self):
        from accounts.models import VerifierAssignment

        self.org = Organization.objects.create(
            name='Coverage Org', org_type='ict', is_active=True
        )
        self.informal_org = Organization.objects.create(
            name='Coverage Informal', org_type='informal_sector', is_active=True
        )

        # Cycle closed first so we control questionnaire creation.
        self.cycle = AwardCycle.objects.create(year=2098, name='DSE 2098', is_open=False)

        self.cat_a = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Cat A', order=1,
            is_active=True, is_informal_sector_only=False,
        )
        self.cat_b = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Cat B', order=2,
            is_active=True, is_informal_sector_only=False,
        )
        self.cat_informal = AssessmentCategory.objects.create(
            cycle=self.cycle, name='Informal Sector', order=3,
            is_active=True, is_informal_sector_only=True,
        )

        self.crit_a1 = Criterion.objects.create(
            category=self.cat_a, number=1, name='A1', order=1, is_active=True)
        self.crit_a2 = Criterion.objects.create(
            category=self.cat_a, number=2, name='A2', order=2, is_active=True)
        self.crit_b1 = Criterion.objects.create(
            category=self.cat_b, number=1, name='B1', order=1, is_active=True)
        self.crit_num = Criterion.objects.create(
            category=self.cat_b, number=2, name='B2 numeric', order=2, is_active=True,
            is_numeric=True, numeric_fields=[{'name': 'Headcount', 'type': 'integer'}])
        self.crit_informal = Criterion.objects.create(
            category=self.cat_informal, number=1, name='I1', order=1, is_active=True)

        for level in range(6):
            LevelIndicator.objects.create(
                criterion=self.crit_a1, level=level, indicator=f'A1 level {level}')

        # Open the cycle — auto-creates a Questionnaire per active org.
        self.cycle.is_open = True
        self.cycle.save()

        self.q = Questionnaire.objects.get_or_create(cycle=self.cycle, organization=self.org)[0]
        self.q.is_submitted = True
        self.q.save()
        self.informal_q = Questionnaire.objects.get_or_create(
            cycle=self.cycle, organization=self.informal_org)[0]
        self.informal_q.is_submitted = True
        self.informal_q.save()

        self.v1 = User.objects.create_user(
            username='cov_v1', password='Pass@123', first_name='Joyce', last_name='Mwita')
        UserProfile.objects.create(user=self.v1, role='verifier')
        self.v2 = User.objects.create_user(
            username='cov_v2', password='Pass@123', first_name='Amina', last_name='Kimaro')
        UserProfile.objects.create(user=self.v2, role='verifier')
        for verifier in (self.v1, self.v2):
            VerifierAssignment.objects.create(verifier=verifier, organization=self.org)
            VerifierAssignment.objects.create(
                verifier=verifier, organization=self.informal_org)

    # ── criterion_coverage ────────────────────────────────────────────────────

    def test_criterion_coverage_lists_each_verifier_oldest_first(self):
        from assessment.coverage import criterion_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a1, score=3)
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_a1, score=4)

        result = criterion_coverage(self.q, [self.crit_a1, self.crit_a2])

        entries = result[self.crit_a1.id]
        self.assertEqual([e['name'] for e in entries], ['Joyce Mwita', 'Amina Kimaro'])
        self.assertEqual([e['verifier_id'] for e in entries], [self.v1.id, self.v2.id])
        self.assertNotIn(self.crit_a2.id, result)

    def test_criterion_coverage_falls_back_to_username(self):
        from assessment.coverage import criterion_coverage

        nameless = User.objects.create_user(username='cov_v3', password='Pass@123')
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=nameless, criterion=self.crit_a1, score=2)

        result = criterion_coverage(self.q, [self.crit_a1])

        self.assertEqual(result[self.crit_a1.id][0]['name'], 'cov_v3')

    def test_criterion_coverage_ignores_null_score(self):
        from assessment.coverage import criterion_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a1,
            score=None, notes='thinking about it')

        self.assertEqual(criterion_coverage(self.q, [self.crit_a1]), {})

    def test_criterion_coverage_numeric_needs_notes(self):
        from assessment.coverage import criterion_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_num,
            score=None, notes='   ')
        self.assertEqual(criterion_coverage(self.q, [self.crit_num]), {})

        VerifierResponse.objects.filter(criterion=self.crit_num).update(
            notes='Figures confirmed against payroll.')
        result = criterion_coverage(self.q, [self.crit_num])
        self.assertEqual(result[self.crit_num.id][0]['name'], 'Joyce Mwita')

    def test_criterion_coverage_empty_criteria_returns_empty(self):
        from assessment.coverage import criterion_coverage

        self.assertEqual(criterion_coverage(self.q, []), {})

    def test_criterion_coverage_scoped_to_questionnaire(self):
        from assessment.coverage import criterion_coverage

        VerifierResponse.objects.create(
            questionnaire=self.informal_q, verifier=self.v1,
            criterion=self.crit_informal, score=5)

        self.assertEqual(criterion_coverage(self.q, [self.crit_informal]), {})

    # ── category_coverage ─────────────────────────────────────────────────────

    def test_category_coverage_counts_covered_over_total(self):
        from assessment.coverage import category_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a1, score=3)

        result = category_coverage(self.q)

        self.assertEqual(result[self.cat_a.id], (1, 2))
        self.assertEqual(result[self.cat_b.id], (0, 2))

    def test_category_coverage_counts_a_criterion_once_per_category(self):
        from assessment.coverage import category_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a1, score=3)
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_a1, score=5)

        # Two verifiers, one criterion — still 1 of 2 covered, never 2 of 2.
        self.assertEqual(category_coverage(self.q)[self.cat_a.id], (1, 2))

    def test_category_coverage_total_excludes_inactive_criteria(self):
        from assessment.coverage import category_coverage

        self.crit_a2.is_active = False
        self.crit_a2.save()

        self.assertEqual(category_coverage(self.q)[self.cat_a.id], (0, 1))

    def test_category_coverage_ignores_rows_on_inactive_criteria(self):
        from assessment.coverage import category_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a2, score=4)
        self.crit_a2.is_active = False
        self.crit_a2.save()

        # A stale row must not push the category past its own total.
        covered, total = category_coverage(self.q)[self.cat_a.id]
        self.assertEqual((covered, total), (0, 1))
        self.assertLessEqual(covered, total)

    def test_category_coverage_scopes_regular_org_to_regular_categories(self):
        from assessment.coverage import category_coverage

        result = category_coverage(self.q)

        self.assertIn(self.cat_a.id, result)
        self.assertIn(self.cat_b.id, result)
        self.assertNotIn(self.cat_informal.id, result)

    def test_category_coverage_scopes_informal_org_to_informal_category(self):
        from assessment.coverage import category_coverage

        VerifierResponse.objects.create(
            questionnaire=self.informal_q, verifier=self.v1,
            criterion=self.crit_informal, score=2)

        result = category_coverage(self.informal_q)

        self.assertEqual(result[self.cat_informal.id], (1, 1))
        self.assertNotIn(self.cat_a.id, result)
        self.assertNotIn(self.cat_b.id, result)

    # ── questionnaire_coverage ────────────────────────────────────────────────

    def test_questionnaire_coverage_totals_per_questionnaire(self):
        from assessment.coverage import questionnaire_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a1, score=3)
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_b1, score=4)
        VerifierResponse.objects.create(
            questionnaire=self.informal_q, verifier=self.v1,
            criterion=self.crit_informal, score=1)

        result = questionnaire_coverage([self.q, self.informal_q])

        # Regular org: 4 applicable criteria (A1, A2, B1, B2-numeric), 2 covered.
        self.assertEqual(result[self.q.pk], (2, 4))
        # Informal org: only the informal category applies.
        self.assertEqual(result[self.informal_q.pk], (1, 1))

    def test_questionnaire_coverage_empty_input(self):
        from assessment.coverage import questionnaire_coverage

        self.assertEqual(questionnaire_coverage([]), {})

    def test_questionnaire_coverage_zero_when_nothing_verified(self):
        from assessment.coverage import questionnaire_coverage

        self.assertEqual(questionnaire_coverage([self.q])[self.q.pk], (0, 4))

    def test_questionnaire_coverage_ignores_cross_org_criteria(self):
        from assessment.coverage import questionnaire_coverage

        # A row against a criterion outside the org's applicable set.
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1,
            criterion=self.crit_informal, score=5)

        covered, total = questionnaire_coverage([self.q])[self.q.pk]
        self.assertEqual((covered, total), (0, 4))

    def test_questionnaire_coverage_query_count_is_fixed(self):
        from assessment.coverage import questionnaire_coverage

        questionnaires = list(
            Questionnaire.objects.filter(cycle=self.cycle).select_related('organization')
        )
        self.assertGreaterEqual(len(questionnaires), 2)

        with self.assertNumQueries(2):
            questionnaire_coverage(questionnaires)

    def test_category_coverage_numeric_criterion_needs_notes(self):
        from assessment.coverage import category_coverage

        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_num,
            score=None, notes='')
        self.assertEqual(category_coverage(self.q)[self.cat_b.id], (0, 2))

        VerifierResponse.objects.filter(criterion=self.crit_num).update(notes='Checked.')
        self.assertEqual(category_coverage(self.q)[self.cat_b.id], (1, 2))

    # ── verify page ───────────────────────────────────────────────────────────

    def test_verify_page_shows_other_verifier_name(self):
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_a1, score=4)

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(
            reverse('verify_questionnaire', args=[self.q.pk]),
            {'category': self.cat_a.id},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Amina Kimaro')

    def test_verify_page_never_reveals_other_verifier_score(self):
        """The 'name + date only' decision. A leak here reintroduces anchoring."""
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_a1,
            score=4, notes='Evidence covers 2024 only.')

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(
            reverse('verify_questionnaire', args=[self.q.pk]),
            {'category': self.cat_a.id},
        )

        self.assertNotContains(resp, 'Evidence covers 2024 only.')
        entry = next(
            item for item in resp.context['criteria_data']
            if item['criterion'].id == self.crit_a1.id
        )
        self.assertEqual(len(entry['others']), 1)
        self.assertEqual(set(entry['others'][0]), {'verifier_id', 'name', 'at'})

    def test_verify_page_excludes_own_work_from_chip(self):
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a1, score=3)

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(
            reverse('verify_questionnaire', args=[self.q.pk]),
            {'category': self.cat_a.id},
        )

        entry = next(
            item for item in resp.context['criteria_data']
            if item['criterion'].id == self.crit_a1.id
        )
        self.assertEqual(entry['others'], [])

    def test_verify_page_scoring_stays_enabled_when_covered(self):
        """The 'inform only' decision — coverage must never lock the controls."""
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_a1, score=4)

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(
            reverse('verify_questionnaire', args=[self.q.pk]),
            {'category': self.cat_a.id},
        )

        # Check the radio tags themselves — 'disabled' appears elsewhere in
        # base.html's form-loading JS, so a whole-page assertion would be a
        # false positive.
        html = resp.content.decode()
        tags = re.findall(
            rf'<input type="radio" name="criterion_{self.crit_a1.id}"[^>]*>', html)
        self.assertEqual(len(tags), 6)
        for tag in tags:
            self.assertNotIn('disabled', tag)

    def test_verify_page_category_nav_counts(self):
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_a1, score=4)

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(reverse('verify_questionnaire', args=[self.q.pk]))

        nav = {entry['category'].id: entry for entry in resp.context['category_nav']}
        self.assertEqual((nav[self.cat_a.id]['covered'], nav[self.cat_a.id]['total']), (1, 2))
        self.assertEqual((nav[self.cat_b.id]['covered'], nav[self.cat_b.id]['total']), (0, 2))
        self.assertContains(resp, '1/2')

    # ── verifier dashboard ────────────────────────────────────────────────────

    def test_dashboard_shows_coverage_for_submitted_questionnaire(self):
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_a1, score=4)

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(reverse('verifier_dashboard'))

        row = next(
            item for item in resp.context['org_data']
            if item['org'].id == self.org.id
        )
        self.assertEqual(row['coverage'], (1, 4))
        self.assertContains(resp, 'Coverage')
        self.assertContains(resp, '1/4')

    def test_dashboard_coverage_none_when_not_submitted(self):
        self.q.is_submitted = False
        self.q.save()

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(reverse('verifier_dashboard'))

        row = next(
            item for item in resp.context['org_data']
            if item['org'].id == self.org.id
        )
        self.assertIsNone(row['coverage'])

    def test_dashboard_coverage_counts_all_verifiers_not_just_viewer(self):
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v1, criterion=self.crit_a1, score=3)
        VerifierResponse.objects.create(
            questionnaire=self.q, verifier=self.v2, criterion=self.crit_b1, score=5)

        self.client.login(username='cov_v1', password='Pass@123')
        resp = self.client.get(reverse('verifier_dashboard'))

        row = next(
            item for item in resp.context['org_data']
            if item['org'].id == self.org.id
        )
        self.assertEqual(row['coverage'], (2, 4))
