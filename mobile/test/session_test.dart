import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/api/api_client.dart';
import 'package:one_english/api/oe_api.dart';
import 'package:one_english/api/secret_store.dart';
import 'package:one_english/router.dart';
import 'package:one_english/state/lock.dart';
import 'package:one_english/state/session.dart';
import 'package:one_english/state/settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/fake_backend.dart';

void main() {
  late FakeBackend be;
  late MemorySecretStore store;
  late Session s;
  late LockController lock;

  Future<void> make() async {
    SharedPreferences.setMockInitialValues({});
    final settings = Settings(await SharedPreferences.getInstance());
    final api = OeApi(ApiClient(baseUrl: 'https://oe.test', secrets: store, client: be.client));
    lock = LockController(store, settings);
    s = Session(api: api, settings: settings, lock: lock);
  }

  setUp(() {
    be = FakeBackend();
    store = MemorySecretStore();
  });

  test('no stored session → login', () async {
    await make();
    await s.boot();
    expect(s.stage, Stage.signedOut);
    expect(appRedirect(s, lock, '/home'), '/login');
    expect(appRedirect(s, lock, '/login/code'), isNull);
  });

  test('stored refresh token restores the session and loads the children', () async {
    await store.write(ApiClient.refreshKey, 'r1');
    await make();
    await s.boot();
    expect(s.stage, Stage.ready);
    expect(s.isParent, isTrue);
    expect(s.children.map((c) => c.firstName), ['Арман', 'Алия']);
    expect(s.child!.id, 3);
    s.selectChild(4);
    expect(s.child!.id, 4);
    expect(s.needsRules, isFalse);
    expect(appRedirect(s, lock, '/splash'), '/home');
    expect(appRedirect(s, lock, '/schedule'), isNull);
  });

  test('expired refresh token → login, token wiped', () async {
    await store.write(ApiClient.refreshKey, 'stale');
    await make();
    await s.boot();
    expect(s.stage, Stage.signedOut);
    expect(await store.read(ApiClient.refreshKey), isNull);
  });

  test('server unreachable on start → offline screen, token kept', () async {
    await store.write(ApiClient.refreshKey, 'r1');
    be.overrides['POST /auth/refresh'] = (_) => throw Exception('down');
    await make();
    await s.boot();
    expect(s.stage, Stage.offline);
    expect(appRedirect(s, lock, '/home'), '/offline');
    expect(await store.read(ApiClient.refreshKey), 'r1');
  });

  test('new rules version gates the app until accepted', () async {
    be.rulesAccepted = '1.0';
    be.rulesVersion = '2.0';
    await make();
    await s.verifyCode('+77052000001', '123456');
    expect(s.offerPin, isTrue);
    s.pinOffered();
    expect(s.needsRules, isTrue);
    expect(appRedirect(s, lock, '/home'), '/gate');
    await s.acceptRules();
    expect(s.needsRules, isFalse);
    expect(appRedirect(s, lock, '/gate'), '/home');
  });

  test('a PIN locks a restored session; push links wait for unlock', () async {
    await store.write(ApiClient.refreshKey, 'r1');
    await make();
    await lock.load();
    await lock.setPin('7391');
    await s.boot();
    expect(lock.locked, isTrue);
    expect(appRedirect(s, lock, '/home'), '/lock');
    s.pendingLink = '/coins';
    await lock.verify('7391');
    expect(appRedirect(s, lock, '/lock'), '/coins');
    expect(s.pendingLink, isNull);
  });

  test('staff accounts are turned away', () async {
    be.kind = 'staff';
    await make();
    await s.verifyCode('+77010000000', '123456');
    expect(s.staffRejected, isTrue);
    expect(s.stage, Stage.signedOut);
    expect(await store.read(ApiClient.refreshKey), isNull);
  });

  test('sign out calls the server and forgets the account', () async {
    await make();
    await s.verifyCode('+77052000001', '123456');
    await s.signOut();
    expect(be.requests.last.url.path, '/api/auth/logout');
    expect(s.me, isNull);
    expect(await store.read(ApiClient.refreshKey), isNull);
  });
}
