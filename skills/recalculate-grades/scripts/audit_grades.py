#!/usr/bin/env python3
"""Audit normalized course records. Python 3.10+, standard library only."""
import argparse
import json
import os
import tempfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def number(value, label, low=Decimal('0'), high=Decimal('100')):
    require(not isinstance(value, (bool, float)), f'{label}: use decimal strings, not floats/bools')
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise AuditError(f'{label}: invalid number') from None
    require(result.is_finite() and low <= result <= high, f'{label}: out of range')
    require(len(result.as_tuple().digits) <= 16 and -10 <= result.as_tuple().exponent <= 16,
            f'{label}: at most 16 digits and 10 decimal places')
    return result


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f'{label}: required string')
    require(value == value.strip(), f'{label}: remove surrounding whitespace')
    return value


def decimal_text(value):
    return format(value, 'f')


def validate_rules(rules):
    text(rules.get('rule_source'), 'rule_source')
    threshold = number(rules.get('pass_threshold'), 'pass_threshold')
    require(threshold > 0, 'pass_threshold: must be positive')
    academic = number(rules.get('academic_weight'), 'academic_weight', high=Decimal('1'))
    assessment = number(rules.get('assessment_weight'), 'assessment_weight', high=Decimal('1'))
    require(academic + assessment == 1, 'weights must sum to 1')
    require(rules.get('nonfailure_mode') in ('recalculate', 'original'), 'invalid nonfailure_mode')
    require(type(rules.get('zero_is_failure')) is bool, 'zero_is_failure must be boolean')
    unresolved = rules.get('unresolved')
    require(isinstance(unresolved, dict), 'unresolved: required object')
    for status in ('deferred', 'pending', 'absent'):
        require(unresolved.get(status) in ('block', 'exclude', 'zero'), f'invalid {status} policy')
    mapping = rules.get('grade_map')
    require(isinstance(mapping, dict), 'grade_map: required object')
    for label, value in mapping.items():
        text(label, 'grade label')
        number(value, f'grade_map.{label}')
    return threshold, academic, assessment


def score_value(value, rules):
    if isinstance(value, str) and value in rules['grade_map']:
        value = rules['grade_map'][value]
    return number(value, 'score')


def audit_student(student, rules, threshold, academic_weight, assessment_weight):
    sid = text(student.get('student_id'), 'student_id')
    result = {'student_id': sid, 'status': 'blocked', 'errors': [], 'courses': []}
    try:
        result['name'] = text(student.get('name'), 'name')
        result['class_name'] = text(student.get('class_name'), 'class_name')
        assessment = number(student.get('assessment'), 'assessment')
        text(student.get('assessment_source'), 'assessment_source')
        expected = student.get('expected_course_ids')
        require(isinstance(expected, list) and bool(expected), 'expected_course_ids: required nonempty list')
        for cid in expected:
            text(cid, 'expected_course_id')
        require(len(set(expected)) == len(expected), 'duplicate expected course IDs')
        text(student.get('course_list_source'), 'course_list_source')
        courses = student.get('courses')
        require(isinstance(courses, list) and bool(courses), 'courses: required nonempty list')
        ids = [text(c.get('course_id'), 'course_id') for c in courses if isinstance(c, dict)]
        require(len(ids) == len(courses), 'each course must be an object')
        require(len(set(ids)) == len(ids), 'duplicate course: select one verified examination record first')
        require(set(ids) == set(expected), 'course list differs from expected_course_ids')
        numerator = Decimal('0')
        denominator = Decimal('0')
        failures = []
        unresolved_count = 0
        for course in courses:
            trace = dict(course)
            result['courses'].append(trace)
            try:
                text(course.get('name'), 'course name')
                text(course.get('score_source'), 'score_source')
                text(course.get('credit_source'), 'credit_source')
                credits = number(course.get('credits'), 'credits', high=Decimal('1000'))
                require(credits > 0, 'credits must be positive')
                status = course.get('status')
                require(status in ('normal', 'failed', 'deferred', 'pending', 'absent'), 'unknown status')
                if status in ('normal', 'failed'):
                    raw = score_value(course.get('score'), rules)
                    require(not (status == 'failed' and raw >= threshold), 'failed status contradicts passing score')
                    require(not (status == 'normal' and raw == 0 and not rules['zero_is_failure']),
                            'ambiguous zero: verify status or confirm zero_is_failure')
                    failed = status == 'failed' or raw < threshold
                    counted = Decimal('0') if failed else raw
                    include = True
                    if failed:
                        failures.append(course['course_id'])
                    trace['normalized_score'] = decimal_text(raw)
                    trace['decision'] = 'failed_zero' if failed else 'normal'
                else:
                    require(course.get('score') in (None, ''), 'unresolved status has score: verify examination record')
                    unresolved_count += 1
                    policy = rules['unresolved'][status]
                    require(policy != 'block', f'{status}: unresolved under confirmed rules')
                    include = policy == 'zero'
                    counted = Decimal('0')
                    trace['decision'] = f'{status}_{policy}'
                trace['counted_score'] = decimal_text(counted) if include else None
                trace['included_credits'] = decimal_text(credits) if include else '0'
                trace['weighted_points'] = decimal_text(credits * counted) if include else '0'
                if include:
                    numerator += credits * counted
                    denominator += credits
            except AuditError as exc:
                trace['error'] = str(exc)
                result['errors'].append(f"{course['course_id']}: {exc}")
        result['failed_course_ids'] = failures
        result['unresolved_count'] = unresolved_count
        require(not result['errors'], 'course validation failed')
        require(denominator > 0, 'no included course credits')
        mode = 'recalculate'
        if not failures and rules['nonfailure_mode'] == 'original':
            require(unresolved_count == 0, 'original average cannot be reused with unresolved courses')
            science = number(student.get('original_average'), 'original_average')
            text(student.get('original_average_source'), 'original_average_source')
            mode = 'original'
        else:
            science = numerator / denominator
        composite = science * academic_weight + assessment * assessment_weight
        result.update({
            'status': 'ok', 'mode': mode,
            'weighted_points_total': decimal_text(numerator),
            'included_credits_total': decimal_text(denominator),
            'academic_unrounded': decimal_text(science),
            'academic_display': decimal_text(science.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)),
            'assessment': decimal_text(assessment),
            'composite_unrounded': decimal_text(composite),
            'composite_display': decimal_text(composite.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)),
        })
    except AuditError as exc:
        result['errors'].append(str(exc))
    return result


