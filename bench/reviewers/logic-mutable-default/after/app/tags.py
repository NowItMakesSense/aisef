def add_tag(tag: str, tags=[]) -> list:
    if tag not in tags:
        tags.append(tag)
    return tags
