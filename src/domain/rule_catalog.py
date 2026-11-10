import json
from pathlib import Path

from .monitoring_rule import ThresholdRule, CombinedRule, TrendRule, Condition

RULES_PATH = Path(__file__).resolve().parents[2] / 'config/monitoring-rules.json'


def load_rules(profile_id, path=RULES_PATH):
    config = json.loads(Path(path).read_text())
    definitions = config['common'] if profile_id == 'common' else config['profiles'].get(profile_id,[])
    rules = []
    for definition in definitions:
        fields = dict(definition)
        kind = fields.pop('kind')
        if kind == 'combined':
            fields['conditions'] = tuple(Condition(**c) for c in fields['conditions'])
        rule_type = {'threshold':ThresholdRule,'combined':CombinedRule,'trend':TrendRule}.get(kind)
        if rule_type is None:
            raise ValueError(f'Unknown rule kind: {kind}')
        rules.append(rule_type(**fields))
    if len({rule.rule_id for rule in rules}) != len(rules):
        raise ValueError(f'Duplicate rule identifiers in {profile_id}')
    return rules
