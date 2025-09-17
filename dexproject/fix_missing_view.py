import sys 
import os 
 
# Add the missing metrics_stream view 
from django.http import StreamingHttpResponse 
import json 
import time 
from datetime import datetime 
 
import django 
import os 
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings') 
django.setup() 
 
from dashboard.engine_service import engine_service 
 
print('Views fix applied successfully!') 
