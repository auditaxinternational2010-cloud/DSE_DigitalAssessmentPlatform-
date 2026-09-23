from django.db import models
from django.contrib.auth.models import User


ORG_TYPE_SUBTYPES = {
    'public_administration': [
        ('ministries', 'Ministries'),
        ('local_government_authorities', 'Local government authorities'),
        ('public_agencies_regulatory', 'Public agencies and regulatory bodies'),
        ('other', 'Other'),
    ],
    'mining_extraction': [
        ('gold_mining', 'Gold mining'),
        ('tanzanite_gemstones', 'Tanzanite and gemstones'),
        ('coal', 'Coal'),
        ('natural_gas', 'Natural gas'),
        ('quarrying', 'Quarrying activities'),
        ('other', 'Other'),
    ],
    'manufacturing': [
        ('food_beverage_processing', 'Food and beverage processing'),
        ('textiles_garments', 'Textiles and garments'),
        ('cement_construction_materials', 'Cement and construction materials'),
        ('chemicals_pharmaceuticals', 'Chemicals and pharmaceuticals'),
        ('metal_plastic_products', 'Metal and plastic products'),
        ('other', 'Other'),
    ],
    'financial_services': [
        ('banking', 'Banking'),
        ('microfinance', 'Microfinance'),
        ('capital_markets', 'Capital markets'),
        ('fintech_services', 'Fintech services'),
        ('other', 'Other'),
    ],
    'insurance': [
        ('health', 'Health'),
        ('properties', 'Properties'),
        ('other', 'Other'),
    ],
    'tourism_hospitality': [
        ('hotels_lodges', 'Hotels and lodges'),
        ('tour_operations', 'Tour operations'),
        ('travel_agencies', 'Travel agencies'),
        ('cultural_wildlife_tourism', 'Cultural and wildlife tourism'),
        ('other', 'Other'),
    ],
    'transportation_logistics': [
        ('road_transport', 'Road transport'),
        ('railways', 'Railways'),
        ('aviation', 'Aviation'),
        ('maritime_ports', 'Maritime and ports'),
        ('warehousing_logistics', 'Warehousing and logistics'),
        ('other', 'Other'),
    ],
    'ict': [
        ('telecommunications', 'Telecommunications'),
        ('internet_services', 'Internet services'),
        ('software_digital_services', 'Software and digital services'),
        ('media_broadcasting', 'Media and broadcasting'),
        ('other', 'Other'),
    ],
    'health_social': [
        ('hospitals_clinics', 'Hospitals and clinics'),
        ('pharmaceuticals', 'Pharmaceuticals'),
        ('social_welfare_services', 'Social welfare services'),
        ('other', 'Other'),
    ],
    'education_vocational': [
        ('schools', 'Schools'),
        ('universities', 'Universities'),
        ('vocational_training', 'Vocational training'),
        ('research_institutions', 'Research institutions'),
        ('other', 'Other'),
    ],
    'construction': [
        ('building_construction', 'Building construction'),
        ('roads_bridges', 'Roads and bridges'),
        ('real_estate_development', 'Real estate development'),
        ('infrastructure_projects', 'Infrastructure projects'),
        ('other', 'Other'),
    ],
    'real_estate_property': [
        ('property_development', 'Property development'),
        ('property_management', 'Property management'),
        ('real_estate_brokerage', 'Real estate brokerage'),
        ('other', 'Other'),
    ],
    'energy': [
        ('electricity_generation_distribution', 'Electricity generation and distribution'),
        ('oil_gas', 'Oil and gas'),
        ('water_supply_sanitation', 'Water supply and sanitation'),
        ('renewable_energy', 'Renewable energy'),
        ('other', 'Other'),
    ],
    'ngos': [
        ('international_ngos', 'International NGOs'),
        ('local_ngos', 'Local NGOs'),
        ('development_programs_donor_funded', 'Development programs and donor-funded projects'),
        ('other', 'Other'),
    ],
    'agriculture_agribusiness': [
        ('crop_farming', 'Crop farming'),
        ('livestock', 'Livestock'),
        ('forestry', 'Forestry'),
        ('fishing_aquaculture', 'Fishing and aquaculture'),
        ('other', 'Other'),
    ],
    'trade_commerce': [
        ('wholesale_trade', 'Wholesale trade'),
        ('retail_trade', 'Retail trade'),
        ('import_export', 'Import and export businesses'),
        ('other', 'Other'),
    ],
    'professional_services': [
        ('legal_services', 'Legal services'),
        ('audit_accounting', 'Audit and accounting'),
        ('consulting', 'Consulting'),
        ('human_resource_services', 'Human resource services'),
        ('advertising_marketing', 'Advertising and marketing'),
        ('architectural_engineering', 'Architectural and engineering activities, technical testing and analysis'),
        ('scientific_research', 'Scientific research and development'),
        ('photographic_activities', 'Photographic activities'),
        ('security_systems', 'Security systems service activities'),
        ('other', 'Other'),
    ],
    'sports_recreation_creative': [
        ('sports_clubs', 'Sports clubs'),
        ('fitness_wellness', 'Fitness and wellness'),
        ('event_recreation_services', 'Event and recreation services'),
        ('music_entertainment', 'Music and entertainment'),
        ('film_media_production', 'Film and media production'),
        ('fashion_design', 'Fashion and design'),
        ('arts_crafts', 'Arts and crafts'),
        ('other', 'Other'),
    ],
    'environmental_green': [
        ('waste_management', 'Waste management'),
        ('recycling', 'Recycling'),
        ('climate_carbon_projects', 'Climate and carbon projects'),
        ('environmental_conservation', 'Environmental conservation services'),
        ('other', 'Other'),
    ],
    'informal_sector': [],
}


