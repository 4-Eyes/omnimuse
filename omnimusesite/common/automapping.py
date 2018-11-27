import json
import os
import re
import sys
from collections import namedtuple
from datetime import datetime
from enum import Enum
from html import unescape
from queue import Queue
from threading import Thread, Event
from uuid import uuid4

import django
import requests
from lxml import etree
from tzlocal import get_localzone

# append parent directory to python path so that we can import omnimusesite.settings
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))

# need to set up Django before importing the models otherwise the database
# connection will not be properly initiated
# could probably do this another way, but I'm lazy
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "omnimusesite.settings")
django.setup()

from configuration.models import (LastfmArtistProcessQueueItem,
                                  LastfmUserProcessQueueItem, Mapping)

SpotifyMapping = namedtuple('SpotifyMapping', ['spotify_id', 'spotify_url', 'track_name', 'last_fm_track_url', 'artist_name', 'last_fm_artist_url'])
ArtistInfo = namedtuple('ArtistInfo', ['name', 'last_fm_artist_url'])
UserInfo = namedtuple('UserInfo', ['name', 'last_fm_user_url'])

class FileTypes(Enum):
    TRACK_PAGE = 1
    USER_LIB_ARTIST_PAGE = 2
    USER_FOLLOWERS_PAGE = 3

class DownloadThreadTypes(Enum):
    ARTIST_PAGES = 1
    USER_PAGES = 2

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

    def _parse_user_follower_info_from_element(self, element):
        try:
            name = unescape(element.text)
            last_fm_user_url = element.attrib['href']
            return True, UserInfo(name, last_fm_user_url)
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
    
    def parse_user_followers_page(self, html):
        tree = etree.HTML(html)
        results = tree.xpath('//a[contains(@class, "user-list-link")]')
        for result in results:
            success, parsed_result = self._parse_user_follower_info_from_element(result)
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
        self.user_followers_page_folder = os.path.join(self.cache_folder, 'user-followers')
        
        # if the cache folder exists, then load existing cache files
        if os.path.exists(self.cache_folder):
            self._refresh_files()
        else:
            os.makedirs(self.cache_folder)
            os.makedirs(self.track_page_folder)
            os.makedirs(self.user_lib_artist_page_folder)
            os.makedirs(self.user_followers_page_folder)
    
    def _refresh_files(self):
        # clear queue
        with self.cache_file_paths.mutex:
            self.cache_file_paths.queue.clear()
        
        # only get html files
        track_files_to_add = [f for f in os.listdir(self.track_page_folder) if os.path.isfile(os.path.join(self.track_page_folder, f)) and f.endswith('.html')]
        user_lib_art_files_to_add = [f for f in os.listdir(self.user_lib_artist_page_folder) if os.path.isfile(os.path.join(self.user_lib_artist_page_folder, f)) and f.endswith('.html')]
        user_followers_files_to_add = [f for f in os.listdir(self.user_followers_page_folder) if os.path.isfile(os.path.join(self.user_followers_page_folder, f)) and f.endswith('.html')]
        
        # add track files
        for file_name in track_files_to_add:
            self.cache_file_paths.put((FileTypes.TRACK_PAGE, os.path.join(self.track_page_folder, file_name)))

        # add user library artist files
        for file_name in user_lib_art_files_to_add:
            self.cache_file_paths.put((FileTypes.USER_LIB_ARTIST_PAGE, os.path.join(self.user_lib_artist_page_folder, file_name)))
        
        # add user followers files
        for file_name in user_followers_files_to_add:
            self.cache_file_paths.put((FileTypes.USER_FOLLOWERS_PAGE, os.path.join(self.user_followers_page_folder, file_name)))
    
    def save_html(self, html, file_type, file_name=None):
        if file_name is None:
            file_name = uuid4().hex + ".html"
        
        save_folder = None
        if file_type == FileTypes.TRACK_PAGE:
            save_folder = self.track_page_folder
        elif file_type == FileTypes.USER_LIB_ARTIST_PAGE:
            save_folder = self.user_lib_artist_page_folder
        elif file_type == FileTypes.USER_FOLLOWERS_PAGE:
            save_folder = self.user_followers_page_folder
        
        # if we aren't given a valid file type then return as we won't know how to process it later
        if save_folder is None:
            return

        file_path = os.path.join(save_folder, re.sub(r"[<>:\"\/\\\|\?\*]", "", file_name))

        # only write to file if it doesn't already exist
        if os.path.exists(file_path):
            return

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        self.cache_file_paths.put((file_type, file_path))

    def get_html(self):
        # only get something if the queue is not empty
        if self.cache_file_paths.empty():
            return None, None
        
        file_type, file_path = self.cache_file_paths.get()

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_contents = f.read()
            
            # delete file
            os.remove(file_path)

            # return file_type and html content
            return file_type, file_contents
        except:
            # if there was an error getting the file then return none
            return None, None

