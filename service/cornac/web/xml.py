from textwrap import dedent

from flask import make_response
from jinja2 import Template


ERROR_TMPL = Template("""\
<ErrorResponse>
   <Error>
      <Type>{{ type }}</Type>
      <Code>{{ rdscode }}</Code>
      <Message>{{ message }}</Message>
   </Error>
   <RequestId>{{ requestid }}</RequestId>
</ErrorResponse>
""")


def make_error_xml(error, requestid):
    xml = ERROR_TMPL.render(
        code=error.code,
        message=error.description,
        rdscode=error.rdscode,
        requestid=requestid,
        type='Sender' if error.code < 500 else 'Receiver',
    )
    response = make_response(xml)
    response.status_code = error.code
    response.content_type = 'text/xml; charset=utf-8'
    response.headers['X-Amzn-RequestId'] = requestid
    return response


RESPONSE_TMPL = Template("""\
<{{ action }}Response xmlns="http://rds.amazonaws.com/doc/2014-10-31/">
  <{{ action }}Result>
    {{ result | indent(4) }}
  </{{ action }}Result>
  <ResponseMetadata>
    <RequestId>{{ requestid }}</RequestId>
  </ResponseMetadata>
</{{ action }}Response>
""")


def make_response_xml(action, requestid, result):
    # Wraps result XML snippet in response XML envelope.

    xml = RESPONSE_TMPL.render(**locals())
    response = make_response(xml)
    response.content_type = 'text/xml; charset=utf-8'
    response.headers['X-Amzn-RequestId'] = requestid
    return response


def booltostr(value):
    return 'true' if value is True else 'false'


class InstanceEncoder:
    # Adapt DBInstance object to RDS XML response.

    XML_SNIPPET_TMPL = Template(dedent("""\
    <DBInstance>
      <DBInstanceIdentifier>{{ identifier }}</DBInstanceIdentifier>
      <Engine>postgres</Engine>
      <DBInstanceStatus>{{ status }}</DBInstanceStatus>
    {% if endpoint_address %}
      <Endpoint>
        <Address>{{ endpoint_address }}</Address>
        <Port>5432</Port>
      </Endpoint>
    {% endif %}
    {% for field in known_fields %}
      <{{ field }}>{{ data[field] }}</{{ field }}>
    {% endfor %}
    </DBInstance>
    """), trim_blocks=True)

    def __init__(self, instance):
        self.instance = instance

    _known_fields = [
        'MasterUsername',
        'AllocatedStorage',
        'InstanceCreateTime',
        'MultiAZ',
    ]

    def as_xml(self):
        data = self.instance.data or {}
        try:
            endpoint_address = data['Endpoint']['Address']
        except KeyError:
            endpoint_address = None

        data = {
            k: booltostr(v) if v in (True, False) else v
            for k, v in data.items()
        }
        known_fields = [
            h for h in self._known_fields
            if h in data]

        kw = dict(self.instance.__dict__, data=data)
        return self.XML_SNIPPET_TMPL.render(
            endpoint_address=endpoint_address,
            known_fields=known_fields,
            **kw,
        )