class Organization(models.Model):
    ORG_TYPE_CHOICES = [
        ('public_administration', 'Public Administration and Government Services'),
        ('mining_extraction', 'Mining/Extraction'),
        ('manufacturing', 'Manufacturing Industries'),
        ('financial_services', 'Financial Services'),
        ('insurance', 'Insurance Services'),
        ('tourism_hospitality', 'Tourism and Hospitality'),
        ('transportation_logistics', 'Transportation, Logistics and Storage'),
        ('ict', 'Information Communication Technology'),
        ('health_social', 'Health and Social Services'),
        ('education_vocational', 'Education and Vocational Training'),
        ('construction', 'Construction and Land Development'),
        ('real_estate_property', 'Real Estate and Property Services'),
        ('energy', 'Energy'),
        ('ngos', 'NGOs'),
        ('agriculture_agribusiness', 'Agriculture & Agri Business'),
        ('trade_commerce', 'Trade and Commerce'),
        ('professional_services', 'Professional Services'),
        ('sports_recreation_creative', 'Sports, Recreation, Creative and Cultural Industries'),
        ('environmental_green', 'Environmental and Green Economy'),
        ('informal_sector', 'Informal Sector'),
    ]
    NUM_EMPLOYEES_CHOICES = [
        ('1_4', '1 – 4'),
        ('5_49', '5 – 49'),
        ('50_99', '50 – 99'),
        ('100_plus', '100+'),
    ]
    INVESTMENT_CAPITAL_CHOICES = [
        ('up_to_5m', 'Up to 5 Million'),
        ('5m_to_200m', '5 Million – 200 Million'),
        ('200m_to_800m', '200 Million – 800 Million'),
        ('above_800m', 'Above 800 Million'),
    ]

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    org_type = models.CharField(max_length=50, choices=ORG_TYPE_CHOICES, blank=True)
    org_subtype = models.CharField(max_length=100, blank=True)
    org_subtype_other = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=255, blank=True)
    physical_address = models.TextField(blank=True)
    postal_address = models.CharField(max_length=255, blank=True)
    num_employees = models.CharField(max_length=20, choices=NUM_EMPLOYEES_CHOICES, blank=True)
    investment_capital = models.CharField(max_length=50, choices=INVESTMENT_CAPITAL_CHOICES, blank=True)
    is_active = models.BooleanField(default=True)
    ASSESSMENT_PROFILE_CHOICES = [
        ('bond_issuer', 'Bond Issuer'),
        ('bond_trader', 'Bond Trader'),
        ('custodian', 'Custodian'),
        ('egm', 'EGM'),
        ('mims', 'MIMs'),
        ('nomads', 'NOMADs'),
        ('ldms', 'LDMs'),
    ]
    assessment_profile = models.CharField(
        max_length=30, choices=ASSESSMENT_PROFILE_CHOICES, blank=True,
        help_text='DSE assessment workbook profile used for this organisation.'
    )
    requires_judging = models.BooleanField(
        default=False,
        help_text='If enabled, this organization follows Member → Secretariat → Judges → Final Results.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_org_subtype_display(self):
        if not self.org_subtype:
            return ''
        if self.org_subtype == 'other':
            return self.org_subtype_other or 'Other'
        for slug, label in ORG_TYPE_SUBTYPES.get(self.org_type, []):
            if slug == self.org_subtype:
                return label
        return self.org_subtype

    @property
    def member(self):
        profile = self.member_profiles.filter(role='member').first()
        return profile.user if profile else None

    @property
    def verifiers(self):
        return [a.verifier for a in self.verifier_assignments.all()]


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('verifier', 'Secretariat'),
        ('judge', 'Judge'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='userprofile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    organization = models.ForeignKey(
        Organization,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='member_profiles',
    )
    must_change_password = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class VerifierAssignment(models.Model):
    verifier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verifier_assignments')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='verifier_assignments')

    class Meta:
        unique_together = ['verifier', 'organization']

    def __str__(self):
        return f"{self.verifier.username} → {self.organization.name}"


class ParticipationRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # Organization details
    org_name = models.CharField(max_length=255)
    org_type = models.CharField(max_length=50, choices=Organization.ORG_TYPE_CHOICES)
    org_subtype = models.CharField(max_length=100, blank=True)
    org_subtype_other = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=255)
    physical_address = models.TextField()
    postal_address = models.CharField(max_length=255)
    num_employees = models.CharField(max_length=20, choices=Organization.NUM_EMPLOYEES_CHOICES)
    investment_capital = models.CharField(max_length=50, choices=Organization.INVESTMENT_CAPITAL_CHOICES)

    # Respondent details
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    position = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30)
    email = models.EmailField()

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_requests',
    )

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.org_name} ({self.get_status_display()})"

    def get_org_subtype_display(self):
        if not self.org_subtype:
            return ''
        if self.org_subtype == 'other':
            return self.org_subtype_other or 'Other'
        for slug, label in ORG_TYPE_SUBTYPES.get(self.org_type, []):
            if slug == self.org_subtype:
                return label
        return self.org_subtype


class EmailLog(models.Model):
    """One row per send_mail() call — records the attempt, not delivery.

    A 'sent' status means the SMTP server accepted the message for relay. It
    does not prove the message reached the recipient's mailbox; proving that
    would require an ESP with delivery webhooks.
    """

    KIND_CHOICES = [
        ('welcome', 'Welcome email'),
        ('new_request', 'New request notification'),
        ('password_reset', 'Password reset'),
    ]
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    recipient = models.EmailField(max_length=254)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    error = models.TextField(blank=True)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='email_logs',
    )
    organization = models.ForeignKey(
        'Organization', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='email_logs',
    )
    triggered_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='emails_triggered',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['kind', 'status']),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} → {self.recipient} ({self.status})"
