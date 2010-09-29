from xml.dom import minidom

# extremely boring dom parsing ahead. Consider yourself warned.

API_VERSION = "1"
USER_AGENT = "Spotimeta %s" % 1

# The reason for the uri arg is that the xml returned from lookups do not
# contain the href uri of the thing that was looked up. However, when an
# element is encountered that is NOT the root of a query, it DOES contain
# the href. We pass it in so the returned data will have the same format
# always
def parse_lookup_doc(src, uri=None):
    doc = minidom.parse(src)
    root = doc.documentElement

    if root.nodeName == "artist":
        return {"type": "artist", "result": parse_artist(root, uri)}
    elif root.nodeName == "album":
        return {"type": "album", "result": parse_album(root, uri)}
    elif root.nodeName == "track":
        return {"type": "track", "result": parse_track(root, uri)}
    else:
        raise Exception("unknown node type! " + root.nodeName) # fixme: proper exception here


def parse_search_doc(src):
    doc = minidom.parse(src)
    root = doc.documentElement

    if root.nodeName == "artists":
        return parse_artist_search(root)
    elif root.nodeName == "albums":
        return parse_album_search(root)
    elif root.nodeName == "tracks":
        return parse_track_search(root)
    else:
        raise Exception("unknown node type! " + root.nodeName) # fixme: proper exception here


def parse_artist(root, uri=None):
    ret = {}
    if uri or root.hasAttribute("href"):
        ret["href"] = uri or root.getAttribute("href")

    for name, elem in _nodes(root):
        if name == "name":
            ret["name"] = _text(elem)
        elif name == "albums":
            ret["albums"] = parse_albumlist(elem)

    return ret


def parse_artistlist(root):
    return map(parse_artist, _filter(root, "artist"))


def parse_albumlist(root):
    return map(parse_album, _filter(root, "album"))


def parse_tracklist(root):
    return map(parse_track, _filter(root, "track"))


def parse_album(root, uri=None):
    ret = {}
    if uri or root.hasAttribute("href"):
        ret["href"] = uri or root.getAttribute("href")

    for name, elem in _nodes(root):
        if name == "name":
            ret["name"] = _text(elem)
        elif name == "released":
            released = _text(elem)
            if released:
                ret["released"] = int(_text(elem))
        elif name == "id":
            if not "ids" in ret:
                ret["ids"] = []
            ret["ids"].append(parse_id(elem))
        elif name == "tracks":
            ret["tracks"] = parse_tracklist(elem)

    ret["artists"] = parse_artistlist(root)
    if len(ret["artists"]) == 1:
        ret["artist"] = ret["artists"][0]
    else:
        ret["artist"] = None


    # todo: availability stuff. RFH
    return ret


def parse_id(elem):
    ret = {"type": elem.getAttribute("type"),
           "id": _text(elem)}
    if elem.hasAttribute("href"):
        ret["href"] = elem.getAttribute("href")
    return ret


def parse_track(root, uri=None):
    ret = {}
    if uri or root.hasAttribute("href"):
        ret["href"] = uri or root.getAttribute("href")

    for name, elem in _nodes(root):
        if name == "name":
            ret["name"] = _text(elem)
        elif name == "disc-number":
            ret["disc-number"] = int(_text(elem))
        elif name == "track-number":
            ret["track-number"] = int(_text(elem))
        elif name == "length":
            ret["length"] = float(_text(elem))
        elif name == "popularity":
            ret["popularity"] = float(_text(elem))
        elif name == "album":
            ret["album"] = parse_album(elem)
        elif name == "id":
            if not "ids" in ret:
                ret["ids"] = []
            ret["ids"].append(parse_id(elem))

    ret["artists"] = parse_artistlist(root)

    # Following prop is there for backwards compat. It may be dropped in a
    # future version
    if ret["artists"]:
        ret["artist"] = ret["artists"][0]

    return ret


def parse_opensearch(root):
    ret = {}
    elems = root.getElementsByTagNameNS("http://a9.com/-/spec/opensearch/1.1/", "*")

    for name, elem in ((e.localName, e) for e in elems):
        if name == "Query":
            ret["term"] = elem.getAttribute("searchTerms")
            ret["start_page"] = int(elem.getAttribute("startPage"))
        elif name == "totalResults":
            ret["total_results"] = int(_text(elem))
        elif name == "startIndex":
            ret["start_index"] = int(_text(elem))
        elif name == "itemsPerPage":
            ret["items_per_page"] = int(_text(elem))

    return ret


