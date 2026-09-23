from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    UserProfile,
    Organization,
    VerifierAssignment,
)

from assessment.models import (
    AwardCycle,
    AssessmentCategory,
    Criterion,
    LevelIndicator,
    Questionnaire,
    Response,
    VerifierResponse,
)


User = get_user_model()


class Command(BaseCommand):
    help = "Seed complete test data for the Judge workflow."

    @transaction.atomic
    def handle(self, *args, **options):

        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "Creating Judge workflow test data..."
            )
        )

        # ============================================================
        # 1. USERS
        # ============================================================

        admin = self.create_user(
            username="test_admin",
            email="testadmin@example.com",
            password="TestAdmin123!",
        )

        verifier = self.create_user(
            username="test_verifier",
            email="testverifier@example.com",
            password="TestVerifier123!",
        )

        judge = self.create_user(
            username="test_judge",
            email="testjudge@example.com",
            password="TestJudge123!",
        )

        member_judged = self.create_user(
            username="test_member_judged",
            email="member.judged@example.com",
            password="TestMember123!",
        )

        member_normal = self.create_user(
            username="test_member_normal",
            email="member.normal@example.com",
            password="TestMember123!",
        )

        # ============================================================
        # 2. ORGANIZATIONS
        # ============================================================

        judging_org, _ = Organization.objects.get_or_create(
            name="TEST - Organization Requiring Judging",
            defaults={
                "description": "Test organization for Judge workflow.",
                "org_type": "professional_services",
                "region": "Dar es Salaam",
                "physical_address": "Test Address",
                "postal_address": "00000",
                "num_employees": "5_49",
                "investment_capital": "5m_to_200m",
                "is_active": True,
                "requires_judging": True,
            },
        )

        # Make sure the workflow flag is correct even if the record
        # already existed.
        judging_org.requires_judging = True
        judging_org.is_active = True
        judging_org.save()

        normal_org, _ = Organization.objects.get_or_create(
            name="TEST - Normal Organization",
            defaults={
                "description": "Test organization for normal workflow.",
                "org_type": "professional_services",
                "region": "Dar es Salaam",
                "physical_address": "Test Address",
                "postal_address": "00000",
                "num_employees": "5_49",
                "investment_capital": "5m_to_200m",
                "is_active": True,
                "requires_judging": False,
            },
        )

        normal_org.requires_judging = False
        normal_org.is_active = True
        normal_org.save()

        # ============================================================
        # 3. USER PROFILES
        # ============================================================

        self.create_profile(
            admin,
            role="admin",
            organization=None,
        )

        self.create_profile(
            verifier,
            role="verifier",
            organization=None,
        )

        self.create_profile(
            judge,
            role="judge",
            organization=None,
        )

        self.create_profile(
            member_judged,
            role="member",
            organization=judging_org,
        )

        self.create_profile(
            member_normal,
            role="member",
            organization=normal_org,
        )

        # ============================================================
        # 4. VERIFIER ASSIGNMENTS
        # ============================================================

        VerifierAssignment.objects.get_or_create(
            verifier=verifier,
            organization=judging_org,
        )

        VerifierAssignment.objects.get_or_create(
            verifier=verifier,
            organization=normal_org,
        )

        # ============================================================
        # 5. AWARD CYCLE
        # ============================================================

        cycle, _ = AwardCycle.objects.get_or_create(
            year=timezone.now().year,
            defaults={
                "name": f"TEST Judge Workflow {timezone.now().year}",
                "is_open": True,
            },
        )

        cycle.name = f"TEST Judge Workflow {cycle.year}"
        cycle.is_open = True
        cycle.save()

        # ============================================================
        # 6. CATEGORIES
        # ============================================================

        category, _ = AssessmentCategory.objects.get_or_create(
            cycle=cycle,
            name="TEST - Business Performance",
            defaults={
                "description": "Test category for Judge workflow.",
                "order": 1,
                "is_active": True,
                "is_informal_sector_only": False,
            },
        )

        category.is_active = True
        category.is_informal_sector_only = False
        category.save()

        # ============================================================
        # 7. CRITERIA
        # ============================================================

        criteria = []

        criterion_data = [
            (
                "1",
                "Business Strategy",
                "The organization has a clear business strategy.",
            ),
            (
                "2",
                "Financial Management",
                "The organization demonstrates good financial management.",
            ),
            (
                "3",
                "Customer Management",
                "The organization effectively manages customers.",
            ),
            (
                "4",
                "Innovation",
                "The organization demonstrates innovation.",
            ),
            (
                "5",
                "Human Resources",
                "The organization manages its employees effectively.",
            ),
        ]

        for number, name, description in criterion_data:

            criterion, _ = Criterion.objects.get_or_create(
                category=category,
                number=number,
                defaults={
                    "name": name,
                    "description": description,
                    "order": int(number),
                    "is_active": True,
                    "is_numeric": False,
                    "numeric_fields": [],
                },
            )

            criterion.name = name
            criterion.description = description
            criterion.order = int(number)
            criterion.is_active = True
            criterion.is_numeric = False
            criterion.numeric_fields = []
            criterion.save()

            criteria.append(criterion)

            # ========================================================
            # 8. LEVEL INDICATORS
            # ========================================================

            for level in range(1, 6):

                LevelIndicator.objects.get_or_create(
                    criterion=criterion,
                    level=level,
                    defaults={
                        "indicator": (
                            f"Level {level} indicator for {name}."
                        )
                    },
                )

        # ============================================================
        # 9. QUESTIONNAIRES
        # ============================================================

        judging_q, _ = Questionnaire.objects.get_or_create(
            cycle=cycle,
            organization=judging_org,
        )

        normal_q, _ = Questionnaire.objects.get_or_create(
            cycle=cycle,
            organization=normal_org,
        )

        # The member has submitted both questionnaires.
        judging_q.is_submitted = True
        judging_q.submitted_at = timezone.now()
        judging_q.is_distributed = False
        judging_q.distributed_at = None
        judging_q.distributed_by = None

        # VERY IMPORTANT:
        # The Judge test starts BEFORE judging is completed.
        judging_q.judging_completed = False
        judging_q.judged_at = None
        judging_q.judged_by = None

        judging_q.save()

        normal_q.is_submitted = False
        normal_q.submitted_at = timezone.now()
        normal_q.is_distributed = False
        normal_q.distributed_at = None
        normal_q.distributed_by = None
        normal_q.save()

        # ============================================================
        # 10. MEMBER RESPONSES
        # ============================================================

        for index, criterion in enumerate(criteria, start=1):

            Response.objects.update_or_create(
                questionnaire=judging_q,
                criterion=criterion,
                defaults={
                    "score": min(index, 5),
                    "notes": (
                        f"Member test response for {criterion.name}."
                    ),
                    "numeric_data": {},
                },
            )

            Response.objects.update_or_create(
                questionnaire=normal_q,
                criterion=criterion,
                defaults={
                    "score": min(index, 5),
                    "notes": (
                        f"Member test response for {criterion.name}."
                    ),
                    "numeric_data": {},
                },
            )

        # ============================================================
        # 11. VERIFIER RESPONSES
        # ============================================================

        # This is what makes the judging organization READY.
        # Every applicable criterion receives a verifier response.

        for index, criterion in enumerate(criteria, start=1):

            VerifierResponse.objects.update_or_create(
                questionnaire=judging_q,
                verifier=verifier,
                criterion=criterion,
                defaults={
                    "score": max(1, 5 - index % 3),
                    "notes": (
                        f"Verifier completed verification for "
                        f"{criterion.name}."
                    ),
                },
            )

            VerifierResponse.objects.update_or_create(
                questionnaire=normal_q,
                verifier=verifier,
                criterion=criterion,
                defaults={
                    "score": max(1, 5 - index % 3),
                    "notes": (
                        f"Verifier completed verification for "
                        f"{criterion.name}."
                    ),
                },
            )

        # ============================================================
        # 12. SUMMARY
        # ============================================================

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("========================================"))
        self.stdout.write(self.style.SUCCESS("JUDGE TEST DATA CREATED"))
        self.stdout.write(self.style.SUCCESS("========================================"))

        self.stdout.write("")
        self.stdout.write("USERS")
        self.stdout.write(f"Admin:       test_admin / TestAdmin123!")
        self.stdout.write(f"Verifier:    test_verifier / TestVerifier123!")
        self.stdout.write(f"Judge:       test_judge / TestJudge123!")
        self.stdout.write(f"Member:      test_member_judged / TestMember123!")
        self.stdout.write(f"Member:      test_member_normal / TestMember123!")

        self.stdout.write("")
        self.stdout.write("ORGANIZATIONS")
        self.stdout.write(
            f"Judging:     {judging_org.name} "
            f"(requires_judging=True)"
        )
        self.stdout.write(
            f"Normal:      {normal_org.name} "
            f"(requires_judging=False)"
        )

        self.stdout.write("")
        self.stdout.write("CYCLE")
        self.stdout.write(f"{cycle.name} (OPEN)")

        self.stdout.write("")
        self.stdout.write("JUDGE DASHBOARD")
        self.stdout.write("/judges/dashboard/")

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "The judging organization is submitted and fully verified."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "It should therefore appear as READY on the Judge dashboard."
            )
        )

        self.stdout.write("")

    def create_user(self, username, email, password):

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_active": True,
            },
        )

        user.email = email
        user.is_active = True
        user.set_password(password)
        user.save()

        return user

    def create_profile(self, user, role, organization=None):

        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role": role,
                "organization": organization,
                "must_change_password": False,
                "phone_number": "",
            },
        )

        profile.role = role
        profile.organization = organization
        profile.must_change_password = False
        profile.save()

        return profile