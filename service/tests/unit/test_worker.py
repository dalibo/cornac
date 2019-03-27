import pytest


def test_actor_error(caplog, mocker):
    mocker.patch('cornac.worker.dramatiq.actor', lambda fn: fn)

    from cornac.worker import actor, KnownError, TaskStop

    @actor
    def myactor(param=None):
        if isinstance(param, Exception):
            raise param
        else:
            return param

    myactor()
    assert 1 == myactor(1)

    assert myactor(Exception()) is None
    assert 'Unhandled' in caplog.records[-1].message

    assert myactor(KnownError("pouet")) is None
    assert 'Unhandled' not in caplog.records[-1].message

    assert myactor(TaskStop()) is None


def test_state_manager(mocker):
    mocker.patch('cornac.worker.db')
    from cornac.worker import state_manager, KnownError

    instance = mocker.Mock(name='instance')

    # Return instance and set to available
    with state_manager(instance) as ctx:
        assert ctx is instance
    assert 'available' == instance.status

    # Check instance status.
    instance.status = 'available'
    with pytest.raises(KnownError):
        with state_manager(instance, from_='creating') as ctx:
            assert ctx is instance

    # Set to custom state.
    with state_manager(instance, to_='funky') as ctx:
        assert ctx is instance
    assert 'funky' == instance.status

    # Set to failed state and reraise.
    with pytest.raises(KnownError):
        with state_manager(instance) as ctx:
            raise KnownError("Error")
    assert 'failed' == instance.status
