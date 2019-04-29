#!/bin/bash -eu

if getent passwd cornac-worker &>/dev/null ; then
	userdel --force cornac-worker
fi

if getent passwd cornac-web &>/dev/null ; then
	userdel --force cornac-web
fi

if getent group cornac-web &>/dev/null ; then
	groupdel cornac-web
fi

rm -rf \
   /usr{,/local}/lib/systemd/system/cornac-{web,worker}.service \
   /etc/opt/cornac \
   /opt/cornac \
   ${NULL-}

systemctl daemon-reload
