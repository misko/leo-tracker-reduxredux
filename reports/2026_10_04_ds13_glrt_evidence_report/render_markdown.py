"""Small renderer for this report's HTML vocabulary, with portable asset links."""
from html.parser import HTMLParser
import html
import re


class Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []


class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'img', 'br', 'meta', 'link', 'hr', 'input'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def descendants(node, tag):
    for child in node.children:
        if isinstance(child, Node):
            if child.tag == tag:
                yield child
            else:
                yield from descendants(child, tag)


def plain(node):
    if isinstance(node, str):
        return node
    return ''.join(plain(c) for c in node.children)


def render(node):
    if isinstance(node, str):
        return re.sub(r'\s+', ' ', node)
    tag, attrs = node.tag, node.attrs
    if tag in {'head', 'style', 'script'}:
        return ''
    anchor = f'\n\n<a id="{html.escape(attrs["id"], quote=True)}"></a>\n\n' if 'id' in attrs else ''
    if tag == 'div' and attrs.get('class') == 'flow':
        steps = [' '.join(render(c).strip() for c in child.children)
                 for child in node.children if isinstance(child, Node)]
        return '\n\n' + '\n\n'.join(steps) + '\n\n'
    if tag == 'figure':
        name = attrs['id'].removeprefix('fig-')
        img = next(descendants(node, 'img'))
        caption = next(descendants(node, 'figcaption'))
        alt = img.attrs['alt'].replace('[', r'\[').replace(']', r'\]')
        return anchor + f'![{alt}](assets/{name}.png)\n\n' + render(caption) + '\n\n'
    if tag == 'pre':
        return '\n\n```text\n' + plain(node).strip() + '\n```\n\n'
    if tag == 'table':
        rows = []
        for row in descendants(node, 'tr'):
            cells = [render(c).strip().replace('|', r'\|').replace('\n', '<br>')
                     for c in row.children if isinstance(c, Node) and c.tag in {'th', 'td'}]
            rows.append('| ' + ' | '.join(cells) + ' |')
        if not rows:
            return ''
        width = len([c for c in next(descendants(node, 'tr')).children
                     if isinstance(c, Node) and c.tag in {'th', 'td'}])
        rows.insert(1, '| ' + ' | '.join(['---']*width) + ' |')
        return '\n\n' + '\n'.join(rows) + '\n\n'
    if tag in {'ul', 'ol'}:
        items = [c for c in node.children if isinstance(c, Node) and c.tag == 'li']
        return '\n\n' + '\n'.join((f'{i}. ' if tag == 'ol' else '- ') + render(c).strip()
                                  for i, c in enumerate(items, 1)) + '\n\n'
    value = ''.join(render(c) for c in node.children)
    if tag == 'span' and attrs.get('class') == 'value':
        return '**' + value.strip() + '** — '
    if tag in {'h1', 'h2', 'h3', 'h4'}:
        return anchor + '\n\n' + '#'*int(tag[1]) + ' ' + value.strip() + '\n\n'
    if tag == 'summary':
        return '\n\n### ' + value.strip() + '\n\n'
    if tag in {'strong', 'b'}:
        return '**' + value.strip() + '**'
    if tag in {'em', 'i'}:
        return '*' + value.strip() + '*'
    if tag == 'code':
        return '`' + plain(node) + '`'
    if tag in {'sub', 'sup'}:
        return f'<{tag}>' + value + f'</{tag}>'
    if tag == 'a':
        target = attrs.get('href', '')
        if 'download' in attrs:
            name = attrs['download']
            target = ('sources/' if name.endswith('.py') else 'evidence/') + name
        return f'[{value.strip()}]({target})'
    if tag == 'br':
        return ' '
    if tag in {'p', 'div', 'section', 'header', 'footer', 'nav', 'details'}:
        return anchor + '\n\n' + value.strip() + '\n\n'
    return anchor + value


def markdown(source):
    text = render(Tree(source).root)
    parts = re.split(r'(```text\n.*?\n```)', text, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'\n[ \t]+', '\n', parts[i])
        parts[i] = re.sub(r'[ \t]+\n', '\n', parts[i])
        parts[i] = re.sub(r'\n{3,}', '\n\n', parts[i])
    return ''.join(parts).strip() + '\n'
