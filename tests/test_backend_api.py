import unittest
import os
import importlib
from pathlib import Path
import urllib.error
from unittest.mock import patch

os.environ.setdefault('NVIDIA_API_KEY', 'test-nvidia-key')
os.environ.setdefault('NVIDIA_API_BASE_URL', 'https://example.com/v1/chat/completions')
os.environ.setdefault('NVIDIA_COACH_MODEL', 'test-coach-model')
os.environ.setdefault('NVIDIA_SAFETY_MODEL', 'test-safety-model')

import backend.app as app_module


class BackendApiSmokeTests(unittest.TestCase):
    def setUp(self):
        app_module._rate_limit_buckets.clear()
        self.client = app_module.app.test_client()
        self.client.post('/api/demo/reset')
        _, self.csrf_token = self._login()

    def _login(self, username='TestUser', password='password123'):
        response = self.client.post('/api/auth/login', json={
            'username': username,
            'password': password,
        })
        self.assertEqual(response.status_code, 200)
        csrf_token = response.get_json()['csrf_token']
        return response, csrf_token

    def test_latest_glucose_is_fresh(self):
        response = self.client.get('/api/glucose/latest/user123')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload['value'], 120)
        self.assertFalse(payload['is_stale'])

    def test_invalid_glucose_timestamp_gets_unknown_freshness_label(self):
        self.assertEqual(app_module.freshness_label('not-a-timestamp'), 'Unknown')

    def test_out_of_range_glucose_timestamp_gets_unknown_freshness_label(self):
        self.assertEqual(app_module.freshness_label('999999999999999999999999-01-01T00:00:00+00:00'), 'Unknown')

    def test_out_of_range_glucose_timestamp_is_treated_as_stale(self):
        self.assertTrue(app_module.is_glucose_reading_stale('999999999999999999999999-01-01T00:00:00+00:00'))

    def test_health_api_responses_are_not_cached(self):
        response = self.client.get('/api/glucose/latest/user123')
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    def test_health_and_readiness(self):
        health = self.client.get('/api/health')
        ready = self.client.get('/api/ready')
        self.assertEqual(health.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(health.get_json()['ok'])
        self.assertTrue(ready.get_json()['ok'])

    def test_production_responses_require_https_for_future_visits(self):
        original_config = app_module.CONFIG
        app_module.CONFIG = app_module.Config(
            **{**original_config.__dict__, 'app_env': 'production'}
        )
        try:
            response = self.client.get('/api/health')
            self.assertEqual(
                response.headers.get('Strict-Transport-Security'),
                'max-age=31536000; includeSubDomains',
            )
        finally:
            app_module.CONFIG = original_config

    def test_readiness_failure_returns_503(self):
        with patch.object(app_module, 'db', side_effect=RuntimeError('boom')):
            response = self.client.get('/api/ready')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()['ok'])

    def test_readiness_query_failure_closes_connection(self):
        class FailingConnection:
            closed = False

            def exec_driver_sql(self, *_args, **_kwargs):
                raise RuntimeError('query failed')

            def close(self):
                self.closed = True

        connection = FailingConnection()
        with patch.object(app_module, 'db', return_value=connection):
            response = self.client.get('/api/ready')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()['ok'])
        self.assertTrue(connection.closed)

    def test_auth_login_and_me(self):
        response, csrf_token = self._login()
        self.assertNotIn('password_hash', response.get_json()['user'])

        me_response = self.client.get('/api/auth/me', headers={'X-CSRF-Token': csrf_token})
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.get_json()['user']['username'], 'TestUser')

    def test_unsafe_request_requires_csrf(self):
        response = self.client.post('/api/glucose/user123', json={
            'value': 123,
            'timestamp': app_module.utcnow().isoformat(),
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error']['code'], 'CSRF_INVALID')

    def test_glucose_rejects_non_text_id(self):
        response = self.client.post('/api/glucose/user123', json={
            'id': {'unexpected': True},
            'value': 123,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_glucose_rejects_duplicate_id(self):
        payload = {'id': 'duplicate-reading', 'value': 110}
        first = self.client.post('/api/glucose/user123', json=payload, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post('/api/glucose/user123', json=payload, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()['error']['code'], 'CONFLICT')

    def test_meal_rejects_non_text_id(self):
        response = self.client.post('/api/meals/user123', json={
            'id': {'unexpected': True},
            'name': 'Breakfast',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_meal_rejects_non_finite_nutrition(self):
        response = self.client.post('/api/meals/user123', json={
            'name': 'Breakfast',
            'carbs': 'NaN',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_meal_rejects_boolean_nutrition(self):
        response = self.client.post('/api/meals/user123', json={
            'name': 'Breakfast',
            'carbs': True,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_meal_rejects_duplicate_id(self):
        payload = {'id': 'duplicate-meal', 'name': 'Breakfast'}
        first = self.client.post('/api/meals/user123', json=payload, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post('/api/meals/user123', json=payload, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()['error']['code'], 'CONFLICT')

    def test_award_rejects_non_text_achievement_id(self):
        response = self.client.post('/api/achievements/award', json={
            'user_id': 'user123',
            'achievement_id': {'unexpected': True},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_award_rejects_missing_achievement_id(self):
        response = self.client.post('/api/achievements/award', json={
            'user_id': 'user123',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_award_rejects_unknown_achievement_id(self):
        response = self.client.post('/api/achievements/award', json={
            'user_id': 'user123',
            'achievement_id': 'not-real',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['error']['code'], 'NOT_FOUND')

    def test_award_rejects_unknown_user(self):
        _, admin_csrf_token = self._login(username='AdminUser', password='password123')
        response = self.client.post('/api/achievements/award', json={
            'user_id': 'missing-user',
            'achievement_id': 'first_glucose',
        }, headers={'X-CSRF-Token': admin_csrf_token})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['error']['code'], 'NOT_FOUND')

    def test_coach_rejects_non_text_message(self):
        response = self.client.post('/api/coach/respond', json={
            'message': {'unexpected': True},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_coach_rejects_blank_message_without_model_call(self):
        with patch.object(app_module, 'nvidia_chat_completion') as mock_chat:
            response = self.client.post('/api/coach/respond', json={
                'message': '   ',
            }, headers={'X-CSRF-Token': self.csrf_token})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')
        mock_chat.assert_not_called()

    def test_cross_user_access_is_forbidden(self):
        register_response = self.client.post('/api/auth/register', json={
            'username': 'OtherUser',
            'password': 'password123',
        })
        self.assertEqual(register_response.status_code, 200)
        other_id = register_response.get_json()['user']['id']

        response = self.client.get('/api/glucose/latest/user123')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error']['code'], 'FORBIDDEN')

        create_response = self.client.post(f'/api/glucose/{other_id}', json={
            'value': 125,
            'timestamp': app_module.utcnow().isoformat(),
        }, headers={'X-CSRF-Token': register_response.get_json()['csrf_token']})
        self.assertEqual(create_response.status_code, 201)

    def test_all_user_scoped_collections_reject_cross_user_access(self):
        register_response = self.client.post('/api/auth/register', json={
            'username': 'RouteAuditUser',
            'password': 'password123',
        })
        self.assertEqual(register_response.status_code, 200)

        routes = [
            '/api/profile/user123',
            '/api/glucose/latest/user123',
            '/api/glucose/user123',
            '/api/meals/user123',
            '/api/insulin/user123',
            '/api/alerts/user123',
            '/api/alert-rules/user123',
            '/api/achievements/user123',
            '/api/achievements/progress/user123',
            '/api/analytics/glucose/user123',
            '/api/settings/user123',
            '/api/meals/user123/summary',
            '/api/insulin/user123/summary',
            '/api/alerts/evaluate/user123',
            '/api/emergency/contacts/user123',
            '/api/shop/requests/user123',
        ]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 403)

    def test_record_mutations_reject_cross_user_access(self):
        glucose = self.client.post('/api/glucose/user123', json={
            'value': 123,
            'timestamp': app_module.utcnow().isoformat(),
        }, headers={'X-CSRF-Token': self.csrf_token}).get_json()['reading']
        meal = self.client.post('/api/meals/user123', json={
            'name': 'Ownership test',
            'carbs': 20,
        }, headers={'X-CSRF-Token': self.csrf_token}).get_json()['meal']
        shop = self.client.post('/api/shop/requests/user123', json={
            'item_id': 'sensor-pack',
            'quantity': 1,
        }, headers={'X-CSRF-Token': self.csrf_token}).get_json()['request']

        other = self.client.post('/api/auth/register', json={
            'username': 'RecordAuditUser',
            'password': 'password123',
        }).get_json()
        headers = {'X-CSRF-Token': other['csrf_token']}

        attempts = [
            self.client.delete(f"/api/glucose/{glucose['id']}", headers=headers),
            self.client.delete(f"/api/meals/{meal['id']}", headers=headers),
            self.client.delete(f"/api/shop/request/{shop['id']}", headers=headers),
        ]
        self.assertTrue(all(response.status_code == 403 for response in attempts))

    def test_premium_users_do_not_gain_admin_access(self):
        register_response = self.client.post('/api/auth/register', json={
            'username': 'PremiumUser',
            'password': 'password123',
        })
        self.assertEqual(register_response.status_code, 200)
        premium_user = register_response.get_json()['user']
        app_module.execute("UPDATE users SET plan = 'premium' WHERE id = ?", (premium_user['id'],))

        forbidden_response = self.client.get('/api/glucose/latest/user123')
        self.assertEqual(forbidden_response.status_code, 403)
        self.assertEqual(forbidden_response.get_json()['error']['code'], 'FORBIDDEN')

    def test_malformed_json_returns_400(self):
        response = self.client.post('/api/auth/login', data='not-json', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_oversized_json_is_rejected_before_validation(self):
        response = self.client.post('/api/auth/login', json={
            'username': 'x' * (1024 * 1024),
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 413)

    def test_auth_rejects_non_text_credentials(self):
        cases = [
            ('/api/auth/register', {'username': {'unexpected': True}, 'password': 'password123'}),
            ('/api/auth/register', {'username': 'NewUser', 'password': {'unexpected': True}}),
            ('/api/auth/login', {'username': {'unexpected': True}, 'password': 'password123'}),
            ('/api/auth/login', {'username': 'TestUser', 'password': {'unexpected': True}}),
        ]
        for endpoint, payload in cases:
            with self.subTest(endpoint=endpoint, field=next(key for key, value in payload.items() if not isinstance(value, str))):
                response = self.client.post(endpoint, json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_settings_reject_malformed_sections(self):
        response = self.client.put('/api/settings/user123', json={
            'profile': 'not-an-object',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_settings_reject_falsey_malformed_sections(self):
        for field, value in (('profile', False), ('alert_rules', 0), ('notification_settings', '')):
            with self.subTest(field=field):
                response = self.client.put('/api/settings/user123', json={
                    field: value,
                }, headers={'X-CSRF-Token': self.csrf_token})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_settings_reject_non_boolean_notification_flag(self):
        response = self.client.put('/api/settings/user123', json={
            'notification_settings': {'push_enabled': 'false'},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_settings_invalid_notification_keeps_other_sections_unchanged(self):
        before = self.client.get('/api/settings/user123').get_json()
        response = self.client.put('/api/settings/user123', json={
            'profile': {'username': 'Changed User', 'target_low': 80, 'target_high': 180},
            'alert_rules': {'low': 80, 'high': 200},
            'notification_settings': {'push_enabled': 'false'},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

        after = self.client.get('/api/settings/user123').get_json()
        self.assertEqual(after['profile']['username'], before['profile']['username'])
        self.assertEqual(after['profile']['target_low'], before['profile']['target_low'])
        self.assertEqual(after['alert_rules']['low'], before['alert_rules']['low'])
        self.assertEqual(after['alert_rules']['high'], before['alert_rules']['high'])

    def test_settings_partial_update_preserves_omitted_sections(self):
        seed_response = self.client.put('/api/settings/user123', json={
            'alert_rules': {'low': 85, 'high': 210, 'stale_minutes': 45},
            'notification_settings': {'missed_meal_alert': True, 'push_enabled': False},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(seed_response.status_code, 200)

        response = self.client.put('/api/settings/user123', json={
            'profile': {'diabetes_type': 'Type 1'},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 200)
        settings = response.get_json()['settings']
        self.assertEqual(settings['profile']['diabetes_type'], 'Type 1')
        self.assertEqual(settings['alert_rules']['low'], 85)
        self.assertEqual(settings['alert_rules']['high'], 210)
        self.assertEqual(settings['alert_rules']['stale_minutes'], 45)
        self.assertEqual(settings['notification_settings']['missed_meal_alert'], 1)
        self.assertEqual(settings['notification_settings']['push_enabled'], 0)

    def test_default_settings_rows_tolerate_initialization_race(self):
        for table, getter in (
            ('alert_rules', app_module.get_alert_rules),
            ('notification_settings', app_module.get_notification_settings),
        ):
            with self.subTest(table=table):
                app_module.execute(f"DELETE FROM {table} WHERE user_id = ?", ('user123',))
                real_fetch_one = app_module.fetch_one
                calls = {'count': 0}

                def racing_fetch(query, params=()):
                    calls['count'] += 1
                    if calls['count'] == 1:
                        app_module.execute(
                            f"INSERT INTO {table} (user_id, updated_at) VALUES (?, ?)",
                            ('user123', app_module.iso()),
                        )
                        return None
                    return real_fetch_one(query, params)

                with patch.object(app_module, 'fetch_one', side_effect=racing_fetch):
                    row = getter('user123')
                self.assertEqual(row['user_id'], 'user123')

    def test_alert_rules_reject_contradictory_threshold_order(self):
        response = self.client.put('/api/alert-rules/user123', json={
            'urgent_low': 100,
            'low': 80,
            'high': 70,
            'urgent_high': 200,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_alert_rules_partial_update_preserves_omitted_values(self):
        seed_response = self.client.put('/api/alert-rules/user123', json={
            'urgent_low': 60,
            'low': 85,
            'high': 210,
            'urgent_high': 260,
            'stale_minutes': 45,
            'missed_meal_hours': 8,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(seed_response.status_code, 200)

        response = self.client.put('/api/alert-rules/user123', json={
            'low': 90,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 200)
        rules = response.get_json()['alert_rules']
        self.assertEqual(rules['urgent_low'], 60)
        self.assertEqual(rules['low'], 90)
        self.assertEqual(rules['high'], 210)
        self.assertEqual(rules['urgent_high'], 260)
        self.assertEqual(rules['stale_minutes'], 45)
        self.assertEqual(rules['missed_meal_hours'], 8)

    def test_alert_rules_reject_invalid_stale_minutes(self):
        response = self.client.put('/api/alert-rules/user123', json={
            'stale_minutes': 'soon',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_settings_reject_contradictory_threshold_order(self):
        response = self.client.put('/api/settings/user123', json={
            'alert_rules': {'urgent_low': 100, 'low': 80, 'high': 70, 'urgent_high': 200},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_settings_reject_target_low_above_target_high(self):
        response = self.client.put('/api/settings/user123', json={
            'profile': {'target_low': 200, 'target_high': 100},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_auth_register(self):
        response = self.client.post('/api/auth/register', json={
            'username': 'NewUser',
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        self.assertIn('csrf_token', response.get_json())

    def test_auth_register_rolls_back_partial_account_bootstrap(self):
        app_module.execute(
            "INSERT INTO cgm_connections (user_id, state, backend_available, updated_at) VALUES (?, ?, ?, ?)",
            ('user_fixed', 'not_connected', 0, app_module.iso()),
        )
        with patch.object(app_module.secrets, 'token_hex', return_value='fixed'):
            response = self.client.post('/api/auth/register', json={
                'username': 'AtomicUser',
                'password': 'password123',
            })
        self.assertEqual(response.status_code, 500)
        self.assertIsNone(app_module.get_user_by_username('AtomicUser'))

    def test_auth_register_rejects_case_insensitive_duplicate(self):
        response = self.client.post('/api/auth/register', json={
            'username': 'testuser',
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['error']['code'], 'CONFLICT')

    def test_auth_register_handles_username_uniqueness_race(self):
        duplicate_error = app_module.IntegrityError('insert', {}, Exception('duplicate'))
        with patch.object(app_module, 'get_user_by_username', return_value=None), patch.object(app_module, 'conn_execute', side_effect=duplicate_error):
            response = self.client.post('/api/auth/register', json={
                'username': 'RaceUser',
                'password': 'password123',
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['error']['code'], 'CONFLICT')

    def test_auth_login_is_case_insensitive(self):
        response = self.client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['user']['id'], 'user123')

    def test_profile_username_conflict_returns_409(self):
        register_response = self.client.post('/api/auth/register', json={
            'username': 'CollisionUser',
            'password': 'password123',
        })
        self.assertEqual(register_response.status_code, 200)

        collision_login = self.client.post('/api/auth/login', json={
            'username': 'CollisionUser',
            'password': 'password123',
        })
        self.assertEqual(collision_login.status_code, 200)

        response = self.client.put(f"/api/profile/{register_response.get_json()['user']['id']}", json={
            'username': 'TestUser',
            'diabetes_type': 'Type 1',
            'units': 'mg/dL',
            'target_low': 70,
            'target_high': 180,
        }, headers={'X-CSRF-Token': collision_login.get_json()['csrf_token']})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['error']['code'], 'CONFLICT')

    def test_profile_rejects_inverted_target_range(self):
        response = self.client.put('/api/profile/user123', json={
            'target_low': 200,
            'target_high': 100,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_profile_partial_update_preserves_settings_json(self):
        seed_response = self.client.put('/api/profile/user123', json={
            'settings': {'theme': 'dark', 'view': 'compact'},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(seed_response.status_code, 200)

        response = self.client.put('/api/profile/user123', json={
            'diabetes_type': 'Type 2',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 200)
        profile = response.get_json()['profile']
        self.assertEqual(profile['diabetes_type'], 'Type 2')
        self.assertEqual(profile['settings_json'], '{"theme": "dark", "view": "compact"}')

    def test_profile_rejects_non_object_settings(self):
        response = self.client.put('/api/profile/user123', json={
            'settings': ['unexpected'],
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_execute_rolls_back_and_closes_on_failure(self):
        class FailingConnection:
            rolled_back = False
            closed = False

            def execute(self, *_args, **_kwargs):
                raise RuntimeError('write failed')

            def rollback(self):
                self.rolled_back = True

            def close(self):
                self.closed = True

        connection = FailingConnection()
        with patch.object(app_module, 'db', return_value=connection):
            with self.assertRaises(RuntimeError):
                app_module.execute('UPDATE users SET username = ? WHERE id = ?', ('Name', 'user123'))
        self.assertTrue(connection.rolled_back)
        self.assertTrue(connection.closed)

    def test_fetch_helpers_close_on_failure(self):
        class FailingConnection:
            closed = False

            def execute(self, *_args, **_kwargs):
                raise RuntimeError('read failed')

            def close(self):
                self.closed = True

        for helper in (app_module.fetch_one, app_module.fetch_all):
            with self.subTest(helper=helper.__name__):
                connection = FailingConnection()
                with patch.object(app_module, 'db', return_value=connection):
                    with self.assertRaises(RuntimeError):
                        helper('SELECT 1')
                self.assertTrue(connection.closed)

    def test_demo_reset_is_blocked_in_production(self):
        original_env = os.environ.get('FLASK_ENV')
        original_config = app_module.CONFIG
        os.environ['FLASK_ENV'] = 'production'
        app_module.CONFIG = app_module.Config(
            app_env='production',
            flask_debug=False,
            secret_key='x' * 32,
            database_url=original_config.database_url,
            cors_origins=original_config.cors_origins,
            log_level=original_config.log_level,
            port=original_config.port,
            token_ttl_minutes=original_config.token_ttl_minutes,
            request_timeout_seconds=original_config.request_timeout_seconds,
            demo_reset_enabled=False,
            gunicorn_workers=original_config.gunicorn_workers,
            gunicorn_threads=original_config.gunicorn_threads,
            gunicorn_timeout=original_config.gunicorn_timeout,
            session_ttl_minutes=original_config.session_ttl_minutes,
            cookie_secure=original_config.cookie_secure,
        )
        try:
            response = self.client.post('/api/demo/reset', headers={'X-CSRF-Token': self.csrf_token})
            self.assertEqual(response.status_code, 403)
            self.assertFalse(response.get_json()['success'])
        finally:
            app_module.CONFIG = original_config
            if original_env is None:
                os.environ.pop('FLASK_ENV', None)
            else:
                os.environ['FLASK_ENV'] = original_env

    def test_demo_reset_rejects_remote_callers(self):
        response = self.client.post('/api/demo/reset', headers={'X-CSRF-Token': self.csrf_token}, environ_base={'REMOTE_ADDR': '203.0.113.10'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()['success'])

    def test_demo_reset_rolls_back_and_preserves_data_when_reseed_fails(self):
        app_module.execute(
            "INSERT INTO glucose_readings (id, user_id, value, timestamp, source, notes, symptoms, context, is_stale, archived, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('g_reset_guard', 'user123', 123, app_module.iso(), 'manual', '', '', 'test', 0, 0, app_module.iso()),
        )

        with patch.object(app_module, 'seed_demo_data', side_effect=RuntimeError('seed failed')):
            response = self.client.post('/api/demo/reset', headers={'X-CSRF-Token': self.csrf_token})

        self.assertEqual(response.status_code, 500)
        self.assertIsNotNone(app_module.fetch_one(
            "SELECT id FROM glucose_readings WHERE id = ?",
            ('g_reset_guard',),
        ))

    def test_missing_nvidia_config_fails_cleanly(self):
        keys = ['NVIDIA_API_KEY', 'NVIDIA_API_BASE_URL', 'NVIDIA_COACH_MODEL', 'NVIDIA_SAFETY_MODEL']
        original_env = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            with self.assertRaises(RuntimeError):
                importlib.reload(app_module)
        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            importlib.reload(app_module)

    def test_production_config_requires_secret(self):
        with patch.dict(os.environ, {
            'APP_ENV': 'production',
            'FLASK_ENV': 'production',
            'SECRET_KEY': '',
            'DATABASE_URL': '/tmp/gluverse.db',
            'CORS_ORIGINS': 'http://localhost:5000',
        }, clear=False):
            with self.assertRaises(RuntimeError):
                app_module.load_config()

    def test_invalid_numeric_config_fails(self):
        with patch.dict(os.environ, {
            'APP_ENV': 'development',
            'TOKEN_TTL_MINUTES': 'not-a-number',
        }, clear=False):
            with self.assertRaises(RuntimeError):
                app_module.load_config()

    def test_auth_rate_limit_applies_in_production(self):
        original_config = app_module.CONFIG
        app_module._rate_limit_buckets.clear()
        app_module.CONFIG = app_module.Config(
            **{**original_config.__dict__, 'app_env': 'production'}
        )
        try:
            for index in range(60):
                response = self.client.post('/api/auth/login', json={
                    'username': 'missing-user',
                    'password': 'password123',
                }, headers={'X-Forwarded-For': f'198.51.100.{index + 1}'})
                self.assertEqual(response.status_code, 401)
            limited = self.client.post('/api/auth/login', json={
                'username': 'missing-user',
                'password': 'password123',
            }, headers={'X-Forwarded-For': '203.0.113.1'})
            self.assertEqual(limited.status_code, 429)
        finally:
            app_module.CONFIG = original_config
            app_module._rate_limit_buckets.clear()

    def test_community_posts_are_sanitized_and_clean(self):
        response = self.client.get('/api/community/posts')
        self.assertEqual(response.status_code, 200)
        posts = response.get_json()

        contents = [post['content'] for post in posts]
        self.assertNotIn('DROP * FROM INFORMATION_SCEMA', contents)
        self.assertTrue(all('display_content' in post for post in posts))

    def test_community_post_ids_are_unique(self):
        first = self.client.post('/api/community/posts', json={
            'content': 'First post',
        }, headers={'X-CSRF-Token': self.csrf_token})
        second = self.client.post('/api/community/posts', json={
            'content': 'Second post',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.get_json()['post']['id'], second.get_json()['post']['id'])

    def test_community_post_rejects_non_text_content(self):
        response = self.client.post('/api/community/posts', json={
            'content': {'unexpected': True},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_community_post_rejects_blank_content(self):
        response = self.client.post('/api/community/posts', json={
            'content': '   ',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_community_report_rejects_non_text_reason(self):
        post_id = self.client.get('/api/community/posts').get_json()[0]['id']
        response = self.client.post(f'/api/community/posts/{post_id}/report', json={
            'reason': {'unexpected': True},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_community_report_rejects_unknown_post(self):
        response = self.client.post('/api/community/posts/missing-post/report', json={}, headers={
            'X-CSRF-Token': self.csrf_token,
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['error']['code'], 'NOT_FOUND')

    def test_community_hide_rejects_unknown_post(self):
        _, admin_csrf_token = self._login(username='AdminUser', password='password123')
        response = self.client.post('/api/community/posts/missing-post/hide', headers={
            'X-CSRF-Token': admin_csrf_token,
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['error']['code'], 'NOT_FOUND')

    def test_community_delete_rejects_unknown_post(self):
        _, admin_csrf_token = self._login(username='AdminUser', password='password123')
        response = self.client.delete('/api/community/posts/missing-post', headers={
            'X-CSRF-Token': admin_csrf_token,
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['error']['code'], 'NOT_FOUND')

    def test_glucose_rejects_non_text_source(self):
        response = self.client.post('/api/glucose/user123', json={
            'value': 110,
            'source': {'unexpected': True},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_glucose_rejects_non_text_timestamp(self):
        response = self.client.post('/api/glucose/user123', json={
            'value': 110,
            'timestamp': {'unexpected': True},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_health_records_reject_falsey_non_text_timestamps(self):
        cases = [
            ('/api/glucose/user123', {'value': 110, 'timestamp': 0}),
            ('/api/meals/user123', {'name': 'Breakfast', 'timestamp': False}),
            ('/api/insulin/user123', {'units': 1, 'timestamp': 0}),
        ]
        for endpoint, payload in cases:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json=payload, headers={'X-CSRF-Token': self.csrf_token})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.get_json()['success'])

    def test_health_records_reject_timezone_naive_timestamps(self):
        cases = [
            ('/api/glucose/user123', {'value': 110, 'timestamp': '2026-08-29T12:00:00'}),
            ('/api/meals/user123', {'name': 'Breakfast', 'timestamp': '2026-08-29T12:00:00'}),
            ('/api/insulin/user123', {'units': 1, 'timestamp': '2026-08-29T12:00:00'}),
        ]
        for endpoint, payload in cases:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json=payload, headers={'X-CSRF-Token': self.csrf_token})
                self.assertEqual(response.status_code, 400)

    def test_health_timestamps_are_normalized_to_utc(self):
        response = self.client.post('/api/glucose/user123', json={
            'value': 110,
            'timestamp': '2026-08-29T12:00:00+05:30',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()['reading']['timestamp'], '2026-08-29T06:30:00+00:00')

    def test_health_records_reject_far_future_timestamps(self):
        cases = [
            ('/api/glucose/user123', {'value': 110, 'timestamp': '2100-01-01T00:00:00+00:00'}),
            ('/api/meals/user123', {'name': 'Breakfast', 'timestamp': '2100-01-01T00:00:00+00:00'}),
            ('/api/insulin/user123', {'units': 1, 'timestamp': '2100-01-01T00:00:00+00:00'}),
        ]
        for endpoint, payload in cases:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json=payload, headers={'X-CSRF-Token': self.csrf_token})
                self.assertEqual(response.status_code, 400)

    def test_health_records_reject_timestamps_that_overflow_utc(self):
        response = self.client.post('/api/glucose/user123', json={
            'value': 110,
            'timestamp': '9999-12-31T23:59:59-23:59',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)

    def test_glucose_rejects_fractional_value(self):
        response = self.client.post('/api/glucose/user123', json={
            'value': 110.5,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_insulin_rejects_non_text_id(self):
        response = self.client.post('/api/insulin/user123', json={
            'id': {'unexpected': True},
            'units': 1,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_insulin_rejects_duplicate_id(self):
        payload = {'id': 'duplicate-insulin', 'units': 1}
        first = self.client.post('/api/insulin/user123', json=payload, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post('/api/insulin/user123', json=payload, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()['error']['code'], 'CONFLICT')

    def test_insulin_rejects_unknown_linked_meal(self):
        response = self.client.post('/api/insulin/user123', json={
            'units': 1,
            'linked_meal_id': 'missing-meal',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_duplicate_achievements_are_not_returned(self):
        response = self.client.get('/api/achievements/progress/user123')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertCountEqual(payload['earned_achievements'], [
            'week_warrior',
            'meal_tracker',
            'glucose_guardian',
        ])

    def test_emergency_contacts_persist(self):
        save_response = self.client.put('/api/emergency/contacts/user123', json={
            'contacts': [
                {'name': 'Casey', 'phone': '555-0101', 'relationship': 'Caregiver'},
                {'name': 'Mina', 'phone': '555-0102', 'relationship': 'Partner'},
            ]
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(save_response.status_code, 200)
        self.assertTrue(save_response.get_json()['success'])

        get_response = self.client.get('/api/emergency/contacts/user123')
        self.assertEqual(get_response.status_code, 200)
        contacts = get_response.get_json()
        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0]['name'], 'Casey')

    def test_emergency_contacts_reject_malformed_payload(self):
        response = self.client.put('/api/emergency/contacts/user123', json={
            'contacts': 'not-a-list',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_emergency_contacts_reject_incomplete_contact(self):
        response = self.client.put('/api/emergency/contacts/user123', json={
            'contacts': [{'name': 'Casey', 'phone': ''}],
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_emergency_contacts_reject_non_text_name(self):
        response = self.client.put('/api/emergency/contacts/user123', json={
            'contacts': [{'name': {'unexpected': True}, 'phone': '555-0101'}],
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')

    def test_emergency_contacts_reject_duplicate_ids(self):
        save_response = self.client.put('/api/emergency/contacts/user123', json={
            'contacts': [{'id': 'existing-contact', 'name': 'Casey', 'phone': '555-0101'}],
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(save_response.status_code, 200)
        response = self.client.put('/api/emergency/contacts/user123', json={
            'contacts': [
                {'id': 'same-contact', 'name': 'Casey', 'phone': '555-0101'},
                {'id': 'same-contact', 'name': 'Mina', 'phone': '555-0102'},
            ],
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'VALIDATION_ERROR')
        self.assertEqual(self.client.get('/api/emergency/contacts/user123').get_json()[0]['id'], 'existing-contact')

    def test_shop_request_lifecycle(self):
        create_response = self.client.post('/api/shop/requests/user123', json={
            'item_id': 'sensor-pack',
            'quantity': 2,
            'notes': 'Need backup sensors.',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(create_response.status_code, 200)
        payload = create_response.get_json()
        self.assertTrue(payload['success'])

        get_response = self.client.get('/api/shop/requests/user123')
        self.assertEqual(get_response.status_code, 200)
        requests = get_response.get_json()
        self.assertGreaterEqual(len(requests), 1)
        self.assertEqual(requests[0]['item_id'], 'sensor-pack')

        delete_response = self.client.delete(f"/api/shop/request/{requests[0]['id']}", headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.get_json()['success'])

    def test_shop_request_save_without_status_preserves_existing_status(self):
        create_response = self.client.post('/api/shop/requests/user123', json={
            'item_id': 'sensor-pack',
            'quantity': 2,
            'notes': 'Need backup sensors.',
            'status': 'requested',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(create_response.status_code, 200)

        save_response = self.client.post('/api/shop/requests/user123', json={
            'item_id': 'sensor-pack',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(save_response.status_code, 200)
        saved_request = save_response.get_json()['request']
        self.assertEqual(saved_request['quantity'], 2)
        self.assertEqual(saved_request['notes'], 'Need backup sensors.')
        self.assertEqual(saved_request['status'], 'requested')

    def test_shop_request_blank_status_preserves_existing_or_default_status(self):
        create_response = self.client.post('/api/shop/requests/user123', json={
            'item_id': 'sensor-pack',
            'status': '   ',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.get_json()['request']['status'], 'saved')

        update_response = self.client.put(
            f"/api/shop/request/{create_response.get_json()['request']['id']}",
            json={'status': '   '},
            headers={'X-CSRF-Token': self.csrf_token},
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json()['request']['status'], 'saved')

    def test_shop_request_rejects_invalid_quantity(self):
        invalid_create = self.client.post('/api/shop/requests/user123', json={
            'item_id': 'sensor-pack',
            'quantity': 'many',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(invalid_create.status_code, 400)
        self.assertFalse(invalid_create.get_json()['success'])

        create_response = self.client.post('/api/shop/requests/user123', json={
            'item_id': 'sensor-pack',
            'quantity': 1,
            'notes': 'Need backup sensors.',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(create_response.status_code, 200)
        request_id = create_response.get_json()['request']['id']

        update_response = self.client.put(f'/api/shop/request/{request_id}', json={
            'quantity': 'many',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(update_response.status_code, 400)
        self.assertFalse(update_response.get_json()['success'])

        over_limit_response = self.client.put(f"/api/shop/request/{request_id}", json={
            'quantity': 100,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(over_limit_response.status_code, 400)
        self.assertFalse(over_limit_response.get_json()['success'])

        invalid_notes_response = self.client.put(f"/api/shop/request/{request_id}", json={
            'notes': 123,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(invalid_notes_response.status_code, 400)
        self.assertFalse(invalid_notes_response.get_json()['success'])

        invalid_status_response = self.client.put(f"/api/shop/request/{request_id}", json={
            'status': {'unexpected': True},
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(invalid_status_response.status_code, 400)
        self.assertFalse(invalid_status_response.get_json()['success'])

    def test_shop_request_rejects_non_text_item_id(self):
        response = self.client.post('/api/shop/requests/user123', json={
            'item_id': 123,
            'quantity': 1,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_analytics_uses_recent_data(self):
        response = self.client.get('/api/analytics/glucose/user123?date_range=7D')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload['readings_count'], 3)
        self.assertGreater(payload['average_glucose'], 0)

    def test_meal_create_edit_delete(self):
        create_response = self.client.post('/api/meals/user123', json={
            'name': 'Lunch',
            'carbs': 55,
            'protein': 22,
            'fat': 14,
            'calories': 520,
            'notes': 'test meal',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(create_response.status_code, 201)
        meal = create_response.get_json()['meal']

        update_response = self.client.put(f"/api/meals/{meal['id']}", json={
            'name': 'Updated Lunch',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(update_response.status_code, 200)
        updated_meal = update_response.get_json()['meal']
        self.assertEqual(updated_meal['name'], 'Updated Lunch')
        self.assertEqual(updated_meal['carbs'], 55)
        self.assertEqual(updated_meal['protein'], 22)
        self.assertEqual(updated_meal['fat'], 14)
        self.assertEqual(updated_meal['calories'], 520)
        self.assertEqual(updated_meal['notes'], 'test meal')

        invalid_timestamp = self.client.put(f"/api/meals/{meal['id']}", json={
            **meal,
            'timestamp': 'not-a-timestamp',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(invalid_timestamp.status_code, 400)
        self.assertFalse(invalid_timestamp.get_json()['success'])

        invalid_falsey_timestamp = self.client.put(f"/api/meals/{meal['id']}", json={
            **meal,
            'timestamp': False,
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(invalid_falsey_timestamp.status_code, 400)
        self.assertFalse(invalid_falsey_timestamp.get_json()['success'])

        delete_response = self.client.delete(f"/api/meals/{meal['id']}", headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(delete_response.status_code, 200)

    def test_insulin_create(self):
        response = self.client.post('/api/insulin/user123', json={
            'insulin_type': 'bolus',
            'units': 3.5,
            'notes': 'with lunch',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()['insulin']['units'], 3.5)

    def test_old_low_glucose_does_not_trigger_emergency(self):
        app_module.execute("DELETE FROM glucose_readings WHERE user_id = ?", ('user123',))
        stale_timestamp = (app_module.utcnow() - app_module.dt.timedelta(hours=2)).isoformat()
        self.client.post('/api/glucose/user123', json={
            'value': 45,
            'timestamp': stale_timestamp,
            'source': 'manual',
        }, headers={'X-CSRF-Token': self.csrf_token})

        response = self.client.get('/api/alerts/evaluate/user123')
        self.assertEqual(response.status_code, 200)
        alert = response.get_json()['alert']
        self.assertFalse(alert['triggered'])
        self.assertEqual(alert['reason'], 'stale')

    def test_fresh_low_glucose_triggers_alert(self):
        self.client.post('/api/glucose/user123', json={
            'value': 60,
            'timestamp': app_module.utcnow().isoformat(),
            'source': 'manual',
        }, headers={'X-CSRF-Token': self.csrf_token})

        response = self.client.get('/api/alerts/evaluate/user123')
        self.assertEqual(response.status_code, 200)
        alert = response.get_json()['alert']
        self.assertTrue(alert['triggered'])
        self.assertEqual(alert['severity'], 'low')

    def test_cgm_unavailable_gracefully(self):
        response = self.client.post('/api/cgm/sync', json={
            'username': 'demo',
            'password': 'demo',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 503)
        self.assertIn('not enabled', response.get_json()['message'])

    def test_notification_test_gracefully_fails_when_gated(self):
        response = self.client.post('/api/notifications/test-low-email', json={
            'email': 'demo@example.com',
        }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 503)
        self.assertIn('not enabled', response.get_json()['message'])

    def test_ai_coach_refuses_insulin_dosing(self):
        with patch.object(app_module, 'nvidia_chat_completion') as mock_chat:
            response = self.client.post('/api/coach/respond', json={
                'user_id': 'user123',
                'message': 'How much insulin should I dose?',
            }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 400)
        self.assertIn('insulin dosing', response.get_json()['message'])
        mock_chat.assert_not_called()

    def test_ai_coach_returns_next_top_5(self):
        with patch.object(app_module, 'nvidia_chat_completion', return_value='Coach reply.\n1. First\n2. Second\n3. Third\n4. Fourth\n5. Fifth') as mock_chat:
            response = self.client.post('/api/coach/respond', json={
                'user_id': 'user123',
                'message': 'Give me the next top 5',
            }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        mock_chat.assert_called_once()
        self.assertEqual(payload['reply'], 'Coach reply.')
        self.assertEqual(len(payload['next_top_5']), 5)
        self.assertEqual(payload['next_top_5'][0], 'First')

    def test_ai_coach_deduplicates_next_top_5(self):
        with patch.object(app_module, 'nvidia_chat_completion', return_value='Coach reply.\n1. First\n2. First\n3. Second\n4. Third\n5. Fourth\n6. Fifth'):
            response = self.client.post('/api/coach/respond', json={
                'user_id': 'user123',
                'message': 'Give me five steps',
            }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['next_top_5'], ['First', 'Second', 'Third', 'Fourth', 'Fifth'])

    def test_ai_coach_falls_back_when_model_returns_fewer_than_five_steps(self):
        with patch.object(app_module, 'nvidia_chat_completion', return_value='Coach reply.\n1. Only one'):
            response = self.client.post('/api/coach/respond', json={
                'user_id': 'user123',
                'message': 'Give me five steps',
            }, headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()['next_top_5']), 5)

    def test_request_id_is_preserved(self):
        response = self.client.get('/api/health', headers={'X-Request-ID': 'test-request-id'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-Request-ID'], 'test-request-id')

    def test_nvidia_chat_completion_retries_once(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"Retry worked.\\n1. One\\n2. Two\\n3. Three"}}]}'

        with patch.object(app_module.urllib.request, 'urlopen', side_effect=[urllib.error.URLError('boom'), FakeResponse()]) as mock_urlopen:
            reply = app_module.nvidia_chat_completion('test-model', [{'role': 'user', 'content': 'hello'}])
        self.assertEqual(reply, 'Retry worked.\n1. One\n2. Two\n3. Three')
        self.assertEqual(mock_urlopen.call_count, 2)

    def test_ai_coach_uses_safety_model_for_concern(self):
        original_config = app_module.CONFIG
        with patch.object(app_module, 'nvidia_chat_completion', return_value='Safety reply.\n1. Emergency\n2. Recheck\n3. Call care team') as mock_chat:
            try:
                app_module.CONFIG = app_module.Config(
                    app_env=app_module.CONFIG.app_env,
                    flask_debug=app_module.CONFIG.flask_debug,
                    secret_key=app_module.CONFIG.secret_key,
                    database_url=app_module.CONFIG.database_url,
                    cors_origins=app_module.CONFIG.cors_origins,
                    log_level=app_module.CONFIG.log_level,
                    port=app_module.CONFIG.port,
                    token_ttl_minutes=app_module.CONFIG.token_ttl_minutes,
                    request_timeout_seconds=app_module.CONFIG.request_timeout_seconds,
                    demo_reset_enabled=app_module.CONFIG.demo_reset_enabled,
                    gunicorn_workers=app_module.CONFIG.gunicorn_workers,
                    gunicorn_threads=app_module.CONFIG.gunicorn_threads,
                    gunicorn_timeout=app_module.CONFIG.gunicorn_timeout,
                    session_ttl_minutes=app_module.CONFIG.session_ttl_minutes,
                    cookie_secure=app_module.CONFIG.cookie_secure,
                    nvidia_api_key=app_module.CONFIG.nvidia_api_key,
                    nvidia_api_base_url=app_module.CONFIG.nvidia_api_base_url,
                    nvidia_coach_model='normal-model',
                    nvidia_safety_model='safety-model',
                )
                self.client.post('/api/glucose/user123', json={
                    'value': 45,
                    'timestamp': app_module.utcnow().isoformat(),
                }, headers={'X-CSRF-Token': self.csrf_token})
                response = self.client.post('/api/coach/respond', json={
                    'user_id': 'user123',
                    'message': 'What should I do next?',
                }, headers={'X-CSRF-Token': self.csrf_token})
            finally:
                app_module.CONFIG = original_config
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['reply'], 'Safety reply.')
        self.assertEqual(mock_chat.call_args.args[0], 'safety-model')

    def test_demo_reset_restores_fresh_dashboard_seed(self):
        conn = app_module.db()
        conn.exec_driver_sql("DELETE FROM glucose_readings WHERE user_id = ?", ('user123',))
        stale_timestamp = (app_module.utcnow() - app_module.dt.timedelta(hours=2)).isoformat()
        conn.exec_driver_sql(
            "INSERT INTO glucose_readings (id, user_id, value, timestamp, source, notes, symptoms, context, is_stale, archived, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('g_stale', 'user123', 45, stale_timestamp, 'manual', '', '', 'demo', 1, 0, app_module.iso()),
        )
        conn.commit()
        conn.close()

        reset_response = self.client.post('/api/demo/reset', headers={'X-CSRF-Token': self.csrf_token})
        self.assertEqual(reset_response.status_code, 200)
        self._login()

        response = self.client.get('/api/glucose/latest/user123')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['value'], 120)
        self.assertFalse(payload['is_stale'])

    def test_frontend_has_no_raw_api_fetches(self):
        frontend_src = Path(app_module.__file__).resolve().parents[1] / 'frontend' / 'src'
        offenders = []
        for path in frontend_src.rglob('*.js'):
            if path.name == 'api.js':
                continue
            text = path.read_text()
            if "fetch('/api" in text or 'fetch("/api' in text or "fetch(`/api" in text:
                offenders.append(str(path))
        self.assertEqual(offenders, [], f'Raw frontend fetch calls remain in: {offenders}')


if __name__ == '__main__':
    unittest.main()