def audit(payload):
    """Preserve roster order; invalid global scope raises, invalid students block individually."""
    require(isinstance(payload, dict), 'input must be an object')
    require(type(payload.get('schema_version')) is int and payload['schema_version'] == 1,
            'schema_version must be integer 1')
    text(payload.get('term'), 'term')
    rules = payload.get('rules')
    require(isinstance(rules, dict), 'rules must be an object')
    with localcontext() as ctx:
        ctx.prec = 60
        threshold, academic, assessment = validate_rules(rules)
        roster = payload.get('roster')
        require(isinstance(roster, list) and bool(roster), 'roster: required nonempty list')
        for sid in roster:
            text(sid, 'roster student_id')
        require(len(set(roster)) == len(roster), 'duplicate student_id in roster')
        students = payload.get('students')
        require(isinstance(students, list) and all(isinstance(s, dict) for s in students), 'students: required object list')
        ids = [text(s.get('student_id'), 'student_id') for s in students]
        require(len(set(ids)) == len(ids), 'duplicate student_id in students')
        require(set(ids) == set(roster), 'students must exactly match roster; no missing or extra IDs')
        by_id = {s['student_id']: s for s in students}
        results = [audit_student(by_id[sid], rules, threshold, academic, assessment) for sid in roster]
    blocked = [r['student_id'] for r in results if r['status'] == 'blocked']
    return {'schema_version': 1, 'term': payload['term'], 'rules': rules,
            'status': 'blocked' if blocked else 'ok', 'roster_count': len(roster),
            'ok_count': len(roster) - len(blocked), 'blocked_student_ids': blocked,
            'failed_student_ids': [r['student_id'] for r in results
                                   if r['status'] == 'ok' and r['failed_course_ids']],
            'results': results}


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as temp:
        temp_path = temp.name
        json.dump(report, temp, ensure_ascii=False, indent=2, default=decimal_text)
        temp.write('\n')
    try:
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate JSON field: {key}')
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(args.input.resolve() != args.output.resolve(), 'input and output must differ')
    try:
        payload = json.loads(args.input.read_text(encoding='utf-8'), parse_float=Decimal,
                             object_pairs_hook=unique_object)
        report = audit(payload)
    except (AuditError, OSError, ValueError, TypeError, AttributeError) as exc:
        report = {'schema_version': 1, 'status': 'invalid', 'errors': [str(exc)], 'results': []}
    write_report(args.output, report)
    print(f"Audit {report['status']}; report written.")
    return 0 if report['status'] == 'ok' else 2


if __name__ == '__main__':
    raise SystemExit(main())
