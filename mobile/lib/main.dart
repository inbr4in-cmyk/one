import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:local_auth/local_auth.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/api_client.dart';
import 'api/oe_api.dart';
import 'api/secret_store.dart';
import 'app.dart';
import 'config.dart';
import 'push/push_service.dart';
import 'router.dart';
import 'state/counters.dart';
import 'state/lock.dart';
import 'state/realtime.dart';
import 'state/session.dart';
import 'state/settings.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting();
  final prefs = await SharedPreferences.getInstance();
  final settings = Settings(prefs);
  final secrets = SecureSecretStore();
  final api = OeApi(ApiClient(baseUrl: AppConfig.apiBase, secrets: secrets));
  final lock = LockController(secrets, settings, auth: LocalAuthentication());
  final session = Session(api: api, settings: settings, lock: lock);
  final realtime = Realtime(api)..onSessionLost = () => session.signOut(remote: false);
  final counters = Counters(api, session, realtime);
  session.onSignedIn.add(() async {
    realtime.start();
    counters.start();
  });
  session.onSigningOut.add(() async {
    realtime.stop();
    counters.stop();
  });
  final router = buildRouter(session, lock);
  final push = PushService(api, session, settings, open: (link) => openLink(router, session, lock, link));

  runApp(OeApp(
      api: api, settings: settings, session: session, lock: lock, realtime: realtime, counters: counters, router: router));

  // Push is optional: without Firebase config files the app runs without it.
  await push.init();
  await session.boot();
}
