import os, re
from collections import OrderedDict

from django.apps import apps
from django.contrib.staticfiles import utils
from django.core.files.storage import FileSystemStorage

from django.contrib.staticfiles.finders import BaseFinder, searched_locations


class FileNameRegexAppDirectoriesFinder(BaseFinder):
    """
    A static files finder that looks in the directory of each app as
    specified in the source_dir attribute.
    """
    storage_class = FileSystemStorage
    source_dir = 'static'

    def __init__(self, app_names=None, *args, **kwargs):
        # The list of apps that are handled
        self.apps = []
        # Mapping of app names to storage instances
        self.storages = OrderedDict()
        app_configs = apps.get_app_configs()
        if app_names:
            app_names = set(app_names)
            app_configs = [ac for ac in app_configs if ac.name in app_names]
        for app_config in app_configs:
            app_storage = self.storage_class(
                os.path.join(app_config.path, self.source_dir))
            if os.path.isdir(app_storage.location):
                self.storages[app_config.name] = app_storage
                if app_config.name not in self.apps:
                    self.apps.append(app_config.name)
        super().__init__(*args, **kwargs)

    def list(self, ignore_patterns):
        """
        List all files in all app storages.
        """
        for storage in self.storages.values():
            if storage.exists(''):  # check if storage location exists
                for path in utils.get_files(storage, ignore_patterns):
                    yield path, storage

    def find(self, regex, all=False):
        """
        Look for files in the app directories.
        """
        matches = []
        file_regex = None
        try:
            file_regex = re.compile(regex)
        except:
            return matches
        for app in self.apps:
            app_location = self.storages[app].location
            if app_location not in searched_locations:
                searched_locations.append(app_location)
            app_matches = self.find_in_app(app, file_regex)
            if len(app_matches) != 0:
                if not all:
                    return app_matches[0]
                matches.extend(app_matches)
        return matches

    def find_in_app(self, app, file_regex):
        """
        Find a requested static file in an app's static locations.
        """
        matches = []
        storage = self.storages.get(app)
        if storage:
            # walk through directory to find files that match the regex
            for d, dirs, files in os.walk(storage.base_location):
                for f in files:
                    if file_regex.match(f) is not None:
                        matches.append(os.path.join(d, f))
        return matches
