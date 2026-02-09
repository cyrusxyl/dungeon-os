"""Text search in resource descriptions and abilities"""

from typing import List


def extract_searchable_text(data: dict, resource_type: str) -> str:
    """
    Extract all searchable text from a resource.

    Args:
        data: Resource data (monster, spell, equipment)
        resource_type: Type of resource

    Returns: Combined searchable text
    """
    texts = [data.get('name', '')]

    if resource_type == 'monsters':
        # Add special abilities
        for ability in data.get('special_abilities', []):
            texts.append(ability.get('name', ''))
            texts.append(ability.get('desc', ''))

        # Add actions
        for action in data.get('actions', []):
            texts.append(action.get('name', ''))
            texts.append(action.get('desc', ''))

        # Add legendary actions
        for action in data.get('legendary_actions', []):
            texts.append(action.get('name', ''))
            texts.append(action.get('desc', ''))

    elif resource_type == 'spells':
        # Add descriptions
        if isinstance(data.get('desc'), list):
            texts.extend(data.get('desc', []))
        else:
            texts.append(str(data.get('desc', '')))

        # Add higher level
        if isinstance(data.get('higher_level'), list):
            texts.extend(data.get('higher_level', []))

        # Add material component
        texts.append(data.get('material', ''))

        # Add school
        texts.append(data.get('school', {}).get('name', ''))

    elif resource_type == 'equipment':
        # Equipment has minimal text
        if isinstance(data.get('desc'), list):
            texts.extend(data.get('desc', []))

        # Add weapon properties
        for prop in data.get('properties', []):
            texts.append(prop.get('name', ''))

    # Combine and clean
    combined = ' '.join(str(t) for t in texts if t)
    return combined.lower()


def text_search(query: str, resources: List[dict],
                resource_type: str) -> List[dict]:
    """
    Search for query in resource text fields.

    Args:
        query: Search query (case-insensitive)
        resources: List of resources to search
        resource_type: Type of resource (for field extraction)

    Returns: Resources containing query text
    """
    query_lower = query.lower()
    matches = []

    for resource in resources:
        searchable_text = extract_searchable_text(resource, resource_type)

        if query_lower in searchable_text:
            matches.append(resource)

    return matches


def multi_keyword_search(keywords: List[str], resources: List[dict],
                        resource_type: str, require_all: bool = False) -> List[dict]:
    """
    Search for multiple keywords.

    Args:
        keywords: List of keywords to search for
        resources: Resources to search
        resource_type: Type of resource
        require_all: If True, resource must contain ALL keywords (AND)
                    If False, resource must contain ANY keyword (OR)
    """
    matches = []

    for resource in resources:
        searchable_text = extract_searchable_text(resource, resource_type)

        if require_all:
            # AND logic
            if all(kw.lower() in searchable_text for kw in keywords):
                matches.append(resource)
        else:
            # OR logic
            if any(kw.lower() in searchable_text for kw in keywords):
                matches.append(resource)

    return matches
