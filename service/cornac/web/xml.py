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


class InstanceEncoder:
    # Adapt DBInstance object to RDS XML response.

    XML_SNIPPET_TMPL = Template(dedent("""\
    <DBInstance>
      <DBInstanceIdentifier>{{ identifier }}</DBInstanceIdentifier>
      <Engine>postgres</Engine>
      <DBInstanceStatus>{{ status }}</DBInstanceStatus>
      <MasterUsername>postgres</MasterUsername>
    {% if endpoint_address %}
      <Endpoint>
        <Address>{{ endpoint_address }}</Address>
        <Port>5432</Port>
      </Endpoint>
    {% endif %}
      <AllocatedStorage>{{ data['AllocatedStorage'] }}</AllocatedStorage>
      <InstanceCreateTime>{{ data['InstanceCreateTime'] }}</InstanceCreateTime>
      <MultiAZ>{{ 'true' if data['MultiAZ'] else 'false' }}</MultiAZ>
    </DBInstance>
    """), trim_blocks=True)

    def __init__(self, instance):
        self.instance = instance

    def as_xml(self):
        try:
            endpoint_address = self.instance.data['Endpoint']['Address']
        except (KeyError, TypeError):
            endpoint_address = None
        return self.XML_SNIPPET_TMPL.render(
            endpoint_address=endpoint_address,
            **self.instance.__dict__,
        )
