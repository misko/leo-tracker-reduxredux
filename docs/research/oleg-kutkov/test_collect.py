from audit import classify
from collect import Content, normalize
from enrich import topic_id
from supplement import literals


def test_relative_assets_and_srcset_are_cataloged():
    parser = Content()
    parser.feed('<a href="/a.pdf#page=2">paper</a><img srcset="a.jpg 1x, b.jpg 2x">')
    assert parser.links == {'/a.pdf#page=2', 'a.jpg', 'b.jpg'}
    assert normalize('/a.pdf#page=2', 'https://olegkutkov.me/post/') == 'https://olegkutkov.me/a.pdf'
    assert normalize('javascript:alert(1)', 'https://olegkutkov.me/') is None


def test_forum_pagination_preserves_topic_and_rejects_actions():
    assert topic_id('https://olegkutkov.me/forum/index.php?topic=57.20') == '57'
    assert topic_id('https://olegkutkov.me/forum/index.php?topic=58.0') != '57'
    assert topic_id('https://olegkutkov.me/forum/index.php?action=logout') is None
    assert topic_id('https://other.example/forum/index.php?topic=57.0') is None


def test_x_literal_extraction_does_not_execute_code():
    raw = 'full_text:"A\\nB",full_text:danger(),full_text:"A\\nB"'
    assert literals(raw, 'full_text') == ['A\nB']


def test_challenge_page_is_not_counted_as_a_datasheet():
    assert classify('https://example.com/data.pdf', b'<html>Blocked</html>') == (
        'invalid-pdf-response')
    assert classify('https://example.com/data.pdf', b'%PDF-1.4\n') == 'PDF'
    assert classify('https://x.com/search?q=test', b'<html>Login</html>') == (
        'X-search-without-posts')
    assert classify('https://www.youtube.com/api/timedtext', b'') == 'empty-response'
