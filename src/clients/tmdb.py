from tmdbv3api import TMDb, Movie, TV
from src.config import config

class TMDBClient:
    def __init__(self):
        self.tmdb = TMDb()
        self.tmdb.api_key = config.get().tmdb_api_key
        self.movie = Movie()
        self.tv = TV()

    def search_movie(self, query):
        if not self.tmdb.api_key: return []
        return self.movie.search(query)

    def search_tv(self, query):
        if not self.tmdb.api_key: return []
        return self.tv.search(query)

    def get_movie_details(self, tmdb_id):
        if not self.tmdb.api_key: return None
        return self.movie.details(tmdb_id)

    def get_tv_details(self, tmdb_id):
        if not self.tmdb.api_key: return None
        return self.tv.details(tmdb_id)
