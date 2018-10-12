import os
import re
import time
from collections import namedtuple
from datetime import datetime
from enum import Enum
from html import unescape
from queue import Queue
from threading import Thread
from uuid import uuid4

import django
import requests
from lxml import etree

# need to set up Django before importing the models otherwise the database
# connection will not be properly initiated
# could probably do this another way, but I'm lazy
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "omnimusesite.settings")
django.setup()

from configuration.models import Mapping, LastfmArtistProcessQueueItem, LastfmUserProcessQueueItem

SpotifyMapping = namedtuple('SpotifyMapping', ['spotify_id', 'spotify_url', 'track_name', 'last_fm_track_url', 'artist_name', 'last_fm_artist_url'])
ArtistInfo = namedtuple('ArtistInfo', ['name', 'last_fm_artist_url'])

class FileTypes(Enum):
    TRACK_PAGE = 1
    USER_LIB_ARTIST_PAGE = 2

class LastfmHTMLProcessor():

    def _parse_spotify_info_from_element(self, element):
        # parse each element
        try:
            spotify_id = element.attrib['data-spotify-id']
            spotify_url = element.attrib['data-spotify-url']
            track_name = element.attrib['data-track-name']
            last_fm_track_url = element.attrib['data-track-url']
            artist_name = element.attrib['data-artist-name']
            last_fm_artist_url = element.attrib['data-artist-url']
            return True, SpotifyMapping(spotify_id, spotify_url, track_name, last_fm_track_url, artist_name, last_fm_artist_url)
        except:
            return False, None

    def _parse_artist_info_from_element(self, element):
        try:
            name = unescape(element.text)
            last_fm_artist_url = element.attrib['href']
            return True, ArtistInfo(name, last_fm_artist_url)
        except:
            return False, None

    def parse_track_page(self, html):
        tree = etree.HTML(html)
        results = tree.xpath('//a[contains(@class, "chartlist-play-button")]')
        for result in results:
            success, parsed_result = self._parse_spotify_info_from_element(result)
            if not success:
                continue
            yield parsed_result

    def parse_user_library_artist_page(self, html):
        tree = etree.HTML(html)
        results = tree.xpath('//a[@class="link-block-target"]')
        for result in results:
            success, parsed_result = self._parse_artist_info_from_element(result)
            if not success:
                continue
            yield parsed_result

class LastfmHTMLCacheManager():

    def __init__(self):
        # file paths for files to process
        self.cache_file_paths = Queue()
        # folder for caching downloaded html files
        self.cache_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lastfm-cache')

        # separate folders for each 
        self.track_page_folder = os.path.join(self.cache_folder, 'tracks')
        self.user_lib_artist_page_folder = os.path.join(self.cache_folder, 'user-lib-artist')
        
        # if the cache folder exists, then load existing cache files
        if os.path.exists(self.cache_folder):
            self._refresh_files()
        else:
            os.makedirs(self.cache_folder)
            os.makedirs(self.track_page_folder)
            os.makedirs(self.user_lib_artist_page_folder)
    
    def _refresh_files(self):
        # clear queue
        with self.cache_file_paths.mutex:
            self.cache_file_paths.queue.clear()
        
        # only get html files
        track_files_to_add = [f for f in os.listdir(self.track_page_folder) if os.path.isfile(os.path.join(self.track_page_folder, f)) and f.endswith('.html')]
        user_lib_art_files_to_add = [f for f in os.listdir(self.user_lib_artist_page_folder) if os.path.isfile(os.path.join(self.user_lib_artist_page_folder, f)) and f.endswith('.html')]
        
        # add track files
        for file_name in track_files_to_add:
            self.cache_file_paths.put((FileTypes.TRACK_PAGE, os.path.join(self.track_page_folder, file_name)))

        # add user library artist files
        for file_name in user_lib_art_files_to_add:
            self.cache_file_paths.put((FileTypes.USER_LIB_ARTIST_PAGE, os.path.join(self.user_lib_artist_page_folder, file_name)))
    
    def save_html(self, html, file_type, file_name=None):
        if file_name is None:
            file_name = uuid4().hex
        
        save_folder = None
        if file_type == FileTypes.TRACK_PAGE:
            save_folder = self.track_page_folder
        elif file_type == FileTypes.USER_LIB_ARTIST_PAGE:
            save_folder = self.user_lib_artist_page_folder
        
        # if we aren't given a valid file type then return as we won't know how to process it later
        if save_folder is None:
            return

        file_path = os.path.join(save_folder, re.sub(r"[<>:\"\/\\\|\?\*]", "", file_name) + ".html")

        # only write to file if it doesn't already exist
        if os.path.exists(file_path):
            return

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        self.cache_file_paths.put((file_path, file_name))

    def get_html(self, type):
        # only get something if the queue is not empty
        if self.cache_file_paths.empty():
            return None, None
        
        file_type, file_path = self.cache_file_paths.get()

        with open(file_path, 'r', encoding='utf-8') as f:
            file_contents = f.read()
        
        # delete file
        os.remove(file_path)

        # return file_type and html content
        return file_type, file_contents

