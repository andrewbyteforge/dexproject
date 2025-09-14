"""
URL configuration for dexproject project.

Updated to include dashboard app URLs and provide proper routing
for the Phase 2 dashboard interface.

File: dexproject/urls.py
"""

from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # Dashboard app (main interface)
    path('dashboard/', include('dashboard.urls')),
    
    # API endpoints (future expansion)
    path('api/trading/', include('trading.urls')),
    path('api/risk/', include('risk.urls')), 
    path('api/wallet/', include('wallet.urls')),
    path('api/analytics/', include('analytics.urls')),
    
    # Root redirect to dashboard
    path('', lambda request: redirect('dashboard:home')),
]

# Customize admin site
admin.site.site_header = 'DEX Trading Bot Administration'
admin.site.site_title = 'DEX Trading Bot Admin'
admin.site.index_title = 'Trading Bot Management'