NAME=cornac
ANSIBLE_INVENTORY?=inventory.d
BUILDDIR=build/

default:

RSYNC=rsync --exclude-from=distignore --recursive --update
.PHONY: build
build:
	mkdir -p $(BUILDDIR)
	$(RSYNC) ./ $(BUILDDIR)/
	if [ -n "$(ANSIBLE_INVENTORY)" ] ; then $(RSYNC) $(ANSIBLE_INVENTORY)/ $(BUILDDIR)/inventory.d/; fi