class LastfmHTMLProcessorThread(Thread):

    def __init__(self, cache):
        super().__init__()
        self.cache = cache # this is a LastfmHTMLCacheManager
        self.processor = LastfmHTMLProcessor()
        self.stop = False
        self.exit = Event()

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
                mapping_to_update.last_updated = datetime.now(tz=get_localzone())
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
                last_updated = datetime.now(tz=get_localzone()),
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
    
    def _process_user_followers_html(self, html):
        users = self.processor.parse_user_followers_page(html)
        for user in users:
            # check for existing user in the queue
            query = LastfmUserProcessQueueItem.objects.filter(name=user.name)
            # if it's already in the queue, no need to add it again
            if len(query) > 0:
                # todo: add re-processing if it hasn't been updated in a while
                continue
            queue_item = LastfmUserProcessQueueItem(
                name = user.name,
                last_fm_user_url = user.last_fm_user_url,
                processed = False
            )
            queue_item.save()

    def run(self):
        while not self.stop:
            file_type, html = self.cache.get_html()
            try:
                if file_type is not None and html is not None:
                    if file_type == FileTypes.TRACK_PAGE:
                        self._process_track_html(html)
                    elif file_type == FileTypes.USER_LIB_ARTIST_PAGE:
                        self._process_user_lib_artist_html(html)
                    elif file_type == FileTypes.USER_FOLLOWERS_PAGE:
                        self._process_user_followers_html(html)
            except:
                print("Error in processing cycle")
                # resave the html if there was an error processing
                self.cache.save_html(html, file_type)
            self.exit.wait(1)
    
    def stop_process(self):
        self.stop = True
        self.exit.set()

