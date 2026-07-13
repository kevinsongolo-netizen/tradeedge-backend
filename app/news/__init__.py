"""News / economic calendar filter (Sprint 12 — Market Context Filters).

Same pluggable-provider pattern as ``app/chart/vision_provider.py``:
``get_calendar_provider()`` is the single factory/switch point.
``PlaceholderCalendarProvider`` (clearly-labeled example events) is
active whenever no ``FINNHUB_API_KEY`` is configured; the moment a key
is set, ``FinnhubCalendarProvider`` takes over with zero other code
changes. ``app/news/news_filter_engine.py`` is a pure function that
knows nothing about HTTP or any specific provider — it just evaluates
a list of already-fetched events against a planned trade time, the
same "engines never touch I/O" convention used throughout this app.
"""
