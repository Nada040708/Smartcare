const {test} = require('node:test');
const assert = require('node:assert/strict');
const flows = require('./flows.json');
const policy = require('../../config/validation-policy.json');
const validator = require('./validator.cjs').createValidator(policy);
const contract = require('../../tests/fixtures/validation_cases.json');
const fnNode = flows.find(n => n.id === 'check-envelope');
const evaluate = new Function('msg','node','global',fnNode.func);
for (const c of contract.cases) {
    test('shared contract: '+c.name, () => {
        const result = validator.validate(c.payload,{topic:c.topic,retained:c.retained,now:Date.parse(contract.now)});
        assert.equal(result.accepted, c.codes.length === 0);
        assert.deepEqual([...new Set(result.errors.map(e=>e.code))].sort(), [...c.codes].sort());
    });
}
function run(payload,topic='health/P001/vitals',retain=false) {
    return evaluate({payload,topic,retain},{error:()=>{}},{get:()=>({validate:(p,ctx)=>validator.validate(p,{...ctx,now:Date.parse(contract.now)})})});
}
test('accepted reading is returned unchanged',()=>{
    const payload=contract.cases[0].payload;
    const result=run(payload);
    assert.equal(result[0].payload,'Patient P001 | heart_rate: 84 bpm');
    assert.deepEqual(JSON.parse(result[1].payload),payload);
    assert.equal(result[1].topic,'health/P001/received');
    assert.equal(result[2],null);
});
test('rejected reading has no accepted output and carries reason codes',()=>{
    const payload={...contract.cases[0].payload,unit:'wrong'};
    const result=run(payload);
    assert.equal(result[0],null);
    assert.equal(result[1],null);
    assert.equal(result[2].topic,'health/P001/rejected');
    assert.equal(JSON.parse(result[2].payload).errors[0].code,'unit_mismatch');
});
test('mismatch is returned to the source topic patient, not payload patient',()=>{
    const result=run(contract.cases[0].payload,'health/P002/vitals');
    assert.equal(result[2].topic,'health/P002/rejected');
});
test('flow has separate accepted and rejected outputs',()=>{
    assert.deepEqual(fnNode.wires,[['received-debug'],['receipt-out'],['errors-debug','receipt-out']]);
    assert.deepEqual(flows.find(n=>n.id==='decode-json').wires,[['check-envelope']]);
    assert.deepEqual(flows.find(n=>n.id==='errors').wires,[['format-rejection']]);
});
