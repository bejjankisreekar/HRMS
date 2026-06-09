"""Static-file helpers for templates."""
import os

from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """Like {% static %} but appends the file's modification time as ?v=<mtime>.

    The version changes whenever the file changes, so browsers always fetch a
    fresh copy after an edit instead of serving a stale cached version.
    """
    url = static(path)
    mtime = None
    abs_path = finders.find(path)
    if abs_path and os.path.exists(abs_path):
        mtime = int(os.path.getmtime(abs_path))
    else:
        # Production / collected static: fall back to the storage's modified time.
        try:
            mtime = int(staticfiles_storage.get_modified_time(path).timestamp())
        except Exception:
            mtime = None
    if mtime is not None:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}v={mtime}"
    return url
