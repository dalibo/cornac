#!/bin/bash -eu
#
#: Usage: vhelper.sh <command> [ARG ...]
#:
#: Set of scripts to manage VM.
#
# See helper.sh help for more information
#

export LC_ALL=en_US.utf8

_log() {
	echo "$@" >&2
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


pwgen() {
	#: Generate a random password.
	od -vN 16 -An -tx1 /dev/urandom | tr -d ' \n'
}

sysprep() {
	#: Refresh system after clone.

	# Inspired by virt-sysprep
	# (https://github.com/libguestfs/libguestfs/tree/master/sysprep)

	_log "Cleaning files and logs."
	rm -rf \
	   /etc/machine-id \
	   /etc/ssh/*_host_* \
	   /root/.bash_history /home/*/.bash_history \
	   /var/lib/rpm/__db* \
	   /var/lib/yum/uuid \
	   /var/log/anaconda \
	   /var/log/audit/audit.log \
	   /var/log/boot.log* \
	   /var/log/cron \
	   /var/log/dmesg* \
	   /var/log/grubby_prune_debug \
	   /var/log/maillog \
	   /var/log/messages \
	   /var/log/secure \
	   /var/log/wtmp \
	   /var/log/tuned/tuned.log \
	   /var/log/vmware-network*.log \
	   /var/log/yum.log \
	   ${NULL-}

	_log "Restarting SSHd"
	systemctl restart sshd

	_log "Randomizing root password."
	echo "root:$(pwgen)" | chpasswd
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
