from django.shortcuts import render
from django.views.generic.base import TemplateView
from django.conf import settings

from django.contrib.staticfiles.finders import find
import re

class IndexView(TemplateView):
    
    template_name = "configuration/index.html"
    
    def _get_angular_files(self, context):
        # check to see if we've got production static files with a hash in them
        hash_regex = re.compile(r'\.([a-zA-Z0-9]{20})\.bundle\.(js|css)$')
        inline_file_path = find(r'^inline(\.[a-zA-Z0-9]{20})?\.bundle\.js$')

        is_production_static_files = hash_regex.search(inline_file_path) is not None
        context["is_production_static_files"] = is_production_static_files
        scripts = {}
        if is_production_static_files:
            scripts["inline"] = "configuration/dist/inline." + hash_regex.search(inline_file_path).group(1) + ".bundle.js"
            scripts["main"] = "configuration/dist/main." + hash_regex.search(find(r'^main(\.[a-zA-Z0-9]{20})?\.bundle\.js$')).group(1) + ".bundle.js"
            scripts["polyfills"] = "configuration/dist/polyfills." + hash_regex.search(find(r'^polyfills(\.[a-zA-Z0-9]{20})?\.bundle\.js$')).group(1) + ".bundle.js"
            scripts["styles"] =  "configuration/dist/styles." + hash_regex.search(find(r'^styles(\.[a-zA-Z0-9]{20})?\.bundle\.(js|css)$')).group(1) + ".bundle.css"
        else:
            scripts['inline'] = "configuration/dist/inline.bundle.js"
            scripts['main'] = "configuration/dist/main.bundle.js"
            scripts['polyfills'] = "configuration/dist/polyfills.bundle.js"
            scripts['styles'] = "configuration/dist/styles.bundle.js"
            scripts['vendor'] = "configuration/dist/vendor.bundle.js"
        
        context["scripts"] = scripts
        

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self._get_angular_files(context)
        return context
