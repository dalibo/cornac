import secrets
import string


_ACCESS_KEY_LETTERS = string.ascii_uppercase + string.digits
_SECRET_LETTERS = string.ascii_letters + string.digits + '+/-_'


def generate_key(prefix='AKDC', length=20):
    # AKDC stands for Access Key Dalibo Cornac.
    return prefix + ''.join(secrets.choice(_ACCESS_KEY_LETTERS)
                            for _ in range(length - len(prefix)))


def generate_secret(length=40):
    return ''.join(secrets.choice(_SECRET_LETTERS) for _ in range(length))
