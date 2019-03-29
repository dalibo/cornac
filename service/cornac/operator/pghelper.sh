#!/bin/bash -eu
#
#: Usage: helper.sh <command> [ARG ...]
#:
#: Opinionated helper to manage Postgres.
#
# Manage a single instance host with hardcoded value.
#
# The instance is named `Managed Postgres`. It's data are all in a disk with
# data and wal isolated in logical volumes. Volumes are mounted at
# ~postgres/managed/{data,wal}_mnt/. A systemd service called `postgres-managed`
# is configured.
#
# See helper.sh help for more information
#

export LC_ALL=en_US.utf8

_log() {
	echo "$@" >&2
}

clean-disk() {
	#: Unmount and destroy volumes. Reset disk partition table.

	local dev=$(readlink -e $1); shift

	if ! [ -b "$dev" ] ; then
		_log "Disk $dev not found."
		return 1
	fi

	for volume in /dev/mapper/Postgres-{DATA,LOG,WAL} ; do
		if mount | grep -q $volume ; then
			umount $volume
		fi
	done
	sed -i~ /Postgres-/d /etc/fstab
	if [ -d /dev/Postgres ] ; then
		vgremove -qq --force Postgres
	fi
	dd if=/dev/zero of=$dev bs=513 count=64
	rm -rf ~postgres/managed
	_log "$dev cleaned."
}


create-database() {  #: <NAME> <OWNER> [CREATEDB_ARG ...]
	#: Create database with some defaults.
	local name=$1; shift
	local owner=$1; shift
	sudo -iu postgres createdb --locale en_US.UTF-8 -O "${owner}" "$@" "${name}"
}


create-masteruser() {  #: <NAME> <PASSWORD> [CREATEUSER_ARG ...]
	#: Create or update master user. Assign all databases to it.
	local name=$1; shift
	local password=$1; shift

	# Naïve escape of parameters
	printf -v name_e "%q" "${name}"
	password_e="${password/\'/''}"

	if ! psql -tc "SELECT 'EXISTS' FROM pg_roles WHERE rolname = '${name_e}';" | grep -q EXISTS ; then
		sudo -iu postgres createuser --no-createdb --superuser "$@" "$name"
	fi

	psql <<-EOF
	ALTER ROLE "${name_e}" WITH PASSWORD '${password_e}';
	EOF

	for dbname in $(psql -tc 'SELECT datname FROM pg_database WHERE datistemplate IS FALSE;'); do
		echo "ALTER DATABASE "'"'"${dbname}"'"'" OWNER TO "'"'"${name_e}"'"'";"
	done | psql
}


create-instance() {  #: <VERSION>
	#: Initialize and enable the managed Postgres instance.
	local pgversion=$1; shift

	local bindir=/usr/pgsql-$pgversion/bin
	if ! [ -d $bindir ] ; then
		_log "Unknown version $pgversion."
		return 1
	fi

	PGDATA=$(readlink -m ~postgres/managed/data_mnt/data)
	PGWAL=$(readlink -m ~postgres/managed/wal_mnt/wal)
	mkdir --parent $PGDATA $PGWAL
	chown -R postgres: ~postgres/managed
	sudo -iu postgres $bindir/initdb \
	     --auth-local peer \
	     --auth-host md5 \
	     --pgdata $PGDATA \
	     --locale en_US.UTF-8 \
	     --waldir $PGWAL \
	     ${NULL-}

	cat >> $PGDATA/postgresql.conf <<-EOF
	include_dir 'conf.d'
	EOF
	_log "Accepting connection from world."
	sed -i s,127.0.0.1/32,0.0.0.0/0,g $PGDATA/pg_hba.conf
	sudo -iu postgres mkdir -p $PGDATA/conf.d
	sudo -iu postgres tee $PGDATA/conf.d/00-managed.conf >/dev/null <<-EOF
	#
	# Managed file. Don't edit manually.
	#
	archive_command = '/bin/true'
	archive_mode = on
	checkpoint_completion_target = 0.9
	default_transaction_isolation = 'read committed'
	hot_standby = on
	lc_messages = C
	listen_addresses = '*'
	log_autovacuum_min_duration = 0
	log_checkpoints = on
	log_connections = on
	log_destination = 'syslog'
	log_disconnections = on
	log_line_prefix = '[%p]: [%l-1] db=%d,user=%u,app=%a,client=%h '
	log_lock_waits = on
	log_min_duration_statement = 3s
	log_min_messages = notice
	log_statement = ddl
	log_temp_files = 0
	logging_collector = off
	pg_stat_statements.max = 10000
	pg_stat_statements.track = all
	shared_preload_libraries = pg_stat_statements
	syslog_facility = 'local0'
	wal_level = hot_standby
	EOF

	_log "Setting up systemd service."
	cat >/etc/systemd/system/postgres-managed.service <<-EOF
	[Unit]
	Description=Managed PostgreSQL $pgversion database server
	Documentation=https://www.postgresql.org/docs/$pgversion/static/
	After=syslog.target
	After=network.target

	[Service]
	Type=notify

	User=postgres
	Group=postgres

	# Note: avoid inserting whitespace in these Environment= lines, or you may
	# break postgresql-setup.

	# Location of database directory
	Environment=PGDATA=${PGDATA}

	# Where to send early-startup messages from the server (before the logging
	# options of postgresql.conf take effect)
	# This is normally controlled by the global default set by systemd
	# StandardOutput=syslog

	# Disable OOM kill on the postmaster
	OOMScoreAdjust=-1000
	Environment=PG_OOM_ADJUST_FILE=/proc/self/oom_score_adj
	Environment=PG_OOM_ADJUST_VALUE=0

	ExecStartPre=$bindir/postgresql-$pgversion-check-db-dir \${PGDATA}
	ExecStart=$bindir/postmaster -D \${PGDATA}
	ExecReload=/bin/kill -HUP \$MAINPID
	KillMode=mixed
	KillSignal=SIGINT

	[Install]
	WantedBy=multi-user.target
	EOF
	systemctl daemon-reload
	systemctl enable postgres-managed.service

	_log "Opening port 5432."
	firewall-cmd --quiet --zone public --add-port "5432/tcp" --permanent
	firewall-cmd --quiet --reload

	_log "Managed instance created."
}