class LastfmHTMLDownloader(Thread):

    def __init__(self, html_cache_manager, download_types=[DownloadThreadTypes.ARTIST_PAGES, DownloadThreadTypes.USER_PAGES], seed_users=[]):
        super().__init__()
        self.html_cache_manager = html_cache_manager
        self.stop = False
        self.exit = Event()
        self.seed_users = seed_users
        self.download_types = download_types
    
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
        artist_queue_item.processed_date = datetime.now(tz=get_localzone())
        artist_queue_item.save()

    def _download_user_pages(self, user_name):
        self._download_user_lib_artist_pages(user_name)
        self._download_user_followers_pages(user_name)

        # after saving all the user library artist pages and followers, mark the user as processed
        user_queue_item = LastfmUserProcessQueueItem.objects.filter(name=user_name).first()
        if user_queue_item is None:
            user_queue_item = LastfmUserProcessQueueItem(
                name = user_name,
                last_fm_user_url = '/user/{0}'.format(user_name)
            )
        user_queue_item.processed = True
        user_queue_item.processed_date = datetime.now(tz=get_localzone())
        user_queue_item.save()
    
    def _download_user_lib_artist_pages(self, user_name):
        page = 1
        while True:
            request = self.session.get("https://www.last.fm/user/{0}/library/artists?page={1}".format(user_name, page))
            if request.status_code != 200 or len(request.history) > 0 and request.history[0].status_code == 302:
                # either a bad request or we've reached the end of the users artist library pages
                break

            # save page
            self.html_cache_manager.save_html(request.text, FileTypes.USER_LIB_ARTIST_PAGE)
            page += 1
    
    def _download_user_followers_pages(self, user_name):
        page = 1
        while True:
            request = self.session.get("https://www.last.fm/user/{0}/followers?page={1}".format(user_name, page))
            if request.status_code != 200 or len(request.history) > 0 and request.history[0].status_code == 302:
                # either a bad request or we've reached the end of the users artist library pages
                break
            
            # save page
            self.html_cache_manager.save_html(request.text, FileTypes.USER_FOLLOWERS_PAGE)
            page += 1

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
        # if we have some seed users then download them first
        for seed_user in self.seed_users:
            self._download_user_pages(seed_user)
        
        while not self.stop:
            try:
                if DownloadThreadTypes.ARTIST_PAGES in self.download_types:
                    # process artist
                    artist_to_process = LastfmArtistProcessQueueItem.objects.filter(processed=False).first()
                    if artist_to_process is not None:
                        self._download_artist_track_pages(artist_to_process.name)

                if DownloadThreadTypes.USER_PAGES in self.download_types:
                    # process user
                    user_to_process = LastfmUserProcessQueueItem.objects.filter(processed=False).first()
                    if user_to_process is not None:
                        self._download_user_pages(user_to_process.name)
            except:
                print("Error in downloading cycle")

            self.exit.wait(2)

    def stop_process(self):
        self.stop = True
        self.exit.set()

class MappingsManager():

    def __init__(self, no_processing_threads=8, no_user_downloaders=1, no_artist_downloaders=6, no_both_downloaders=1, user_seeds=[]):
        self.html_cache_manager = LastfmHTMLCacheManager()
        self.downloaders = []
        self.processing_threads = []
        self.user_seeds = user_seeds
        self.no_processing_threads = no_processing_threads
        self.no_user_downloader_threads = no_user_downloaders
        self.no_artist_downloader_threads = no_artist_downloaders
        self.no_both_downloader_threads = no_both_downloaders
        self.exit = Event()

    def _load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'config.json')
        with open(config_path, 'r') as f:
            return json.load(f)

    def _start_downloader_threads(self, config, downloader_types, no_threads, use_seed_data=False):
        i = 0
        while i < no_threads:
            try:
                # setup downloader
                # if i == 0 add first downloader with seed data
                d = LastfmHTMLDownloader(self.html_cache_manager, downloader_types, self.user_seeds if use_seed_data and i == 0 else [])
                d.setup_last_fm_session(config['scrapingAccountDetails']['username'], config['scrapingAccountDetails']['password'])
                # start downloader
                d.start()
                self.downloaders.append(d)
            except:
                print("Error trying to start thread")
                i -= 1
            i += 1
            # wait briefly between each start up so that the login sesssion isn't blocked
            self.exit.wait(5)

    def start(self):
        # load config
        config = self._load_config()

        # start processing threads first as downloaders take a while to start
        for _ in range(self.no_processing_threads):
            t = LastfmHTMLProcessorThread(self.html_cache_manager)
            t.start()
            self.processing_threads.append(t)

        # start downloader threads
        self._start_downloader_threads(config, [DownloadThreadTypes.USER_PAGES], self.no_user_downloader_threads, True)
        self._start_downloader_threads(config, [DownloadThreadTypes.ARTIST_PAGES], self.no_artist_downloader_threads)
        self._start_downloader_threads(config, [DownloadThreadTypes.ARTIST_PAGES, DownloadThreadTypes.USER_PAGES], self.no_both_downloader_threads)

    
    def stop(self):
        self.exit.set()
        # stop downloader
        for d in self.downloaders:
            d.stop_process()
        
        for d in self.downloaders:
            d.join()

        # stop processing threads
        for t in self.processing_threads:
            t.stop_process()

        for t in self.processing_threads:
            t.join()

if __name__ == '__main__':
    manager = MappingsManager()
    manager.start()
    input()
    manager.stop()
