"""Main function of the wrapper"""
# Import typings dependencies
from __future__ import annotations
from typing import Any, Union, Optional

# Import standard Python dependencies
import warnings
import datetime
import math
import re

# Import other dependencies
from requests import Session
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Import version from __init__
from .__version__ import __version__

# Import own dependencies
from .article_search import *
from .book_reviews import *
from .movie_reviews import *

# Define all URLs that are needed
BASE_URL = "api.nytimes.com"
BASE_TOP_STORIES = BASE_URL + "/svc/topstories/v2/"
BASE_MOST_POPULAR = BASE_URL + "/svc/mostpopular/v2/"
BASE_BOOKS = BASE_URL + "/svc/books/v3/"
BASE_MOVIE_REVIEWS = BASE_URL + "/svc/movies/v2/reviews/search.json"
BASE_META_DATA = BASE_URL + "/svc/news/v3/content.json"
BASE_TAGS = BASE_URL + "/svc/semantic/v2/concept/suggest"
BASE_ARCHIVE_METADATA = BASE_URL + "/svc/archive/v1/"
BASE_ARTICLE_SEARCH = BASE_URL + "/svc/search/v2/articlesearch.json"
BASE_LATEST_ARTICLES = BASE_URL + "/svc/news/v3/content/"
BASE_SECTION_LIST = BASE_URL + "/svc/news/v3/content/section-list.json"
BASE_BOOK_REVIEWS = BASE_BOOKS + "reviews.json"
BASE_BEST_SELLERS_LISTS = BASE_BOOKS + "lists/names.json"
BASE_BEST_SELLERS_LIST = BASE_BOOKS + "lists/"


