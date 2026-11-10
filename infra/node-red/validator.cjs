// Technical validation, not clinical interpretation. Policy is shared with Python.
const text = value => typeof value === 'string' && value.trim().length > 0;
const finite = value => typeof value === 'number' && Number.isFinite(value);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
function parseTimestamp(value) {
    if (typeof value !== 'string') return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
    if (!m) return null;
    const [y, month, day, hour, minute, second] = m.slice(1,7).map(Number);
    if (y < 1 || month < 1 || month > 12 || day < 1 || hour > 23 || minute > 59 || second > 59) return null;
    const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
    if (day > [31,leap ? 29 : 28,31,30,31,30,31,31,30,31,30,31][month-1]) return null;
    if (m[8] !== 'Z' && (Number(m[8].slice(1,3)) > 23 || Number(m[8].slice(4)) > 59)) return null;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
}
function createValidator(policy) {
    for (const key of ['max_age_seconds','max_future_seconds']) {
        if (!finite(policy[key]) || policy[key] < 0) throw new Error('Invalid policy: ' + key);
    }
    return {validate(payload, {topic, retained=false, now=Date.now()}={}) {
        const errors = [];
        const add = (code, field) => errors.push({code,field});
        const result = () => ({accepted: errors.length === 0, errors});
        if (typeof payload === 'string') {
            try {payload = JSON.parse(payload);} catch (_) {add('invalid_json','payload'); return result();}
        }
        if (!object(payload) || own(payload,'values')) {add('invalid_format','payload'); return result();}
        for (const key of ['measurement_id','reading_id','patient_id','device_id','parameter','unit','timestamp','quality']) {
            if (!text(payload[key])) add('invalid_format',key);
        }
        if (errors.length) return result();
        if (!/^[A-Za-z0-9_-]+$/.test(payload.patient_id)) add('invalid_format','patient_id');
        if (topic !== undefined && topic !== null && topic !== 'health/' + payload.patient_id + '/vitals') add('topic_mismatch','topic');
        if (retained) add('retained_message','retain');
        const parameter = own(policy.parameters,payload.parameter) ? policy.parameters[payload.parameter] : null;
        if (!parameter) add('unknown_parameter','parameter');
        else if (payload.unit !== parameter.unit) add('unit_mismatch','unit');
        if (!finite(payload.value)) add('invalid_value','value');
        else if (parameter && (payload.value < parameter.minimum || payload.value > parameter.maximum)) add('out_of_range','value');
        const timestamp = parseTimestamp(payload.timestamp);
        if (timestamp === null) add('invalid_timestamp','timestamp');
        else if ((now-timestamp)/1000 > policy.max_age_seconds) add('stale_timestamp','timestamp');
        else if ((timestamp-now)/1000 > policy.max_future_seconds) add('future_timestamp','timestamp');
        if (!policy.accepted_quality.includes(payload.quality)) add('invalid_quality','quality');
        const metadata = payload.ieee11073_metadata;
        if (!object(metadata)) add('metadata_mismatch','ieee11073_metadata');
        else {
            const expected = {timestamp:payload.timestamp,quality:payload.quality,nomenclature_system:policy.nomenclature_system};
            if (parameter) for (const key of ['metric_code','metric_refid','unit_code','unit_refid','mapping_status']) expected[key] = parameter[key];
            for (const [key,value] of Object.entries(expected)) {
                if (!own(metadata,key) || metadata[key] !== value) add('metadata_mismatch','ieee11073_metadata.'+key);
            }
            if (!text(metadata.device_type)) add('metadata_mismatch','ieee11073_metadata.device_type');
        }
        return result();
    }};
}
module.exports = {createValidator, parseTimestamp};
