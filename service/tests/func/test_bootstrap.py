from sh import cornac


def test_help():
    out = cornac("--help")
    assert 'migratedb' in out
    assert 'worker' in out


def test_bootstrap():
    cornac("--verbose", "bootstrap", _err_to_out=True)
