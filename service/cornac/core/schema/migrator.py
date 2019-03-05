#
# The migrator manage schema and data migration across cornac versions.
#
# A migration is a file in versions/ directory. Filename *is* the version
# identifier. Versions are sorted using POSIX C sort collation. The
# migration_log table keep track of latest version. Only files sorting after
# the latest version are required. This allow to squash versions to speed
# bootstrap at the cost of dropping intermediate migration.
#
# See cornac migratedb command for usage.
#

import logging
import os
from glob import glob
from textwrap import dedent

import psycopg2.errorcodes


logger = logging.getLogger(__name__)


class Migrator(object):
    versionsdir = os.path.dirname(__file__)

    def __init__(self):
        self.current_version = None
        self.versions = []

    @property
    def target_version(self):
        return self.versions[-1]

    @property
    def missing_versions(self):
        try:
            i = self.versions.index(self.current_version)
        except ValueError:
            return self.versions
        else:
            return self.versions[i + 1:]

    def inspect_current_version(self, conn):
        try:
            with conn.cursor() as cur:
                cur.execute(dedent("""\
                SELECT version
                FROM schema_migration_log
                ORDER BY version DESC
                LIMIT 1;
                """))
                row = cur.fetchone()
            self.current_version = row[0]
        except psycopg2.Error as e:
            conn.rollback()
            if e.pgcode != psycopg2.errorcodes.UNDEFINED_TABLE:
                raise
        return self.current_version

    def inspect_available_versions(self):
        self.versions = sorted(
            [os.path.basename(f) for f in glob(self.versionsdir + "/*.sql")]
        )

    def apply(self, pg, version):
        path = os.path.join(self.versionsdir, version)
        with open(path) as fo:
            sql = fo.read()
        with pg.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migration_log (version) VALUES (%s);",
                (version,),
            )
