"""Route registration helpers for the combined stats/admin Flask app."""

from .charts import register_charts_routes
from .deviation_comments import register_deviation_comment_routes
from .mass_fave import register_mass_fave_routes
from .pages import register_pages_routes
from .profile_messages import register_profile_message_routes
from .stats import register_stats_routes
from .thumbnails import register_thumbnail_routes
from .upload_admin import register_upload_admin_routes

__all__ = [
    "register_charts_routes",
    "register_deviation_comment_routes",
    "register_mass_fave_routes",
    "register_pages_routes",
    "register_profile_message_routes",
    "register_stats_routes",
    "register_thumbnail_routes",
    "register_upload_admin_routes",
]
