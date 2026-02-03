import re, json

def parse_json(filename):
    """Remove //-- and /* -- */ style comments from JSON"""
    comment_re = re.compile(
        r'(^)?[^\S\n]*/(?:\*(.*?)\*/[^\S\n]*|/[^\n]*)($)?',
        re.DOTALL | re.MULTILINE
    )

    with open(filename, encoding="utf-8") as f:
        content = f.read()

    # Remove comments
    match = comment_re.search(content)
    while match:
        content = content[:match.start()] + content[match.end():]
        match = comment_re.search(content)

    contents = json.loads(content)

    # Backwards compatibility
    if "data" in contents:
        contents = contents["data"][0]

    return contents
