from django.shortcuts import render
from django.views.generic.base import TemplateView
from django.conf import settings

from os import walk
import django.contrib.staticfiles.templatetags

class IndexView(TemplateView):
    
    template_name = "configuration/index.html"
    
    def _get_angular_files(self, context):
        foo = django.contrib.staticfiles.finders.find('configuration/dist/inline.bundle.js')
        
        # for d, dirs, f in walk(settings.STATIC_ROOT):
        #     print(d)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self._get_angular_files(context)
        return context
