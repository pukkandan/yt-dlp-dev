from yt_dlp.extractor.common import InfoExtractor


class NormalPluginIE(InfoExtractor):
    REPLACED = False


class _IgnoreUnderscorePluginIE(InfoExtractor):
    pass