def parse_album_search(root):
    # Note that the search result tags are not <search> tags or similar.
    # Instead they are normal <artists|albums|tracks> tags with extra
    # stuff from the opensearch namespace. That's why we cant just directly
    # return the result from parse_albumlist
    ret = parse_opensearch(root)
    ret["result"] = parse_albumlist(root)
    return ret


def parse_artist_search(root):
    ret = parse_opensearch(root)
    ret["result"] = parse_artistlist(root)
    return ret


def parse_track_search(root):
    ret = parse_opensearch(root)
    ret["result"] = parse_tracklist(root)
    return ret


def _nodes(elem):
    """return an generator yielding element nodes that are children
    of elem."""
    return ((e.nodeName, e) for e
            in elem.childNodes
            if e.nodeType==e.ELEMENT_NODE)


def _text(elem):
    """Returns a concatenation of all text nodes that are children
    of elem (roughly what elem.textContent does in web dom"""
    return "".join((e.nodeValue for e
                    in elem.childNodes
                    if e.nodeType==e.TEXT_NODE))


def _filter(elem, filtername):
    """Returns a generator yielding all child nodes with the nodeName name"""
    return (elem for (name, elem)
            in _nodes(elem)
            if name == filtername)


import sys
import urllib2
import time

try:
    from email.utils import parsedate_tz, mktime_tz, formatdate
except ImportError: # utils module name was lowercased after 2.4
    from email.Utils import parsedate_tz, mktime_tz, formatdate


from urllib import urlencode



class SpotimetaError(Exception):
    """Superclass for all spotimeta exceptions. Adds no functionality. Only
    there so it's possible to set up try blocks that catch all spotimeta
    errors, regardless of class"""
    pass


class RequestTimeout(SpotimetaError):
    """Raised when the timeout flag is in use and a request did not finish
    within the allotted time."""
    pass


class NotFound(SpotimetaError):
    """Raised when doing lookup on something that does not exist. Triggered
    by the 404 http status code"""
    pass


class RateLimiting(SpotimetaError):
    """Raised when the request was not completed due to rate limiting
    restrictions"""
    pass

class ServiceUnavailable(SpotimetaError):
    """Raised when the metadata service is not available (that is, the server
    is up, but not accepting API requests at this time"""
    pass


class ServerError(SpotimetaError):
    """Raised when an internal server error occurs. According to the spotify
    documentation, this "should not happen"."""
    pass


def canonical(url_or_uri):
    """returns a spotify uri, regardless if a url or uri is passed in"""
    if url_or_uri.startswith("http"): # assume it's a url
        parts = url_or_uri.split("/")
        return "spotify:%s:%s" % (parts[-2], parts[-1])
    else:
        return url_or_uri


def entrytype(url_or_uri):
    """Return "album", "artist" or "track" based on the type of entry the uri
    or url refers to."""
    uri = canonical(url_or_uri)
    try:
        return uri.split(":")[1]
    except IndexError:
        return None


