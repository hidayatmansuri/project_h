"""
Management command `projectauth_check` (Section 9):
Walks every URL pattern in `get_resolver()`, resolves its owning app and classification
(public / protected / unclassified), prints a table, and exits non-zero if any route
is unclassified.
"""

from __future__ import annotations

from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.urls import URLPattern, URLResolver, get_resolver

from projectauth.access import classify_app_label, resolve_view_app_label


def iter_url_patterns(
    patterns,
    prefix: str = "",
    namespace: str = "",
    app_name: str = "",
) -> List[Tuple[str, object, str, str]]:
    """
    Recursively walks URLResolver and URLPattern objects.
    Returns list of (full_pattern_str, callback, namespace, app_name).
    """
    items: List[Tuple[str, object, str, str]] = []
    for entry in patterns:
        pattern_str = str(entry.pattern)
        combined = (prefix + pattern_str).lstrip("^")
        if not combined.startswith("/"):
            combined = "/" + combined

        if isinstance(entry, URLResolver):
            ns = entry.namespace or namespace
            an = entry.app_name or app_name
            items.extend(
                iter_url_patterns(
                    entry.url_patterns,
                    prefix=combined,
                    namespace=ns,
                    app_name=an,
                )
            )
        elif isinstance(entry, URLPattern):
            items.append((combined, entry.callback, namespace, app_name))
    return items


class _DummyMatch:
    def __init__(self, app_name: str, namespace: str):
        self.app_name = app_name
        self.namespace = namespace


class Command(BaseCommand):
    help = "Print every URL pattern with its resolved app and classification (public / protected / unclassified)."

    def handle(self, *args, **options):
        resolver = get_resolver()
        entries = iter_url_patterns(resolver.url_patterns)
        unclassified: List[str] = []

        self.stdout.write(f"{'CLASSIFICATION':<14} {'APP':<18} {'PATTERN'}")
        self.stdout.write("-" * 78)

        for full_pattern, callback, ns, an in entries:
            match = _DummyMatch(app_name=an, namespace=ns)
            app_label = resolve_view_app_label(
                callback,
                path=full_pattern,
                resolver_match=match,
            )
            classification = classify_app_label(app_label)
            self.stdout.write(
                f"{classification:<14} {(app_label or 'NONE'):<18} {full_pattern}"
            )
            if classification == "unclassified":
                unclassified.append(full_pattern)

        self.stdout.write("-" * 78)
        if unclassified:
            raise CommandError(
                f"Found {len(unclassified)} unclassified URL pattern(s): {', '.join(unclassified)}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"All {len(entries)} URL pattern(s) classified cleanly (0 unclassified)."
            )
        )

