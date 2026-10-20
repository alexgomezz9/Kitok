from kitok.providers.pexels import PexelsProvider
from kitok.stock.cache import SearchCache
from kitok.stock.models import StockAsset


def test_creator_provenance_survives_provider_and_cache(tmp_path):
    source={'id':42,'duration':12,'url':'https://www.pexels.com/video/42/',
            'user':{'name':'Creator Name','url':'https://www.pexels.com/@creator/'},
            'video_files':[{'link':'https://videos.pexels.com/42.mp4','width':1920,'height':1080,'fps':30}]}
    asset=PexelsProvider._parse_asset(source,'city')
    cache=SearchCache(tmp_path);cache.store('city','landscape',80,1,[asset])
    restored=cache.load('city','landscape',80,1)[0]
    assert restored.author=='Creator Name' and restored.author_url==source['user']['url']
    assert restored.page_url==source['url']


def test_legacy_cache_keeps_unknown_creator_explicit():
    asset=StockAsset.from_dict({'asset_id':42,'query':'city','duration':12,'variants':[]})
    assert asset.author is None and asset.author_url is None
