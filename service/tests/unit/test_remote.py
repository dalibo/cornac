def test_password():
    from cornac.ssh import Password

    my = Password('secret')

    assert 'secret' not in str(my)
    assert 'secret' not in repr(my)
