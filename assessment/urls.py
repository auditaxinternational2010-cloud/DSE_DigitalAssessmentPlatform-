from django.urls import path
from . import views

urlpatterns = [
    # Admin
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('cycles/', views.cycle_list, name='cycle_list'),
    path('cycles/create/', views.cycle_create, name='cycle_create'),
    path('cycles/<int:pk>/', views.cycle_detail, name='cycle_detail'),
    path('cycles/<int:pk>/toggle-open/', views.cycle_toggle_open, name='cycle_toggle_open'),
    path('cycles/<int:pk>/add-org/', views.cycle_add_org_questionnaire, name='cycle_add_org'),
    path('cycles/<int:pk>/results/', views.cycle_results, name='cycle_results'),
    path('cycles/<int:pk>/org-report/<int:q_pk>/', views.org_report, name='org_report'),
    path('cycles/<int:pk>/export/excel/', views.export_cycle_excel, name='export_cycle_excel'),
    path('cycles/<int:pk>/org-report/<int:q_pk>/export/excel/', views.export_org_excel, name='export_org_excel'),
    path('cycles/<int:pk>/org-report/<int:q_pk>/export/pdf/', views.export_org_pdf, name='export_org_pdf'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    # Member
    path('member/dashboard/', views.member_dashboard, name='member_dashboard'),
    path('member/questionnaire/', views.member_questionnaire_redirect, name='member_questionnaire'),
    path('questionnaires/<int:pk>/fill/', views.questionnaire_fill, name='questionnaire_fill'),
    path('questionnaires/<int:pk>/save-category/', views.save_category, name='save_category'),
    path('questionnaires/<int:pk>/submit/', views.questionnaire_submit, name='questionnaire_submit'),
    path('questionnaires/<int:pk>/submitted/', views.questionnaire_submitted, name='questionnaire_submitted'),
    # Verifier
    path('verifier/dashboard/', views.verifier_dashboard, name='verifier_dashboard'),
    path('verify/<int:pk>/', views.verify_questionnaire, name='verify_questionnaire'),
    # Judges
    path('judges/dashboard/', views.judges_dashboard, name='judges_dashboard'),
    path('judge/<int:pk>/', views.judge_questionnaire, name='judge_questionnaire'),
    # Evidence
    path('evidence/link/', views.evidence_link, name='evidence_link'),
    path('evidence/unlink/<int:link_pk>/', views.evidence_unlink, name='evidence_unlink'),
    path('evidence/upload/', views.evidence_upload_ajax, name='evidence_upload_ajax'),
    # Library
    path('library/', views.library_list, name='library_list'),
    path('library/doc/<int:doc_pk>/file/', views.document_file, name='document_file'),
    path('library/search/', views.library_search, name='library_search'),
    # Reports
    path('reports/', views.reports_list, name='reports_list'),
    path('reports/<int:cycle_pk>/', views.reports_cycle, name='reports_cycle'),
    path('reports/<int:cycle_pk>/distribute/<int:q_pk>/', views.report_distribute, name='report_distribute'),
    path('reports/<int:cycle_pk>/distribute-all/', views.report_distribute_all, name='report_distribute_all'),
    path('reports/<int:cycle_pk>/revoke/<int:q_pk>/', views.report_revoke, name='report_revoke'),
]
