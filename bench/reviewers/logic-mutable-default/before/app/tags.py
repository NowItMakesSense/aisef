def add_tag(tag: str, tags=None) -> list:
    tags = list(tags or [])
    if tag not in tags:
        tags.append(tag)
    return tags
