from warnings import filterwarnings

# psycopg2 and psycopg2-binary is a mess, because you can't define OR
# dependency in Python. Just globally ignore this for now.
filterwarnings("ignore", message="The psycopg2 wheel package will be renamed")  # noqa
