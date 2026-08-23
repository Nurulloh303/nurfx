import sys

# Python 3.14 compatibility patch for Django BaseContext.__copy__
if sys.version_info >= (3, 14):
    try:
        import django.template.context
        def _base_context_copy(self):
            duplicate = object.__new__(self.__class__)
            duplicate.__dict__.update(self.__dict__)
            duplicate.dicts = self.dicts[:]
            return duplicate
        django.template.context.BaseContext.__copy__ = _base_context_copy
    except Exception:
        pass

from .celery import app as celery_app

__all__ = ("celery_app",)

