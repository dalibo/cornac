from textwrap import dedent

import pytest


def test_append_creds():
    from cornac.core.config.writer import append_credentials

    config = ""
    with pytest.raises(ValueError):
        append_credentials(config, 'K', 'S')

    config = "CREDENTIALS = 'string'"
    with pytest.raises(ValueError):
        append_credentials(config, 'K', 'S')

    config = "CREDENTIALS = {}"
    new = append_credentials(config, 'K', 'S', comment=None)
    wanted = dedent("""\
    CREDENTIALS = {
        'K': 'S',
    }
    """)
    assert wanted == str(new)

    config = dedent("""\
    CREDENTIALS = {
        # before comment
        'OLDKEY': 'OLDSECRET'  # line comment
        # end comment
    }
    """)
    new = append_credentials(config, 'KEY', 'SECRET', comment='new comment')
    wanted = dedent("""\
    CREDENTIALS = {
        # before comment
        'OLDKEY': 'OLDSECRET',  # line comment
        # end comment
        # new comment
        'KEY': 'SECRET',
    }
    """)
    assert wanted == str(new)
