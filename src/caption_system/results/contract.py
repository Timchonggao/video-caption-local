def validate(value, duration, evidence):
    if not isinstance(value, dict) or not isinstance(value.get('generated_caption'), str) or (not value['generated_caption'].strip()):
        raise ValueError('Missing caption')
    if 'entities' not in value:
        for key in ('actions', 'state_changes', 'uncertainties'):
            if not isinstance(value.get(key), list):
                raise ValueError('Missing list ' + key)
        for item in value['actions']:
            if not isinstance(item, dict) or not isinstance(item.get('operation'), str) or not item['operation'].strip():
                raise ValueError('Invalid operation')
            for key in ('actor', 'target', 'details'):
                if key not in item or item[key] is not None and not isinstance(item[key], str):
                    raise ValueError('Invalid action ' + key)
        for item in value['state_changes']:
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in ('object', 'before', 'after')):
                raise ValueError('Invalid state change')
        if any(not isinstance(u, str) for u in value['uncertainties']):
            raise ValueError('Invalid uncertainty')
        return value
    for key in ['scene', 'entities', 'actions', 'state_changes', 'observed_outcome', 'uncertainties']:
        if key not in value:
            raise ValueError('Missing structured field ' + key)
    for key in ['entities', 'actions', 'state_changes', 'uncertainties']:
        if not isinstance(value[key], list):
            raise ValueError('Invalid list ' + key)
    ids = {e['id'] for e in value['entities']}
    for action in value['actions']:
        if not 0 <= action['start_s'] <= action['end_s'] <= duration + 0.01:
            raise ValueError('Invalid action time range')
        if action['actor'] not in ids or action.get('object') not in ids | {None}:
            raise ValueError('Unknown entity')
    for item in value['actions'] + value['state_changes']:
        for t in item['evidence_times_s']:
            if not any((abs(t - e) < 0.02 for e in evidence)):
                raise ValueError('Invented evidence timestamp')
    return value
