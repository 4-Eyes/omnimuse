from django.db import models

class Mapping(models.Model):
    spotify_id = models.CharField(max_length=50, primary_key=True)
    spotify_url = models.CharField(max_length=200)
    track_name = models.CharField(max_length=200)
    last_fm_track_url = models.CharField(max_length=200)
    artist_name = models.CharField(max_length=200)
    last_fm_artist_url = models.CharField(max_length=200)
    manually_mapped = models.BooleanField()
    last_updated = models.DateTimeField()

class LastfmArtistProcessQueueItem(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    last_fm_artist_url = models.CharField(max_length=200)
    processed = models.BooleanField()
    processed_date = models.DateTimeField()

class LastfmUserProcessQueueItem(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    last_fm_user_url = models.CharField(max_length=200)
    processed = models.BooleanField()
    processed_date = models.DateTimeField()