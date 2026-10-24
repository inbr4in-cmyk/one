import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/api/api_client.dart';
import 'package:one_english/api/oe_api.dart';
import 'package:one_english/api/secret_store.dart';
import 'package:one_english/app.dart';
import 'package:one_english/router.dart';
import 'package:one_english/state/counters.dart';
import 'package:one_english/state/lock.dart';
import 'package:one_english/state/realtime.dart';
import 'package:one_english/state/session.dart';
import 'package:one_english/state/settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'fake_backend.dart';

class Harness {
  Harness(this.session, this.store);
  final Session session;
  final MemorySecretStore store;
}

/// Pumps the whole app (router, providers, l10n) against [be] on a phone-sized screen.
Future<Harness> pumpApp(WidgetTester tester, FakeBackend be, {MemorySecretStore? store, Size size = const Size(390, 844)}) async {
  tester.view.physicalSize = size * 3;
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({});
  final secrets = store ?? MemorySecretStore();
  final settings = Settings(await SharedPreferences.getInstance());
  final api = OeApi(ApiClient(baseUrl: 'https://oe.test', secrets: secrets, client: be.client));
  final lock = LockController(secrets, settings);
  final session = Session(api: api, settings: settings, lock: lock);
  final realtime = Realtime(api, connect: (_) => throw UnsupportedError('no socket in tests'));
  final counters = Counters(api, session, realtime);
  final router = buildRouter(session, lock);
  await tester.pumpWidget(OeApp(
      api: api, settings: settings, session: session, lock: lock, realtime: realtime, counters: counters, router: router));
  await tester.runAsync(session.boot);
  await settle(tester);
  return Harness(session, secrets);
}

/// pumpAndSettle that tolerates endless animations (skeletons, countdowns).
Future<void> settle(WidgetTester tester, [int frames = 30]) async {
  for (var i = 0; i < frames; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
    await tester.pump(const Duration(milliseconds: 50));
  }
}

/// Unmounts the app so its timers are cancelled before the test ends.
Future<void> unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump(const Duration(seconds: 1));
}
