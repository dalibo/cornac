import functools
import logging
from contextlib import contextmanager

from flask import current_app
from flask_dramatiq import Dramatiq

from .core.config import require_ssh_key
from .core.model import DBInstance, db
from .errors import KnownError
from .iaas import IaaS
from .operator import BasicOperator
from .ssh import wait_machine


dramatiq = Dramatiq()
logger = logging.getLogger(__name__)


class TaskStop(Exception):
    # Exception raised to return task, from anywhere in the stack. e.g. the
    # task is now irrelevant.
    pass


def actor(fn):
    # Declare and wraps a background task function.

    @dramatiq.actor
    @functools.wraps(fn)
    def actor_wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except TaskStop as e:
            logger.info("%s", e)
        except KnownError as e:
            logger.error("Task failed: %s", e)
        except Exception:
            logger.exception("Unhandled error in task:")

        # Swallow errors so that Dramatiq don't retry task. We want Dramatiq to
        # retry task only on SIGKILL.

    return actor_wrapper


def get_instance(instance):
    if isinstance(instance, int):
        instance = DBInstance.query.get(instance)
        if not instance:
            raise TaskStop(f"Unknown instance {instance}.")
    logger.info("Working on %s.", instance)
    return instance


@contextmanager
def state_manager(instance, from_=None, to_='available'):
    # Manage the state of an instance, when working with a single instance.
    # Checks if instance status matches from_. On success, instance status is
    # defined as to_. On error, the instance state is set to failed. SQLAlchemy
    # db session is always committed.

    instance = get_instance(instance)

    if from_ and from_ != instance.status:
        raise KnownError(f"{instance} is not in state {from_}.")

    try:
        yield instance
    except TaskStop:
        # Don't touch instance.
        pass
    except Exception as e:
        instance.status = 'failed'
        instance.status_message = str(e)
        raise
    else:
        instance.status = to_
        instance.status_message = None
    finally:
        db.session.commit()


@actor
def create_db(instance_id):
    require_ssh_key()
    config = current_app.config
    with state_manager(instance_id, from_='creating') as instance:
        with IaaS.connect(config['IAAS'], config) as iaas:
            operator = BasicOperator(iaas, current_app.config)
            response = operator.create_db_instance(instance.data)

        instance.status = 'available'
        instance.data = dict(
            instance.data,
            # Drop password from data.
            MasterUserPassword=None,
            **response,
        )


@actor
def delete_db_instance(instance_id):
    config = current_app.config
    with state_manager(instance_id, from_='deleting') as instance:
        logger.info("Deleting %s.", instance)
        with IaaS.connect(config['IAAS'], config) as iaas:
            iaas.delete_machine(instance.identifier)
        db.session.delete(instance)


@actor
def inspect_instance(instance_id):
    require_ssh_key()
    instance = get_instance(instance_id)
    config = current_app.config
    with IaaS.connect(config['IAAS'], config) as iaas:
        if iaas.is_running(instance.identifier):
            operator = BasicOperator(iaas, config)
            if operator.is_running(instance.identifier):
                instance.status = 'available'
                instance.status_message = None
            else:
                instance.status = 'failed'
                instance.status_message = \
                    'VM is running but Postgres is not running.'
        else:
            instance.status = 'stopped'
            instance.status_message = None

    db.session.commit()
    logger.info("%s inspected.", instance)


@actor
def reboot_db_instance(instance_id):
    config = current_app.config
    with state_manager(instance_id) as instance:
        logger.info("Rebooting %s.", instance)
        with IaaS.connect(config['IAAS'], config) as iaas:
            iaas.stop_machine(instance.identifier)
            iaas.start_machine(instance.identifier)
        wait_machine(instance.data['Endpoint']['Address'])


@actor
def recover_instances():
    instances = (
        DBInstance.query
        .filter(DBInstance.status.in_(('available', 'stopped')))
    )
    for instance in instances:
        logger.info("Ensuring %s is %s.", instance.identifier, instance.status)
        if instance.status == 'available':
            start_db_instance.send(instance.id)
        elif instance.status == 'stopped':
            stop_db_instance.send(instance.id)


@actor
def start_db_instance(instance_id):
    config = current_app.config
    with state_manager(instance_id) as instance:
        logger.info("Starting %s.", instance)
        with IaaS.connect(config['IAAS'], config) as iaas:
            iaas.start_machine(instance.identifier)
        wait_machine(instance.data['Endpoint']['Address'])


@actor
def stop_db_instance(instance_id):
    config = current_app.config
    with state_manager(instance_id) as instance:
        logger.info("Stopping %s.", instance)
        with IaaS.connect(config['IAAS'], config) as iaas:
            iaas.stop_machine(instance.identifier)
