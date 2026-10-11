import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/recalculate-grades/scripts/audit_grades.py'
SPEC = importlib.util.spec_from_file_location('audit_grades', SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class GradeAuditTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'examples/input.json').read_text(encoding='utf-8'))

    def result(self):
        return module.audit(self.data)['results'][0]

    def course(self):
        return self.data['students'][0]['courses'][0]

    def test_failed_course_keeps_credits_in_denominator(self):
        row = self.result()
        self.assertEqual(row['included_credits_total'], '4')
        self.assertEqual(row['weighted_points_total'], '160')
        self.assertEqual(row['academic_display'], '40.00')
        self.assertEqual(row['composite_display'], '52.00')
        self.assertEqual(module.audit(self.data)['failed_student_ids'], ['DEMO-001'])

    def test_pass_boundary_60(self):
        self.data['rules']['nonfailure_mode'] = 'recalculate'
        self.course()['score'] = '60'
        self.assertEqual(self.result()['academic_display'], '70.00')
        self.assertEqual(self.result()['failed_course_ids'], [])

    def test_original_average_only_without_failures(self):
        row = module.audit(self.data)['results'][1]
        self.assertEqual(row['mode'], 'original')
        self.assertEqual(row['academic_display'], '88.13')
        self.assertEqual(row['composite_display'], '88.69')

    def test_grade_mapping_and_recalculate_mode(self):
        self.data['rules']['nonfailure_mode'] = 'recalculate'
        row = module.audit(self.data)['results'][1]
        self.assertEqual(row['weighted_points_total'], '255')
        self.assertEqual(row['academic_display'], '85.00')

    def test_composite_uses_unrounded_academic(self):
        self.data['rules']['nonfailure_mode'] = 'recalculate'
        self.course().update(score='60', credits='1')
        self.data['students'][0]['courses'][1].update(score='61', credits='2')
        self.data['students'][0]['assessment'] = '59.99'
        row = self.result()
        self.assertEqual(row['academic_display'], '60.67')
        self.assertEqual(row['composite_display'], '60.46')
        from decimal import Decimal, ROUND_HALF_UP
        early = (Decimal(row['academic_display']) * Decimal('.7')
                 + Decimal('59.99') * Decimal('.3')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        self.assertEqual(str(early), '60.47')

    def test_ambiguous_zero_blocks(self):
        self.course()['score'] = '0'
        self.assertEqual(self.result()['status'], 'blocked')

    def test_confirmed_zero_is_failure(self):
        self.course()['score'] = '0'
        self.data['rules']['zero_is_failure'] = True
        self.assertEqual(self.result()['status'], 'ok')

    def test_explicit_failed_zero(self):
        self.course().update(status='failed', score='0')
        self.assertEqual(self.result()['status'], 'ok')

    def test_failed_status_conflicts_with_passing_score(self):
        self.course().update(status='failed', score='60')
        self.assertEqual(self.result()['status'], 'blocked')

    def test_unresolved_statuses_block_by_default(self):
        for status in ('deferred', 'pending', 'absent'):
            with self.subTest(status=status):
                self.course().update(status=status, score=None)
                self.assertEqual(self.result()['status'], 'blocked')

    def test_deferred_exclusion_and_zero_are_distinct(self):
        self.data['rules']['nonfailure_mode'] = 'recalculate'
        self.course().update(status='deferred', score=None)
        self.data['rules']['unresolved']['deferred'] = 'exclude'
        self.assertEqual(self.result()['academic_display'], '80.00')
        self.assertEqual(self.result()['included_credits_total'], '2')
        self.data['rules']['unresolved']['deferred'] = 'zero'
        self.assertEqual(self.result()['academic_display'], '40.00')
        self.assertEqual(self.result()['included_credits_total'], '4')
        self.assertEqual(self.result()['failed_course_ids'], [])

    def test_original_mode_rejects_unresolved_average(self):
        self.course().update(status='deferred', score=None)
        self.data['rules']['unresolved']['deferred'] = 'exclude'
        self.assertEqual(self.result()['status'], 'blocked')

    def test_deferred_backfill_requires_status_update(self):
        self.course().update(status='deferred', score='76')
        self.assertEqual(self.result()['status'], 'blocked')
        self.course()['status'] = 'normal'
        self.data['rules']['nonfailure_mode'] = 'recalculate'
        self.assertEqual(self.result()['academic_display'], '78.00')

    def test_duplicate_names_are_separate_by_id(self):
        self.data['students'][1]['name'] = self.data['students'][0]['name']
        self.assertEqual(module.audit(self.data)['ok_count'], 2)

    def test_duplicate_student_id_rejected(self):
        self.data['students'][1]['student_id'] = 'DEMO-001'
        with self.assertRaises(module.AuditError):
            module.audit(self.data)

    def test_missing_and_extra_roster_members_rejected(self):
        self.data['roster'] = ['DEMO-001']
        with self.assertRaises(module.AuditError):
            module.audit(self.data)
        self.data['roster'] = ['DEMO-001', 'DEMO-002', 'DEMO-003']
        with self.assertRaises(module.AuditError):
            module.audit(self.data)

    def test_roster_order_is_preserved(self):
        self.data['roster'].reverse()
        self.assertEqual([r['student_id'] for r in module.audit(self.data)['results']], self.data['roster'])

    def test_duplicate_course_or_examination_blocks(self):
        self.data['students'][0]['courses'].append(copy.deepcopy(self.course()))
        self.assertEqual(self.result()['status'], 'blocked')

    def test_missing_course_blocks(self):
        self.data['students'][0]['courses'].pop()
        self.assertEqual(self.result()['status'], 'blocked')

    def test_missing_or_invalid_credits_block_only_affected_student(self):
        for credits in (None, '', '0', '-1', 'NaN', 'Infinity', True, 2.5):
            with self.subTest(credits=credits):
                self.course()['credits'] = credits
                report = module.audit(self.data)
                self.assertEqual(report['blocked_student_ids'], ['DEMO-001'])
                self.assertEqual(report['ok_count'], 1)

    def test_unknown_grade_and_status_block(self):
        self.course()['score'] = '未知等级'
        self.assertEqual(self.result()['status'], 'blocked')
        self.course().update(score='80', status='unknown')
        self.assertEqual(self.result()['status'], 'blocked')

    def test_sources_are_required(self):
        self.course()['credit_source'] = ''
        self.assertEqual(self.result()['status'], 'blocked')

    def test_duplicate_json_fields_rejected(self):
        with self.assertRaises(module.AuditError):
            json.loads('{"score":"59","score":"80"}', object_pairs_hook=module.unique_object)

    def test_extreme_decimal_exponent_and_boolean_schema_rejected(self):
        self.course()['score'] = '0e999999'
        self.assertEqual(self.result()['status'], 'blocked')
        self.data['schema_version'] = True
        with self.assertRaises(module.AuditError):
            module.audit(self.data)

    def test_invalid_weights_and_grade_map_rejected(self):
        self.data['rules']['academic_weight'] = '.8'
        with self.assertRaises(module.AuditError):
            module.audit(self.data)
        self.data['rules']['academic_weight'] = '.7'
        self.data['rules']['grade_map']['优秀'] = '101'
        with self.assertRaises(module.AuditError):
            module.audit(self.data)

    def test_all_excluded_courses_block(self):
        self.data['rules']['nonfailure_mode'] = 'recalculate'
        self.data['rules']['unresolved']['pending'] = 'exclude'
        for course in self.data['students'][0]['courses']:
            course.update(status='pending', score=None)
        self.assertEqual(self.result()['status'], 'blocked')

    def test_expected_example_matches(self):
        expected = json.loads((ROOT / 'examples/expected.json').read_text(encoding='utf-8'))
        self.assertEqual(module.audit(self.data), expected)

    def test_cli_exit_codes_and_invalid_input_replaces_stale_report(self):
        with tempfile.TemporaryDirectory() as folder:
            inp, out = Path(folder) / 'input.json', Path(folder) / 'report.json'
            for data, status, code in ((self.data, 'ok', 0), ({}, 'invalid', 2)):
                inp.write_text(json.dumps(data), encoding='utf-8')
                run = subprocess.run([sys.executable, str(SCRIPT), str(inp), '--output', str(out)], capture_output=True)
                self.assertEqual(run.returncode, code, run.stderr)
                self.assertEqual(json.loads(out.read_text())['status'], status)
            self.course()['credits'] = None
            inp.write_text(json.dumps(self.data), encoding='utf-8')
            run = subprocess.run([sys.executable, str(SCRIPT), str(inp), '--output', str(out)], capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(json.loads(out.read_text())['status'], 'blocked')

    def test_cli_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as folder:
            inp = Path(folder) / 'input.json'
            original = json.dumps(self.data)
            inp.write_text(original)
            run = subprocess.run([sys.executable, str(SCRIPT), str(inp), '--output', str(inp)], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(inp.read_text(), original)
            self.assertNotIn(b'Traceback', run.stderr)

    def test_report_contains_noncourse_sources(self):
        rows = module.audit(self.data)['results']
        self.assertEqual(rows[0]['assessment_source'], self.data['students'][0]['assessment_source'])
        self.assertEqual(rows[0]['course_list_source'], self.data['students'][0]['course_list_source'])
        self.assertEqual(rows[1]['original_average_source'], self.data['students'][1]['original_average_source'])

    def test_atomic_report_failure_cleans_tempfile_and_preserves_previous_report(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'report.json'
            out.write_text('previous')
            with patch.object(module.os, 'replace', side_effect=OSError('simulated write failure')):
                with self.assertRaises(OSError):
                    module.write_report(out, module.audit(self.data))
            self.assertEqual(out.read_text(), 'previous')
            self.assertEqual(list(Path(folder).iterdir()), [out])

    def test_serialization_failure_cleans_tempfile(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                module.write_report(Path(folder) / 'report.json', {'bad': float('nan')})
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_cli_rejects_nan_even_in_extra_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            inp, out = Path(folder) / 'input.json', Path(folder) / 'report.json'
            self.data['extra'] = float('nan')
            inp.write_text(json.dumps(self.data))
            run = subprocess.run([sys.executable, str(SCRIPT), str(inp), '--output', str(out)], capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(json.loads(out.read_text())['status'], 'invalid')

    def test_cli_output_failure_has_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            inp = Path(folder) / 'input.json'
            inp.write_text(json.dumps(self.data))
            run = subprocess.run([sys.executable, str(SCRIPT), str(inp), '--output', folder], capture_output=True)
            self.assertEqual(run.returncode, 3)
            self.assertNotIn(b'Traceback', run.stderr)


if __name__ == '__main__':
    unittest.main()
