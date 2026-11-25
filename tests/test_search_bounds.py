import pytest

from continuity_mcp.models import CanonicalConversation, CanonicalMessage
from continuity_mcp.store import ArchiveStore


@pytest.mark.parametrize('content', [
    'needle ' + 'x' * 200_000 + ' tail',
    'needle ' + '🦆' * 200_000 + ' tail',
    'needle' + 'x' * 200_000,
    'needle short message',
    'x' * 500 + ' needle tail',
])
def test_search_snippets_have_character_bound_and_exact_retrieval(tmp_path, content):
    store = ArchiveStore(tmp_path / 'archive.sqlite3')
    export = tmp_path / 'export.json'
    export.write_text('[]')
    source = store.ingest_source(export, 'chatgpt')
    store.import_conversations([
        CanonicalConversation('chatgpt', 'c1', 'Synthetic bounds', (
            CanonicalMessage('chatgpt', 'c1', 'm1', 'user', content),
        )),
    ], source_id=source.id)

    # The all-one-token case must be searched as a complete lexical term.
    query = content if ' ' not in content else 'needle'
    hit, = store.search(query)
    assert len(hit['snippet']) <= 1024
    assert hit['snippet_truncated'] is (len(content) > 1024)
    if len(content) <= 1024:
        assert hit['snippet'] == content

    # Clipping search output must never shorten or rewrite stored source text.
    pieces = []
    start = 0
    while start is not None:
        message = store.message(hit['message_id'], start_char=start, max_chars=20_000)
        pieces.append(message['content'])
        start = message['next_start_char']
    assert ''.join(pieces) == content


@pytest.mark.parametrize('content', [
    'x' * 200_000 + ' needle tail',
    'a ' + 'x' * 5_000 + ' needle ' + 'y' * 5_000,
    'é' * 3_000 + ' needle ' + '🦆' * 3_000,
    '\x01' * 64 + 'x' * 5_000 + ' needle ' + '\x02' * 64,
    'left \x01 right needle \x02 source',
])
def test_search_window_keeps_match_and_preserves_marker_like_source(tmp_path, content):
    store = ArchiveStore(tmp_path / 'a.sqlite3')
    export = tmp_path / 'export.json'
    export.write_text('[]')
    source = store.ingest_source(export, 'chatgpt')
    store.import_conversations([
        CanonicalConversation('chatgpt', 'c', 'Synthetic', (
            CanonicalMessage('chatgpt', 'c', 'm', 'user', content),
        )),
    ], source_id=source.id)
    hit, = store.search('needle')
    assert len(hit['snippet']) <= 1024
    assert 'needle' in hit['snippet']
    assert hit['snippet'] in content
    assert hit['snippet_truncated'] is (len(content) > 1024)
    if len(content) <= 1024:
        assert hit['snippet'] == content


def test_character_clip_flag_is_not_whole_message_flag(tmp_path):
    store = ArchiveStore(tmp_path / 'a.sqlite3')
    export = tmp_path / 'export.json'
    export.write_text('[]')
    source = store.ingest_source(export, 'chatgpt')
    content = 'word ' * 2000 + 'needle ' + 'word ' * 2000
    store.import_conversations([
        CanonicalConversation('chatgpt', 'c', 'Synthetic', (
            CanonicalMessage('chatgpt', 'c', 'm', 'user', content),
        )),
    ], source_id=source.id)
    hit, = store.search('needle')
    assert 'needle' in hit['snippet']
    assert hit['snippet_truncated'] is False
    assert hit['content_length'] > len(hit['snippet'])


def test_multiterm_window_retains_first_selected_match_not_every_term(tmp_path):
    store = ArchiveStore(tmp_path / 'a.sqlite3')
    export = tmp_path / 'export.json'
    export.write_text('[]')
    source = store.ingest_source(export, 'chatgpt')
    content = 'x' * 5000 + ' needle ' + 'y' * 5000 + ' thread tail'
    store.import_conversations([
        CanonicalConversation('chatgpt', 'c', 'Synthetic', (
            CanonicalMessage('chatgpt', 'c', 'm', 'user', content),
        )),
    ], source_id=source.id)
    hit, = store.search('needle thread')
    assert len(hit['snippet']) <= 1024
    assert 'needle' in hit['snippet']
    assert hit['snippet_truncated'] is True
    # Both separated matches cannot fit in any character-bounded window.
    assert not ('needle' in hit['snippet'] and 'thread' in hit['snippet'])
