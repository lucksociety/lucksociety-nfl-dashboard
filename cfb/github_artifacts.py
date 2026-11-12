"""Download private Actions archives without cached SAS URLs or cross-host tokens."""
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


def _open(req):
    return urllib.request.build_opener(NoRedirect()).open(req,timeout=30)


def _allowed(url):
    p=urllib.parse.urlsplit(url);h=(p.hostname or '').lower()
    return p.scheme=='https' and not p.username and not p.password and p.port in [None,443] and any(h.endswith('.'+suffix) for suffix in ['blob.core.windows.net','actions.githubusercontent.com'])


def _unsigned_download(url):
    for _ in range(4):
        if not _allowed(url):raise RuntimeError('Unrecognized Actions archive download host')
        try:
            with _open(urllib.request.Request(url,headers={'User-Agent':'LuckSociety-learning','Cache-Control':'no-cache'})) as r:return r.read()
        except urllib.error.HTTPError as e:
            if e.code in [301,302,303,307,308] and e.headers.get('Location'):
                url=urllib.parse.urljoin(url,e.headers['Location']);continue
            raise
    raise RuntimeError('Too many Actions archive redirects')


def api(path,binary=False):
    base='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+path
    headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json',
             'User-Agent':'LuckSociety-learning','Cache-Control':'no-cache'}
    if not binary:
        with _open(urllib.request.Request(base,headers=headers)) as r:return json.load(r)
    last_status=None
    for attempt in range(3):
        # GitHub/CDN can cache a redirect whose short-lived Azure signature expired.
        sep='&' if '?' in base else '?';url=base+sep+urllib.parse.urlencode({'fresh':uuid.uuid4().hex})
        try:
            try:
                with _open(urllib.request.Request(url,headers=headers)) as r:raw=r.read()
            except urllib.error.HTTPError as e:
                if e.code not in [301,302,303,307,308] or not e.headers.get('Location'):raise
                raw=_unsigned_download(urllib.parse.urljoin(url,e.headers['Location']))
            if not zipfile.is_zipfile(io.BytesIO(raw)):raise RuntimeError('Actions archive is not a valid ZIP')
            return raw
        except urllib.error.HTTPError as e:
            last_status=e.code
            if e.code not in [401,403,408,429,500,502,503,504]:break
        except (TimeoutError,urllib.error.URLError):
            last_status='network'
        if attempt<2:time.sleep(attempt+1)
    # Do not expose signed URLs or authorization headers through exception text.
    raise RuntimeError('Actions archive download failed after retries (HTTP '+str(last_status)+')') from None
