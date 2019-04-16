def test_version(capsys, mocker):
    from cornac.cli import get_version

    ctx = mocker.Mock(name='ctx', resilient_parsing=False)
    get_version(ctx=ctx, param='version', value=True)
    out, _ = capsys.readouterr()
    assert 'Cornac' in out
    assert 'Flask 1.' in out
    assert 'Python 3.' in out
    assert 'Werkzeug' in out
    assert 'Bjoern' in out
