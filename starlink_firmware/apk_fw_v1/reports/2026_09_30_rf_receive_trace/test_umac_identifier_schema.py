from umac_identifier_schema import run


def test_identifier_schema_and_object_types():
    result = run()
    nested = {item['name']: item for item in result['descriptor']['nested']}
    assert [(f['number'], f['name']) for f in nested['GatewayID']['fields']] == [
        (1, 'gateway_id'), (2, 'gateway_site_id')]
    assert next(f for f in nested['UtNetworkId']['fields'] if f['number'] == 2)['name'] == 'cell_id'
    assert len(result['types']) == 4
    request = result['enclosing_request']
    assert request['name'] == 'MacUpRequest'
    assert next(f for f in request['fields'] if f['number'] == 5)['name'] == 'local_id'
    assert 'MacUpResponse' in result['rpc_types'][1]['rtti']
    assert '10a530: bl #0x19c420' in result['instruction_windows']['0x10a510']
