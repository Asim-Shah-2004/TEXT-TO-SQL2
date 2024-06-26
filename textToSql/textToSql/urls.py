from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from .views import addDataSource, queryDataSource ,querydatasourceOpenAi ,querydatasourceGemini

urlpatterns = [
    path('admin/', admin.site.urls),
    path('home/', TemplateView.as_view(template_name='dashboard/home.html'), name='home'),
    path('accounts/', include('allauth.urls')),
    path('addDataSource/', addDataSource, name='add_data_source'),
    path('queryDataSource/', queryDataSource, name='query_data_source'),
    path('queryDataSourceOpenAI/',querydatasourceOpenAi,name='query_data_source_openAI'),
    path('querydatasourceGemini/',querydatasourceGemini,name='query_data_source_Gemini')
]
