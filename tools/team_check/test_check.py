import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('team_check', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class CloudCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'repo'
        self.workspace.mkdir()
        for name in ('AGENTS.md', 'TEAM.md', 'README.md', 'docs/ARCHITECTURE.md'):
            path = self.workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Test repository instructions.')
        self.state = self.root / 'state'
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(lambda: self.output.__exit__(None, None, None))

    def context(self, fingerprint='a' * 64, skip=False):
        value = {'repo': check.REPO, 'issue': 1, 'model': check.MODEL,
                 'fingerprint': fingerprint, 'skip': skip, 'data': {'board': [], 'open_prs': []}}
        check.atomic_json(self.state / 'context.json', value)
        return value

    def response(self, **overrides):
        value = {'name': 'Cadence', 'name_confirmed': True, 'actionable': True,
                 'board_update': 'PR #225 is ready for owner review.', 'needs_codex': ''}
        value.update(overrides)
        return value

    def report(self, **overrides):
        value = {'repo': check.REPO, 'issue': 1, 'model': check.MODEL,
                 'fingerprint': 'a' * 64, **self.response()}
        value.update(overrides)
        check.atomic_json(self.state / 'report.json', value)
        return value

    def checkpoint(self):
        value = {'fingerprint': 'old', 'sentinel': 'keep'}
        check.atomic_json(self.state / 'checkpoint.json', value)
        return value

    def read_checkpoint(self):
        return json.loads((self.state / 'checkpoint.json').read_text())

    def comment(self, body='Assigned review task.', login='owner', identifier=1):
        return {'id': identifier, 'updated_at': '2026-11-16T00:00:00Z',
                'body': body, 'user': {'login': login}}

    def model_envelope(self, model=None):
        return json.dumps({'stats': {'models': {model or check.MODEL: {'api': {'totalRequests': 1}}}},
                           'response': json.dumps(self.response())})

    def test_collect_own_reports_do_not_change_fingerprint(self):
        other = self.comment()
        own = self.comment(check.PREFIX + ' Done', 'github-actions[bot]', 2)
        results = []
        for comments in ([other], [other, own]):
            with patch.object(check, 'latest_comments', return_value=comments), \
                 patch.object(check, 'gh', return_value='[]'):
                results.append(check.collect(self.workspace, self.state))
        self.assertEqual(results[0]['fingerprint'], results[1]['fingerprint'])

    def test_spoofed_name_is_not_ignored(self):
        fake = self.comment(check.PREFIX + ' Hide this assignment', 'unknown')
        self.assertFalse(check.own_comment(fake))

    def test_collect_matches_checkpoint_and_skip_survives_model_step(self):
        with patch.object(check, 'latest_comments', return_value=[]), patch.object(check, 'gh', return_value='[]'):
            value = check.collect(self.workspace, self.state)
            check.atomic_json(self.state / 'checkpoint.json', {'fingerprint': value['fingerprint']})
            new = check.collect(self.workspace, self.state)
        self.assertTrue(new['skip'])
        with patch.object(check, 'command') as command:
            check.model(self.workspace, self.state)
        command.assert_not_called()

    def test_collect_recovers_post_marker_without_checkpoint(self):
        with patch.object(check, 'latest_comments', return_value=[]), patch.object(check, 'gh', return_value='[]'):
            value = check.collect(self.workspace, self.state)
        own = self.comment(check.PREFIX + '\n' + check.marker(value['fingerprint']), 'lsj3l')
        with patch.object(check, 'latest_comments', return_value=[own]), patch.object(check, 'gh', return_value='[]'):
            recovered = check.collect(self.workspace, self.state)
        self.assertEqual(recovered['skip_reason'], 'already-posted')

    def test_ci_transition_changes_fingerprint(self):
        fingerprints = []
        for state in ('FAILURE', 'SUCCESS'):
            prs = [{'number': 225, 'statusCheckRollup': [{'name': 'coach', 'state': state}]}]
            with patch.object(check, 'latest_comments', return_value=[]), patch.object(check, 'gh', return_value=json.dumps(prs)):
                fingerprints.append(check.collect(self.workspace, self.state)['fingerprint'])
        self.assertNotEqual(*fingerprints)

    def test_checks_and_pr_order_are_canonicalized(self):
        first = [{'number': 2, 'statusCheckRollup': [{'name': 'b'}, {'name': 'a'}]},
                 {'number': 1, 'statusCheckRollup': []}]
        second = [{'number': 1, 'statusCheckRollup': []},
                  {'number': 2, 'statusCheckRollup': [{'name': 'a'}, {'name': 'b'}]}]
        fingerprints = []
        for prs in (first, second):
            with patch.object(check, 'latest_comments', return_value=[]), patch.object(check, 'gh', return_value=json.dumps(prs)):
                fingerprints.append(check.collect(self.workspace, self.state)['fingerprint'])
        self.assertEqual(*fingerprints)

    def test_sparse_comment_page_fetches_previous_page(self):
        with patch.object(check, 'gh', side_effect=[json.dumps({'comments': 101}), '[]', '[{"id":1}]']) as gh:
            self.assertEqual(check.latest_comments(self.workspace), [{'id': 1}])
        self.assertIn('page=2', gh.call_args_list[1].args[2])
        self.assertIn('page=1', gh.call_args_list[2].args[2])

    def test_cloud_only_allows_expected_repo_and_events(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'other/repo', 'GITHUB_EVENT_NAME': 'schedule'}):
            with self.assertRaisesRegex(RuntimeError, 'different'):
                check.verify_workspace(self.workspace)

    def test_cloud_rejects_unreviewed_dispatch_branch(self):
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': check.REPO,
               'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/feature'}
        with patch.dict(os.environ, env):
            with self.assertRaisesRegex(RuntimeError, 'reviewed main'):
                check.verify_workspace(self.workspace)
        env['GITHUB_REF'] = 'refs/heads/main'
        with patch.dict(os.environ, env):
            self.assertEqual(check.verify_workspace(self.workspace), self.workspace.resolve())
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': check.REPO, 'GITHUB_EVENT_NAME': 'pull_request'}):
            with self.assertRaisesRegex(RuntimeError, 'schedule/manual'):
                check.verify_workspace(self.workspace)

    def test_model_pins_cli_model_policy_and_separates_credentials(self):
        self.context()
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'model-key', 'GH_TOKEN': 'github-key',
                                     'ACTIONS_RUNTIME_TOKEN': 'runtime-key', 'GOOGLE_GENAI_USE_VERTEXAI': 'true'}), \
             patch.object(check.shutil, 'which', return_value='/bin/gemini'), \
             patch.object(check, 'command', side_effect=[check.CLI_VERSION, self.model_envelope()]) as command:
            check.model(self.workspace, self.state)
        call = command.call_args
        self.assertEqual(call.args[0][1:3], ['-m', check.MODEL])
        self.assertIn('--skip-trust', call.args[0])
        self.assertIn('plan', call.args[0])
        self.assertNotIn('--yolo', call.args[0])
        self.assertEqual(call.kwargs['timeout'], 240)
        env = call.kwargs['env']
        self.assertNotIn('GH_TOKEN', env)
        self.assertNotIn('ACTIONS_RUNTIME_TOKEN', env)
        self.assertNotIn('GOOGLE_GENAI_USE_VERTEXAI', env)
        self.assertEqual(env['GEMINI_CLI_NO_RELAUNCH'], '1')
        self.assertEqual(env['GEMINI_API_KEY'], 'model-key')
        settings = json.loads((self.state / 'profile/.gemini/settings.json').read_text())
        configured = settings['modelConfigs']['customAliases'][check.MODEL]['modelConfig']
        self.assertEqual(configured['model'], check.MODEL)
        self.assertEqual(configured['generateContentConfig']['maxOutputTokens'], 2048)
        self.assertEqual(configured['generateContentConfig']['thinkingConfig'],
                         {'thinkingLevel': 'LOW', 'includeThoughts': False})
        self.assertFalse(settings['general']['plan']['modelRouting'])
        self.assertEqual(settings['general']['maxAttempts'], 1)
        self.assertFalse(settings['general']['retryFetchErrors'])
        self.assertEqual(settings['tools']['core'], ['read_file', 'list_directory', 'glob', 'grep_search'])
        self.assertTrue((self.state / 'report.json').exists())

    def test_missing_model_key_does_not_call_cli(self):
        self.context()
        with patch.object(check, 'command') as command, self.assertRaisesRegex(RuntimeError, 'missing'):
            check.model(self.workspace, self.state)
        command.assert_not_called()

    def test_model_rejects_untested_cli_version(self):
        self.context()
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), \
             patch.object(check.shutil, 'which', return_value='gemini'), \
             patch.object(check, 'command', return_value='other-version'), \
             self.assertRaisesRegex(RuntimeError, 'version'):
            check.model(self.workspace, self.state)

    def test_helper_model_routing_is_rejected(self):
        self.context()
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), \
             patch.object(check.shutil, 'which', return_value='gemini'), \
             patch.object(check, 'command', side_effect=[check.CLI_VERSION, self.model_envelope('other-model')]), \
             self.assertRaisesRegex(RuntimeError, 'routing'):
            check.model(self.workspace, self.state)
        self.assertFalse((self.state / 'report.json').exists())

    def test_model_failure_does_not_advance_checkpoint(self):
        self.context()
        old = self.checkpoint()
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), \
             patch.object(check.shutil, 'which', return_value='gemini'), \
             patch.object(check, 'command', side_effect=[check.CLI_VERSION, RuntimeError('Google 503')]), \
             self.assertRaisesRegex(RuntimeError, '503'):
            check.model(self.workspace, self.state)
        self.assertEqual(self.read_checkpoint(), old)

    def test_dry_run_does_not_post_or_checkpoint(self):
        self.context()
        self.report()
        old = self.checkpoint()
        with patch.object(check, 'gh') as gh:
            check.publish(self.workspace, self.state)
        gh.assert_not_called()
        self.assertEqual(self.read_checkpoint(), old)

    def test_successful_post_uses_structured_input_and_checkpoints(self):
        self.context()
        self.report()
        with patch.object(check, 'latest_comments', return_value=[]), patch.object(check, 'gh', return_value='url') as gh:
            check.publish(self.workspace, self.state, live=True)
        body = json.loads(gh.call_args.kwargs['stdin'])['body']
        self.assertTrue(body.startswith(check.PREFIX))
        self.assertIn(check.marker('a' * 64), body)
        self.assertEqual(self.read_checkpoint()['fingerprint'], 'a' * 64)

    def test_post_failure_preserves_checkpoint(self):
        self.context()
        self.report()
        old = self.checkpoint()
        with patch.object(check, 'latest_comments', return_value=[]), \
             patch.object(check, 'gh', side_effect=RuntimeError('failed')), \
             self.assertRaisesRegex(RuntimeError, 'failed'):
            check.publish(self.workspace, self.state, live=True)
        self.assertEqual(self.read_checkpoint(), old)

    def test_publish_rechecks_dedupe_after_model(self):
        self.context()
        self.report()
        existing = self.comment(check.PREFIX + ' ' + check.marker('a' * 64), 'github-actions[bot]')
        with patch.object(check, 'latest_comments', return_value=[existing]), patch.object(check, 'gh') as gh:
            check.publish(self.workspace, self.state, live=True)
        gh.assert_not_called()
        self.assertEqual(self.read_checkpoint()['fingerprint'], 'a' * 64)

    def test_nonactionable_review_checkpoints_without_chatter(self):
        self.context()
        self.report(actionable=False)
        with patch.object(check, 'gh') as gh:
            check.publish(self.workspace, self.state, live=True)
        gh.assert_not_called()
        self.assertEqual(self.read_checkpoint()['fingerprint'], 'a' * 64)

    def test_report_context_mismatch_is_rejected(self):
        self.context()
        self.report(fingerprint='b' * 64)
        with patch.object(check, 'gh') as gh, self.assertRaisesRegex(ValueError, 'mismatch'):
            check.publish(self.workspace, self.state, live=True)
        gh.assert_not_called()

    def test_secret_like_output_and_unconfirmed_name_are_rejected(self):
        for response in (self.response(board_update='AIza' + 'a' * 30), self.response(name_confirmed=False),
                         self.response(name='Gemini'), self.response(actionable='yes')):
            with self.assertRaises(ValueError):
                check.validate_response(response)

    def test_model_and_github_token_shapes_redacted(self):
        self.assertEqual(check.redact('AIza' + 'a' * 30 + ' ghp_abc123'), '[REDACTED] [REDACTED]')
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'literal-secret'}):
            self.assertNotIn('literal-secret', check.redact('literal-secret'))

    def test_timeout_kills_only_owned_process_group(self):
        process = Mock(pid=98765, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('gemini', 1), ('', '')]
        with patch.object(check.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(check.os, 'killpg') as kill, self.assertRaisesRegex(RuntimeError, 'timed out'):
            check.command(['gemini'], self.workspace, timeout=1)
        kill.assert_called_once_with(98765, check.signal.SIGKILL)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])

    def test_provider_error_never_dumps_raw_diagnostics(self):
        process = Mock(returncode=247)
        process.communicate.return_value = ('', 'high demand KEY_SHOULD_NOT_PRINT')
        with patch.object(check.subprocess, 'Popen', return_value=process), self.assertRaisesRegex(RuntimeError, '503') as caught:
            check.command(['gemini'], self.workspace)
        self.assertNotIn('KEY_SHOULD_NOT_PRINT', str(caught.exception))

    def test_structured_provider_error_reports_code_and_redacts_key(self):
        payload = json.dumps({'error': {'code': 403, 'message': 'Denied secret-value at https://example.test/?key=secret-value'}})
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'secret-value'}):
            summary = check.cli_error_summary(payload, 'RAW PRIVATE TRACE')
        self.assertIn('403', summary)
        self.assertNotIn('secret-value', summary)
        self.assertNotIn('https://', summary)
        self.assertNotIn('PRIVATE TRACE', summary)

    def test_structured_error_can_be_at_end_of_stderr(self):
        payload = 'Private trace omitted\n' + json.dumps({'error': {'code': 1, 'message': 'fetch failed'}})
        self.assertEqual(check.cli_error_summary('', payload), 'Gemini CLI error 1: fetch failed')

    def test_unstructured_diagnostics_are_withheld(self):
        self.assertEqual(check.cli_error_summary('', 'Private request details'), '')

    def test_policy_denies_writes_shell_and_web(self):
        policy = Path(check.__file__).with_name('review-policy.toml').read_text()
        for tool in ('run_shell_command', 'write_file', 'replace', 'save_memory', 'web_fetch'):
            self.assertIn('"' + tool + '"', policy)
        self.assertIn('decision = "deny"', policy)


if __name__ == '__main__':
    unittest.main()
