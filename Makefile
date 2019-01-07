default:

%:
	@echo You should use appliance/ Makefile instead. >&2
	$(MAKE) -C appliance/ $@
