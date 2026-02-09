"""Fuzzy string matching for resource name search"""

from rapidfuzz import fuzz, process
from typing import List, Tuple


def fuzzy_match_names(query: str, resources: List[dict],
                      threshold: int = 70) -> List[Tuple[dict, float]]:
    """
    Fuzzy match query against resource names.

    Args:
        query: Search query
        resources: List of resource dicts (must have 'name' field)
        threshold: Minimum similarity score (0-100)

    Returns: [(resource, score)] sorted by score descending
    """
    # Extract names
    names = [r.get('name', '') for r in resources]
    name_to_resource = {r.get('name'): r for r in resources}

    # Use WRatio for partial matching
    results = process.extract(
        query,
        names,
        scorer=fuzz.WRatio,
        limit=20,
        score_cutoff=threshold
    )

    # Map back to resources with normalized scores
    matches = [
        (name_to_resource[name], score / 100.0)
        for name, score, _ in results
    ]

    return matches


def fuzzy_match_multi_algorithm(query: str, resources: List[dict],
                                threshold: int = 60) -> List[Tuple[dict, float]]:
    """
    Multi-algorithm fuzzy matching for better recall.

    Combines:
    - WRatio: Good for partial matches
    - Partial ratio: Good for substrings
    - Token set ratio: Good for word order variations
    """
    names = [r.get('name', '') for r in resources]
    name_to_resource = {r.get('name'): r for r in resources}

    scores = {}

    # WRatio (primary)
    for name, score, _ in process.extract(query, names,
                                          scorer=fuzz.WRatio,
                                          limit=None,
                                          score_cutoff=threshold):
        scores[name] = max(scores.get(name, 0), score)

    # Partial ratio (for substrings like "fir" → "Fireball")
    for name, score, _ in process.extract(query, names,
                                          scorer=fuzz.partial_ratio,
                                          limit=None,
                                          score_cutoff=threshold):
        scores[name] = max(scores.get(name, 0), score)

    # Sort and return top 20
    matches = [
        (name_to_resource[name], score / 100.0)
        for name, score in sorted(scores.items(),
                                  key=lambda x: x[1],
                                  reverse=True)[:20]
    ]

    return matches
