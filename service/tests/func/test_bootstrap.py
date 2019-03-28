from sh import cornac


def test_help():
    out = cornac("--help")
    assert 'migratedb' in out
    assert 'worker' in out


def test_bootstrap(cornac_env):
    cornac("--verbose", "bootstrap", _err_to_out=True, _env=cornac_env)


def test_recover(iaas, cornac_env):
    iaas.stop_machine('cornac')
    cornac("--verbose", "recover", _err_to_out=True, _env=cornac_env)