delete-db-instance() {
	#: Reset managed instance service and data. All data are lost.

	if systemctl is-active postgres-managed.service >&/dev/null ; then
		_log "Deleting systemd unit."
		systemctl stop postgres-managed.service
		systemctl disable postgres-managed.service
		systemctl reset-failed postgres-managed.service ||:
	fi
	rm -f /etc/systemd/system/postgres-managed.service \
	   systemctl daemon-reload

	_log "Deleting files and directory."
	rm -rf ~postgres/managed/*_mnt/{data,wal}

	_log "Managed instance deleted."
}

help() {
	#: Show this message.

	sed -n '/^#:/{s,#: \?,,;p}' $0 >&2

	local commands=$(grep -Po '^([^_].*)(?=\(\) \{)' $0 | sort)

	_log
	_log "AVAILABLE COMMANDS:"
	for comm in $commands ; do
		_log
		_log $comm $(grep -Po "$comm\(\\) \{  #: \K.+" $0)
		sed -n /^$comm/,/^\}/p $0 | sed -n '/\t#:/{s,#: \?,,;p}' >&2
	done
}

prepare-disk() {  #: <DEVICE>
	#: Partition, format and mount disk for managed instance.
	local dev=$(readlink -m $1); shift
	if ! [ -b "$dev" ] ; then
	    _log "Disk $dev not found."
	    return 1
	fi

	if sfdisk --dump $dev | grep -q . ; then
	    _log "Disk already partitionned."
	    return 1
	fi

	total_sectors=$(blockdev --getsz $dev)
	part_sectors=$((total_sectors - 63))
	_log "Writing partition table."
	# Force because we are using virtual disk.
	sfdisk --force $dev >&2 <<-EOF
	unit: sectors

	/dev/vdb1 : start=       63, size= ${part_sectors}, Id=8e
	EOF

	_log "Waiting for block device to appear."
	sleep 1
	part=${dev}1
	if ! [ -b "$part" ] ; then
		_log "Failed to get partition."
		return 1
	fi

	_log "Creating logical volumes."
	pvcreate $part
	vgcreate Postgres $part
	lvcreate --yes --name "DATA" --extents 90%VG Postgres
	lvcreate --yes --name "WAL" --extents 10%VG Postgres

	_log "Formatting logical volumes."
	mkfs.ext4 -q -m 1 -U $(uuidgen) -L "Postgres Data" /dev/mapper/Postgres-DATA
	mkfs.ext4 -q -m 1 -U $(uuidgen) -L "Postgres WAL"  /dev/mapper/Postgres-WAL

	local home=$(readlink -e ~postgres)
	_log "Mounting volumes in $home/managed"
	mkdir -p --mode 0750 $home/managed/{data,wal}_mnt/
	chown -R postgres: ~postgres/managed
	cat >>/etc/fstab <<-EOF
	/dev/mapper/Postgres-DATA	$home/managed/data_mnt	ext4	defaults	0	0
	/dev/mapper/Postgres-WAL	$home/managed/wal_mnt	ext4	defaults	0	0
	EOF

	mount $home/managed/data_mnt
	mount $home/managed/wal_mnt
}

psql() {  #: [PSQL_ARG ...]
	#: Execute psql on managed instance.
	sudo -iu postgres psql --no-password --set ON_ERROR_STOP=1 --quiet "$@"
}

start() {
	#: Starts Postgres managed instance
	systemctl start postgres-managed.service
	systemctl status postgres-managed.service
}




cmd=help
if [ -n "${1-}" ] ; then
	cmd=$1; shift
fi

if type -t ${cmd} | grep -q function ; then
	$cmd "$@"
else
	echo "Unknown command $1." >&2
	exit 1
fi
