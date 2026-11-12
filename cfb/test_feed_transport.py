import gzip,io,json
from unittest.mock import patch
from cfb.sources import get_json


class Reply(io.BytesIO):
    def __init__(self,raw,encoding=''):
        super().__init__(raw);self.headers={'Content-Encoding':encoding}


def test_gzip_inventory_and_uncompressed_espn_share_json_transport():
    body={'events':[{'id':'1'}]}
    for raw,encoding in [(gzip.compress(json.dumps(body).encode()),'gzip'),(json.dumps(body).encode(),'')]:
        def open_(req,timeout):
            assert req.get_header('Accept-encoding')=='gzip'
            return Reply(raw,encoding)
        with patch('urllib.request.urlopen',open_):assert get_json('https://gamma-api.polymarket.com/events?limit=100')==body
