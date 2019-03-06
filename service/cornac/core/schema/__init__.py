#
# cornac.core.schema package groups code and data to manage cornac's database
# schemas and data. See cornac.core.models for objects to query database using
# SQLAlchemy.
#

from .migrator import Migrator


__all__ = ['Migrator']
