from django.shortcuts import render
from django.views.generic.base import TemplateView
from django.conf import settings

from django.contrib.staticfiles.finders import find
import re

class IndexView(TemplateView):
    
    template_name = "configuration/index.html"
    
    def _get_angular_files(self, context):
        # check to see if we've got production static files with a hash in them
        hash_regex = re.compile(r'\.([a-zA-Z0-9]{20})\.(js|css)$')
        runtime_file_path = find(('configuration', r'^runtime(\.[a-zA-Z0-9]{20})?\.js$'))

        is_production_static_files = hash_regex.search(runtime_file_path) is not None
        context["is_production_static_files"] = is_production_static_files
        scripts = {}
        if is_production_static_files:
            scripts["runtime"] = "configuration/dist/runtime." + hash_regex.search(runtime_file_path).group(1) + ".js"
            scripts["main"] = "configuration/dist/main." + hash_regex.search(find(('configuration', r'^main(\.[a-zA-Z0-9]{20})?\.js$'))).group(1) + ".js"
            scripts["polyfills"] = "configuration/dist/polyfills." + hash_regex.search(find(('configuration', r'^polyfills(\.[a-zA-Z0-9]{20})?\.js$'))).group(1) + ".js"
            scripts["styles"] =  "configuration/dist/styles." + hash_regex.search(find(('configuration', r'^styles(\.[a-zA-Z0-9]{20})?\.(js|css)$'))).group(1) + ".css"
        else:
            scripts['runtime'] = "configuration/dist/runtime.js"
            scripts['main'] = "configuration/dist/main.js"
            scripts['polyfills'] = "configuration/dist/polyfills.js"
            scripts['styles'] = "configuration/dist/styles.js"
            scripts['vendor'] = "configuration/dist/vendor.js"
        
        context["scripts"] = scripts
        

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self._get_angular_files(context)
        return context
