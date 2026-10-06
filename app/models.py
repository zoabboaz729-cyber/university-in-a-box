"""Data-model reference for Phase 0.

The authoritative schema lives in app/schema.sql. This module only lists the
table names so code and tests can assert the DB was created completely,
without hardcoding table names in multiple places.
"""

TABLE_NAMES = [
    "users",
    "course_groups",
    "courses",
    "topics",
    "advisor_interviews",
    "sources",
    "tutor_sessions",
    "tutor_turns",
    "editor_reviews",
    "roommate_prompts",
    "_dash_visits",
    "activity_log",
]
