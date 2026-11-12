import io,json,zipfile,urllib.error
from email.message import Message
from unittest.mock import patch
import pytest
from cfb import github_artifacts as G


def archive():
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w')as z:z.writestr('delivery.json','{}')
    return b.getvalue()


def redirect(url,code=302):
    h=Message();h['Location']=url
    return urllib.error.HTTPError('https://api.github.com/archive',code,'redirect',h,None)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('GITHUB_REPOSITORY','o/r');monkeypatch.setenv('GITHUB_TOKEN','do-not-leak')


def test_archive_refreshes_expired_redirect_and_never_forwards_token():
    calls=[];raw=archive()
    def open_(req):
        calls.append(req)
        if 'api.github.com'in req.full_url:raise redirect('https://actionsresults.blob.core.windows.net/archive?sig=private-signature')
        assert req.get_header('Authorization')is None
        if len(calls)==2:raise urllib.error.HTTPError(req.full_url,401,'expired',{},None)
        return io.BytesIO(raw)
    with patch.object(G,'_open',open_),patch.object(G.time,'sleep'):
        assert G.api('/actions/artifacts/1/zip',True)==raw
    api_urls=[r.full_url for r in calls if 'api.github.com'in r.full_url]
    assert len(set(api_urls))==2
    assert all(r.get_header('Authorization')=='Bearer do-not-leak' for r in calls if 'api.github.com'in r.full_url)


def test_metadata_still_uses_authenticated_github_api():
    with patch.object(G,'_open',lambda r:io.BytesIO(json.dumps({'artifacts':[]}).encode())):
        assert G.api('/actions/artifacts')=={'artifacts':[]}


def test_rejects_unrecognized_redirect_without_transmitting_credentials():
    calls=[]
    def open_(req):calls.append(req);raise redirect('https://evil.example/archive')
    with patch.object(G,'_open',open_),pytest.raises(RuntimeError,match='Unrecognized'):
        G.api('/actions/artifacts/1/zip',True)
    assert len(calls)==1


def test_failed_signed_url_is_not_logged_in_error():
    def open_(req):
        if 'api.github.com'in req.full_url:raise redirect('https://actionsresults.blob.core.windows.net/archive?sig=private-signature')
        raise urllib.error.HTTPError(req.full_url,403,'private-signature',{},None)
    with patch.object(G,'_open',open_),patch.object(G.time,'sleep'),pytest.raises(RuntimeError)as e:
        G.api('/actions/artifacts/1/zip',True)
    assert 'private-signature'not in str(e.value)and 'do-not-leak'not in str(e.value)


def test_rejects_invalid_zip():
    with patch.object(G,'_open',lambda r:io.BytesIO(b'not a ZIP')),pytest.raises(RuntimeError,match='valid ZIP'):
        G.api('/actions/artifacts/1/zip',True)