class LastfmHTMLProcessorThread(Thread):

    def __init__(self, cache):
        super().__init__()
        self.cache = cache # this is a LastfmHTMLCacheManager
        self.processor = LastfmHTMLProcessor()
        self.stop = False

    def _process_track_html(self, html):
        track_mappings = self.processor.parse_track_page(html)
        for track_mapping in track_mappings:
            # check for existing results
            query = Mapping.objects.filter(spotify_id=track_mapping.spotify_id)
            if len(query) > 0:
                # take the first result and update that. Hopefully we should never end up with more than one
                mapping_to_update = query[0]
                mapping_to_update.spotify_url = track_mapping.spotify_url
                mapping_to_update.track_name = track_mapping.track_name
                mapping_to_update.last_fm_track_url = track_mapping.last_fm_track_url
                mapping_to_update.artist_name = track_mapping.artist_name
                mapping_to_update.last_fm_artist_url = track_mapping.last_fm_artist_url
                mapping_to_update.last_updated = datetime.now()
                mapping_to_update.manually_mapped = False
                mapping_to_update.save()
                continue
            
            # if it doesn't exist, create a new mapping and save it
            mapping = Mapping(
                spotify_id = track_mapping.spotify_id,
                spotify_url = track_mapping.spotify_url,
                track_name = track_mapping.track_name,
                last_fm_track_url = track_mapping.last_fm_track_url,
                artist_name = track_mapping.artist_name,
                last_fm_artist_url = track_mapping.last_fm_artist_url,
                last_updated = datetime.now(),
                manually_mapped = False
            )
            mapping.save()


    def _process_user_lib_artist_html(self, html):
        artists = self.processor.parse_user_library_artist_page(html)
        for artist in artists:
            # check for existing artists in the queue
            query = LastfmArtistProcessQueueItem.objects.filter(name=artist.name)
            # if it's already in the queue, no need to add it again
            if len(query) > 0:
                # todo: add re-processing if it hasn't been updated in a while (say 2 months or something)
                continue
            queue_item = LastfmArtistProcessQueueItem(
                name = artist.name,
                last_fm_artist_url = artist.last_fm_artist_url,
                processed = False
            )
            queue_item.save()

    def run(self):
        while not self.stop:
            file_type, html = self.cache.get_html()
            if file_type is not None and html is not None:
                if file_type == FileTypes.TRACK_PAGE:
                    self._process_track_html(html)
                elif file_type == FileTypes.USER_LIB_ARTIST_PAGE:
                    self._process_user_lib_artist_html(html)
            time.sleep(30)
    
    def stop_process(self):
        self.stop = True

class LastfmHTMLDownloader(Thread):

    def __init__(self, html_cache_manager):
        super().__init__()
        self.html_cache_manager = html_cache_manager
        self.stop = False
    
    def _download_artist_track_pages(self, artist_name):
        # only take the first 10 pages of an artist, as we're unlikely to get much after this
        for i in range(1, 11):
            request = self.session.get("https://www.last.fm/music/{0}/+tracks?page={1}".format(artist_name, i))
            # if the request failed, or it redirected to a different track page, then break out of this loop
            if (request.status_code != 200 or len(request.history) > 0 and request.history[0].status_code == 302):
                break
            
            # save page
            self.html_cache_manager.save_html(request.text, FileTypes.TRACK_PAGE)
        
        # after saving all the pages, mark the artist as processed
        # (technically it may not be fully processed, but it will definitely be soon)
        artist_queue_item = LastfmArtistProcessQueueItem.objects.get(name=artist_name)
        artist_queue_item.processed = True
        artist_queue_item.processed_date = datetime.now()
        artist_queue_item.save()
    
    def _download_user_lib_artist_pages(self, user_name):
        page = 1
        while True:
            request = self.session.get("https://www.last.fm/user/{0}/library/artists?page={1}".format(user_name, page))
            if request.status_code != 200 or len(request.history) > 0 and request.history[0].status_code == 302:
                # either a bad request or we've reached the end of the users artist library pages
                break

            # save page
            self.html_cache_manager.save_html(request.text, FileTypes.USER_LIB_ARTIST_PAGE)
        
        # todo: get followers

        # after saving all the user library artist pages, mark the user as processed
        user_queue_item = LastfmUserProcessQueueItem.objects.filter(name=user_name)
        user_queue_item.processed = True
        user_queue_item.processed_date = datetime.now()
        user_queue_item.save()


    def setup_last_fm_session(self, user_name, password):
        self.session = requests.session()
        # grab the login page and process it to get the csrf token needed for logging in
        login_page = self.session.get('https://secure.last.fm/login')
        login_page_tree = etree.HTML(login_page.text)
        csrfmiddlewaretoken = login_page_tree.xpath('//input[@name="csrfmiddlewaretoken"]')[0].attrib['value']

        # set the headers and data for the login request
        headers = {'content-type': 'application/x-www-form-urlencoded', 'referer': 'https://secure.last.fm/login'}
        data = {'username': user_name, 'password': password, 'submit': '', 'csrfmiddlewaretoken': csrfmiddlewaretoken}

        # send off the login request. Don't need to process the response, all we care about
        # is the cookies that this request sets
        self.session.post('https://secure.last.fm/login', data=data, headers=headers)


    def run(self):
        while not self.stop:
            # process artist
            artist_to_process = LastfmArtistProcessQueueItem.objects.filter(processed=False).first()
            if artist_to_process is not None:
                self._download_artist_track_pages(artist_to_process.name)

            # process user
            user_to_process = LastfmUserProcessQueueItem.objects.filter(processed=False).first()
            if user_to_process is not None:
                self._download_user_lib_artist_pages(user_to_process.name)

            time.sleep(5)
    
    def stop_process(self):
        self.stop = True

class MappingsManager():

    def __init__(self):
        self.html_cache_manager = LastfmHTMLCacheManager()
        self.downloader = LastfmHTMLDownloader(self.html_cache_manager)
        self.processing_threads = []