class NYTAPI:
    """New York Times API Class. Interacts with user."""

    # pylint: disable=too-many-arguments

    def __init__(
        self,
        key: str = None,
        https: bool = True,
        session: Optional[Session] = None,
        backoff: bool = True,
        user_agent: Optional[str] = None,
        parse_dates: bool = False,
    ) -> NYTAPI:
        # Raise Error if API key is not given, or wrong type
        if key is None:
            raise ValueError(
                "API key is not set, get an API-key from "
                + "https://developer.nytimes.com."
            )

        if not isinstance(key, str):
            raise TypeError("API key needs to be str")

        # Set API key
        self.key: str = key

        # Check if session is Session, add session to class so connection
        # can be reused
        self._local_session = False
        if session is None:
            self._local_session = True
            session = Session()

        if not isinstance(session, Session):
            raise TypeError("Session needs to be a Session object")

        self.session = session

        # Check if parse_dates is bool, if correct set parse_dates
        if not isinstance(parse_dates, bool):
            raise TypeError("parse_dates needs to be bool")

        self.parse_dates = parse_dates

        # Define protocol to be used
        if not isinstance(https, bool):
            raise TypeError("https needs to be bool")

        if https:
            self.protocol = "https://"
        else:
            self.protocol = "http://"

        # Set strategy to prevent HTTP 429 (Too Many Requests) errors
        if not isinstance(backoff, bool):
            raise TypeError("backoff needs to be bool")

        if backoff:
            backoff_strategy = Retry(
                total=10,
                backoff_factor=1,
                status_forcelist=[429, 509],
            )

            adapter = HTTPAdapter(max_retries=backoff_strategy)

            self.session.mount(self.protocol + "api.nytimes.com/", adapter)

        # Set header to show that this wrapper is used
        if user_agent is None:
            user_agent = "pynytimes/" + __version__

        if not isinstance(user_agent, str):
            raise TypeError("user_agent needs to be str")

        self.session.headers.update({"User-Agent": user_agent})

    def __enter__(self) -> NYTAPI:
        return self

    @staticmethod
    def _get_from_location(
        parsed_res: dict[str, Any],
        location: Optional[list[str]],
    ) -> list[dict[str, Any]]:
        # Get the data from the usual results location
        results: dict[str, Any]
        if location is None:
            results = parsed_res.get("results")

        # Sometimes the results are in a different location,
        # this location can be defined in a list
        # Then load the data from that location
        else:
            results = parsed_res
            for loc in location:
                results = results.get(loc)

        return results

    def _load_data(
        self,
        url: str,
        options: Optional[dict[str, Any]] = None,
        location: Optional[list[str]] = None,
    ) -> Union[list[dict[str, Any]], dict[str, Any]]:
        """This function loads the data for the wrapper for most API use cases"""
        # Set API key in query parameters
        params = {"api-key": self.key}

        # Add options to query parameters
        if options is not None:
            params.update(options)

        # Load the data from the API, raise error if there's an invalid status
        # code
        timeout = (4, 10)
        res = self.session.get(
            self.protocol + url,
            params=params,
            timeout=timeout,
        )

        if res.status_code == 400:
            raise ValueError("Error 400: Invalid input")

        if res.status_code == 401:
            raise ValueError("Error 401: Invalid API Key")

        if res.status_code == 403:
            raise RuntimeError("Error 403: You don't have access to this page")

        if res.status_code == 404:
            raise RuntimeError("Error 404: This page does not exist")

        res.raise_for_status()

        parsed_res: dict[str, Any] = res.json()

        return self._get_from_location(parsed_res, location)

    @staticmethod
    def _parse_date(
        date_string: str, date_type: str
    ) -> Union[datetime.datetime, datetime.date, None]:
        """Parse the date into datetime.datetime object"""
        # If date_string is None return None
        if date_string is None:
            return None

        date: Union[datetime.datetime, datetime.date]
        # Parse rfc3339 dates from str
        if date_type == "rfc3339":
            date = datetime.datetime.strptime(
                date_string,
                "%Y-%m-%dT%H:%M:%S%z",
            )

        # Parse date only strings
        if date_type == "date-only":
            if re.match(r"^(\d){4}-00-00$", date_string):
                date = datetime.datetime.strptime(
                    date_string, "%Y-00-00"
                ).date()

            date = datetime.datetime.strptime(date_string, "%Y-%m-%d").date()

        if date_type == "date-time":
            date = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")

        return date

    def _parse_dates(
        self, articles: list, date_type: str, locations: Optional[list] = None
    ) -> list[dict[str, Any]]:
        """Parse dates to datetime"""
        # Create list locations is None
        if locations is None:
            locations = []

        # Don't parse if parse_dates is False
        if self.parse_dates is False:
            return articles

        # Create parsed_articles list
        parsed_articles = []

        # For every article parse date_string into datetime.datetime
        for article in articles:
            parsed_article = article
            for location in locations:
                parsed_article[location] = self._parse_date(
                    parsed_article[location], date_type
                )
            parsed_articles.append(article)

        return parsed_articles

    def top_stories(self, section: str = "home") -> list[dict[str, Any]]:
        """Load the top stories"""
        # Raise error if section is not a str
        if not isinstance(section, str):
            raise TypeError("Section can only be a str")

        # Set the URL the data can be loaded from, and load the data
        url = BASE_TOP_STORIES + section + ".json"

        try:
            result = self._load_data(url)

        # If 404 error throw invalid section name error
        except RuntimeError:
            raise ValueError("Invalid section name")

        # Parse dates from string to datetime.datetime
        date_locations = ["updated_date", "created_date", "published_date"]
        parsed_result = self._parse_dates(result, "rfc3339", date_locations)

        return parsed_result

    def most_viewed(self, days: int = 1) -> list[dict[str, Any]]:
        """Load most viewed articles"""
        days_options = [1, 7, 30]

        # Raise an Exception if days is not a int
        if not isinstance(days, int):
            raise TypeError("You can only enter an int")

        # Raise an Exception if number of days is invalid
        if days not in days_options:
            raise ValueError("You can only select 1, 7 or 30 days")

        # Load the data
        url = BASE_MOST_POPULAR + "viewed/" + str(days) + ".json"
        result = self._load_data(url)

        # Parse the dates in the results
        parsed_date_result = self._parse_dates(
            result,
            "date-only",
            ["published_date"],
        )

        parsed_result = self._parse_dates(
            parsed_date_result,
            "date-time",
            ["updated"],
        )

        return parsed_result

    def most_shared(
        self, days: int = 1, method: str = "email"
    ) -> list[dict[str, Any]]:
        """Load most shared articles"""
        # Check if options are valid
        method_options = ["email", "facebook"]
        days_options = [1, 7, 30]

        # Raise error if method isn't a str
        if not isinstance(method, str):
            raise TypeError("Method needs to be str")

        # Raise error if days isn't an int
        if not isinstance(days, int):
            raise TypeError("Days needs to be int")

        # Raise error if days, or method aren't in options
        if method not in method_options:
            raise ValueError("Shared option does not exist")

        if days not in days_options:
            raise ValueError("You can only select 1, 7 or 30 days")

        # Set URL of data that needs to be loaded
        url = BASE_MOST_POPULAR

        if method is None:
            url += "shared/" + str(days) + ".json"
        elif method == "email":
            url += "emailed/" + str(days) + ".json"
        else:
            url += "shared/" + str(days) + "/" + method + ".json"

        # Load the data
        result = self._load_data(url)

        # Parse the date_strings into datetime.datetime
        parsed_date_result = self._parse_dates(
            result, "date-only", ["published_date"]
        )
        parsed_result = self._parse_dates(
            parsed_date_result, "date-time", ["updated"]
        )

        return parsed_result

    def book_reviews(
        self,
        author: Optional[str] = None,
        isbn: Union[str, int, None] = None,
        title: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Load book reviews"""
        # Check book review input
        book_reviews_check_input(author, isbn, title)

        # Set request options params
        options = {}

        if author is not None:
            options["author"] = author
        elif isbn is not None:
            options["isbn"] = str(isbn)
        elif title is not None:
            options["title"] = title

        # Set URL, load and return data
        url = BASE_BOOK_REVIEWS
        result = self._load_data(url, options=options)

        parsed_result = self._parse_dates(
            result, "date-only", ["publication_dt"]
        )
        return parsed_result

    def best_sellers_lists(self) -> list[dict[str, Any]]:
        """Load all the best seller lists"""
        # Set URL, load and return data
        url = BASE_BEST_SELLERS_LISTS

        result = self._load_data(url)

        parsed_result = self._parse_dates(
            result,
            "date-only",
            ["oldest_published_date", "newest_published_date"],
        )
        return parsed_result

    def best_sellers_list(
        self,
        date: Union[datetime.date, datetime.datetime, None] = None,
        name: str = "combined-print-and-e-book-fiction",
    ) -> list[dict[str, Any]]:
        """Load a best seller list"""
        # Convert datetime.date into datetime.datetime
        if isinstance(date, datetime.date):
            date = datetime.datetime(date.year, date.month, date.day)

        # Set valid date
        if date is None:
            _date = "current"

        # Raise error if date is not a datetime.datetime object
        elif not isinstance(date, datetime.datetime):
            raise TypeError("Date has to be a datetime object")

        # Set date if defined
        else:
            _date = date.strftime("%Y-%m-%d")

        # Set URL and include data
        url = BASE_BEST_SELLERS_LIST + _date + "/" + name + ".json"

        # Set location in JSON of results, load and return data
        location = ["results", "books"]
        try:
            result = self._load_data(url, location=location)
        except RuntimeError:
            raise ValueError("Best sellers list name is invalid")

        return result

    def movie_reviews(
        self,
        keyword: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
        dates: Optional[
            dict[str, Union[datetime.date, datetime.datetime]]
        ] = None,
    ) -> list[dict[str, Any]]:
        """Load movie reviews"""
        # Set options and dates if not defined
        if options is None:
            options = {}

        if dates is None:
            dates = {}

        # Check input types and values
        movie_reviews_check_input(keyword, options, dates)

        # Parse the dates into the request params
        params = movie_reviews_parse_dates(dates)

        # Set keyword if defined
        if keyword is not None:
            params["query"] = keyword

        # Set critics pick to "Y" if true
        if options.get("critics_pick") is True:
            params["critics_pick"] = "Y"

        # Set API request params if defined
        params["reviewer"] = options.get("reviewer")
        params["order"] = options.get("order")

        # Set URL request data
        url = BASE_MOVIE_REVIEWS

        # Set results list
        results = []

        # Keep loading data until amount of results is received
        # Set max_results if undefined
        max_results = options.get("max_results", 20)
        requests_needed = math.ceil(max_results / 20)
        for i in range(requests_needed):
            # Set offset for second request
            offset = i * 20
            params["offset"] = str(offset)

            # Load the data from the API and raise if there's an Error
            res: dict[str, Any] = self._load_data(
                url,
                options=params,
                location=[],
            )

            results += res.get("results")

            # Quit loading more data if no more data is available
            if res.get("has_more") is False:
                break

        # Parse and return the results
        parsed_date_results = self._parse_dates(
            results, "date-only", ["publication_date", "opening_date"]
        )
        parsed_results = self._parse_dates(
            parsed_date_results, "date-time", ["date_updated"]
        )

        return parsed_results

    def article_metadata(self, url: str) -> list[dict[str, Any]]:
        """Load the metadata from an article"""
        # Raise error if url is not an str
        if not isinstance(url, str):
            raise TypeError("URL needs to be str")

        # Set metadata in requests params and define URL
        options = {"url": url}
        url = BASE_META_DATA

        # Load, parse and return the data
        result = self._load_data(url, options=options)

        # Check if result is valid
        if result[0].get("published_date") == "0000-12-31T19:03:58-04:56":
            raise ValueError(
                "Invalid URL, the API cannot parse metadata from live articles"
            )

        date_locations = [
            "updated_date",
            "created_date",
            "published_date",
            "first_published_date",
        ]
        parsed_result = self._parse_dates(result, "rfc3339", date_locations)
        return parsed_result

    def section_list(self) -> list[dict[str, Any]]:
        """Load all sections"""
        # Set URL, load and return the data
        url = BASE_SECTION_LIST
        return self._load_data(url)

    def latest_articles(
        self, source: str = "all", section: str = "all"
    ) -> list[dict[str, Any]]:
        """Load the latest articles"""
        if not isinstance(source, str):
            raise TypeError("Source needs to be str")

        if not isinstance(section, str):
            raise TypeError("Section needs to be str")

        # Check if sections options is valid
        source_options = ["all", "nyt", "inyt"]

        if source not in source_options:
            raise ValueError("Source is not a valid option")

        # Set URL, load and return data
        url = BASE_LATEST_ARTICLES + source + "/" + section + ".json"
        try:
            result = self._load_data(url)
        except RuntimeError:
            raise ValueError("Section is not a valid option")

        date_locations = [
            "updated_date",
            "created_date",
            "published_date",
            "first_published_date",
        ]
        parsed_result = self._parse_dates(result, "rfc3339", date_locations)
        return parsed_result

    def tag_query(
        self,
        query: str,
        filter_option: Optional[dict[str, Any]] = None,
        filter_options: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> list[str]:
        """Load TimesTags"""
        # Raise error for TypeError
        if not isinstance(query, str):
            raise TypeError("Query needs to be str")

        if not isinstance(max_results, (type(None), int)):
            raise TypeError("Max results needs to be int")

        # Add filter options
        _filter_options = ""
        if filter_options is not None:
            for filter_opt in filter_options:
                if _filter_options is not None:
                    _filter_options += ","

                _filter_options += filter_opt

        elif filter_option is not None:
            _filter_options = filter_option

        # Add options to request params
        options = {"query": query, "filter": _filter_options}

        # Define amount of results wanted
        if max_results is not None:
            options["max"] = str(max_results)

        # Set URL, load and return data
        url = BASE_TAGS
        return self._load_data(url, options=options, location=[])[1]

    def archive_metadata(
        self, date: Union[datetime.datetime, datetime.date]
    ) -> list[dict[str, Any]]:
        """Load all the metadata from one month"""
        # Also accept datetime.date, convert it to datetime.datetime
        if isinstance(date, datetime.date):
            date = datetime.datetime(date.year, date.month, date.day)

        # Raise Error if date is not defined
        if not isinstance(date, datetime.datetime):
            raise TypeError("Date has to be datetime")

        # Get date as is needed in request
        year = date.year
        month = date.month
        _date = f"{year}/{month}"

        # Set URL, load and return data
        url = BASE_ARCHIVE_METADATA + _date + ".json"

        result = self._load_data(url, location=["response", "docs"])
        parsed_result = self._parse_dates(result, "rfc3339", ["pub_date"])
        return parsed_result

    def article_search(
        self,
        query: Optional[str] = None,
        dates: Optional[
            dict[str, Union[datetime.date, datetime.datetime]]
        ] = None,
        options: Optional[dict[str, Any]] = None,
        results: int = 10,
    ) -> list[dict[str, Any]]:
        """Load articles from search"""
        # Set if None
        if dates is None:
            dates = {}

        if options is None:
            options = {}

        # Check if input is valid
        article_search_check_input(query, dates, options, results)

        # Limit results loading to 2010
        results = min(results, 2010)

        # Resolve filter options into fq
        options = article_search_parse_options(options)

        # Parse dates into options
        begin_date, end_date = article_search_parse_dates(dates)
        options["begin_date"] = begin_date
        options["end_date"] = end_date

        # Set query if defined
        if query is not None:
            options["q"] = query

        url = BASE_ARTICLE_SEARCH

        # Set result list and add request as much data as needed
        result = []
        for i in range(math.ceil(results / 10)):
            # Set page
            options["page"] = str(i)

            location = ["response"]
            # Load data and raise error if there's and error status
            res = self._load_data(url, options=options, location=location)

            # Parse results and append them to results list
            result += res.get("docs")

            # Stop loading if all responses are already loaded
            if res.get("meta", {}).get("hits") <= i * 10:
                break

        # Parse and return results
        parsed_result = self._parse_dates(result, "rfc3339", ["pub_date"])
        return parsed_result

    # Allow the option to close the session
    def close(self) -> None:
        """Close session"""
        # Close session only if it exists
        if hasattr(self, "session"):
            self.session.close()

    # Close session before delete
    def __del__(self) -> None:
        """Close session on deletion"""
        if getattr(self, "_local_session", False) is True:
            self.close()

    def __exit__(self, *args) -> None:
        """Close session on exit"""
        if getattr(self, "_local_session", False) is True:
            self.close()