class Metadata(object):

    def __init__(self, cache=None, rate=10, timeout=None, user_agent=None):
        self.cache = cache # not implemented yet
        self.rate = rate # not implemented yet
        self.timeout = timeout
        self.user_agent = user_agent or USER_AGENT
        self._timeout_supported = True
        self._port = "80"
        self._host = "ws.spotify.com"
        self._detailtypes = {
            "artist": {1: "album", 2: "albumdetail"},
            "album": {1: "track", 2: "trackdetail"}
        }


        major, minor = sys.version_info[:2]
        if self.timeout and major == 2 and minor <6:
            self._timeout_supported = False
            import warnings
            warnings.warn("Timeouts in urllib not supported in this version" +
                          " of python. timeout argument will be ignored!")


    def _do_request(self, url, headers):
        """Perform an actual response. Deal with 200 and 304 responses
        correctly. If another error occurs, raise the appropriate
        exception"""
        try:
            req = urllib2.Request(url, None, headers)
            if self.timeout and self._timeout_supported:
                return urllib2.urlopen(req, timeout=self.timeout)
            else:
                return urllib2.urlopen(req)

        except urllib2.HTTPError, e:
            if e.code == 304:
                return e # looks wrong but isnt't. On non fatal errors the
                         # exception behaves like the retval from urlopen
            elif e.code == 404:
                raise NotFound()
            elif e.code == 403:
                raise RateLimiting()
            elif e.code == 500:
                raise ServerError()
            elif e.code == 503:
                raise ServiceUnavailable()
            else:
                raise # this should never happen
        except urllib2.URLError, e:
            """Probably timeout. should do a better check. FIXME"""
            raise RequestTimeout()
        except:
            raise
            # all the exceptions we don't know about yet. Probably
            # some socket errors will come up here.

    def _get_url(self, url, query, if_modified_since=None):
        """Perform an http requests and return the open file-like object, if
        there is one, as well as the expiry time and last-modified-time
        if they were present in the reply.
        If the if_modified_since variable is passed in, send it as the value
        of the If-Modified-Since header."""
        if query:
            url = "%s?%s" %(url, urlencode(query))

        headers = {'User-Agent': self.user_agent}
        if if_modified_since:
            headers["If-Modified-Since"] = formatdate(if_modified_since, False, True)

        fp = self._do_request(url, headers)

        # at this point we have something file like after the request
        # finished with a 200 or 304.

        headers = fp.info()
        if fp.code == 304:
            fp = None

        expires = None
        if "Expires" in headers:
            expires = mktime_tz(parsedate_tz(headers.get("Expires")))

        modified = None
        if "Last-Modified" in headers:
            modified = mktime_tz(parsedate_tz(headers.get("Last-Modified")))

        return fp, modified, expires


    def lookup(self, uri, detail=0):
        """Lookup metadata for a URI. Optionally ask for extra details.
        The details argument is an int: 0 for normal ammount of detauls, 1
        for extra details, and 2 for most details. For tracks the details
        argument is ignored, as the Spotify api only has one level of detail
        for tracks. For the meaning of the detail levels, look at the
        Spotify api docs"""

        key = "%s:%s" % (uri, detail)
        res, modified, expires = self._cache_get(key)

        if res and time.time() < expires:
            return res
        # else, cache is outdated or entry not in it. Normal request cycle

        url = "http://%s:%s/lookup/%s/" % (self._host, self._port, API_VERSION)
        uri = canonical(uri)
        query = {"uri": uri}
        kind = entrytype(uri)

        if detail in (1,2) and kind in self._detailtypes.keys():
            query["extras"] = self._detailtypes[kind][detail]

        fp, new_modified, new_expires = self._get_url(url, query, modified)

        if fp: # We got data, sweet
            res = parse_lookup_doc(fp, uri=uri)

        self._cache_put(key, res, new_modified or modified, new_expires or expires)
        return res

    def search_album(self, term, page=None):
        """The first page is numbered 1!"""
        url = "http://%s:%s/search/%s/album" % (
            self._host, self._port, API_VERSION)

        return self._do_search(url, term, page)

    def search_artist(self, term, page=None):
        """The first page is numbered 1!"""
        url = "http://%s:%s/search/%s/artist" % (
            self._host, self._port, API_VERSION)

        return self._do_search(url, term, page)

    def search_track(self, term, page=None):
        """The first page is numbered 1!"""
        url = "http://%s:%s/search/%s/track" % (
            self._host, self._port, API_VERSION)

        return self._do_search(url, term, page)

    def _do_search(self, url, term, page):
        key = "%s:%s" % (term, page)

        res, modified, expires = self._cache_get(key)
        if res and time.time() < expires:
            return res

        query = {"q": term.encode('UTF-8')}

        if page is not None:
            query["page"] = str(page)

        fp, new_modified, new_expires = self._get_url(url, query, modified)

        if fp: # We got data, sweet
            res = parse_search_doc(fp)

        self._cache_put(key, res, new_modified or modified, new_expires or expires)

        return res

    def _cache_get(self, key):
        """Get a tuple containing data, last-modified, expires.
        If entry is not in cache return None, 0, 0
        """
        entry = None
        if self.cache is not None:
            entry = self.cache.get(key)

        return entry or (None, 0, 0)

    def _cache_put(self, key, value, modified, expires):
        """Inverse of _cache_put"""
        if self.cache is not None:
            self.cache[key] = value, modified, expires

