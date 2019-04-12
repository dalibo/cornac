import csv
import os.path
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


def test_generate_credentials(cornac_env):
    path = "tests-func-tmp-config.py"
    if os.path.exists(path):
        os.unlink(path)

    env = dict(cornac_env, CORNAC_CONFIG=path)
    out = cornac("--verbose", "generate-credentials", "--save", _env=env)

    reader = csv.reader(out.splitlines())
    lines = list(reader)
    assert 2 == len(lines)
    _, _, access_key, secret_key, *_ = lines[1]

    with open(path, 'r') as fo:
        config = fo.read()

    assert repr(access_key) in config
    assert repr(secret_key) in config
