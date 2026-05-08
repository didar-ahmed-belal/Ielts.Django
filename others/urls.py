from django.urls import path
from .views import *

urlpatterns = [
    path('blogs/', BlogListView.as_view(), name='blog_list'),
    path('blog/<int:id>/', BlogDetailView.as_view(), name='blog_detail'),
    path('dashboard/', DashBoardView.as_view(), name='dashboard'),
    path('contact/', ContactView.as_view(), name='contact'),
    path('message/', MessagesView.as_view(), name='message'),
    path('faq/', FAQView.as_view(), name='faq'),
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('feedback/<uuid:result_id>/', DetailedFeedbackView.as_view(), name='detailed_feedback'),
    path('report/<uuid:result_id>/', DownloadReportView.as_view(), name='download_report'),
    path('ai-feedback/<uuid:result_id>/', AIFeedbackView.as_view(), name='ai_feedback'),
    path('home-data/', HomeData.as_view(), name='home_data'),
]